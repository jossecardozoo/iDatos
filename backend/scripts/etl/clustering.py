"""
Clustering jerárquico avanzado para detección de alquileres repetidos entre portales.

Implementa:
- Clustering jerárquico bottom-up
- Comparación lexicográfica de títulos
- Comparación de características físicas (dormitorios, baños, superficie)
- Comparación de ubicación (coordenadas y dirección)
- Comparación de precios
- Sistema de scoring basado en características relevantes para alquileres
- Agrupación de ofertas que hacen referencia al mismo inmueble físico
"""
import pandas as pd
import numpy as np
from typing import Optional, Tuple, List, Dict, Set
import time
from collections import defaultdict
from rapidfuzz import fuzz, process
from math import radians, cos, sin, asin, sqrt

from prefect import task, get_run_logger

from .config import DUPLICATE_SIMILARITY_THRESHOLD
from .provenance import get_provenance_tracker
from .utils import normalize_text, normalize_for_match


# Configuración de clustering
CLUSTERING_SIMILARITY_THRESHOLD = 75  # Umbral de similaridad combinada para clustering (0-100)
CLUSTERING_MIN_CLUSTER_SIZE = 2  # Tamaño mínimo de cluster
DISTANCE_THRESHOLD_METERS = 100  # Distancia máxima en metros para considerar misma ubicación
PRICE_SIMILARITY_THRESHOLD = 0.15  # 15% de diferencia máxima en precio


def normalize_title_for_clustering(title: str) -> str:
    """
    Normaliza un título para comparación lexicográfica.
    
    Args:
        title: Título a normalizar
        
    Returns:
        Título normalizado
    """
    if pd.isna(title) or not isinstance(title, str):
        return ""
    
    # Normalizar texto
    normalized = normalize_for_match(title)
    
    # Remover caracteres especiales y espacios múltiples
    normalized = ' '.join(normalized.split())
    
    return normalized.lower().strip()


def lexical_similarity(title1: str, title2: str) -> float:
    """
    Calcula la similaridad lexicográfica entre dos títulos.
    
    Usa múltiples métricas de fuzzy matching:
    - Ratio de similaridad
    - Token sort ratio (ordena tokens antes de comparar)
    - Token set ratio (compara sets de tokens)
    
    Args:
        title1: Primer título
        title2: Segundo título
        
    Returns:
        Similaridad entre 0 y 100
    """
    norm1 = normalize_title_for_clustering(title1)
    norm2 = normalize_title_for_clustering(title2)
    
    if not norm1 or not norm2:
        return 0.0
    
    # Calcular múltiples métricas de similaridad
    ratio = fuzz.ratio(norm1, norm2)
    token_sort = fuzz.token_sort_ratio(norm1, norm2)
    token_set = fuzz.token_set_ratio(norm1, norm2)
    
    # Promedio ponderado (token_set es más robusto para variaciones)
    similarity = (ratio * 0.3 + token_sort * 0.3 + token_set * 0.4)
    
    return similarity


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calcula la distancia entre dos puntos geográficos usando la fórmula de Haversine.
    
    Args:
        lat1, lon1: Coordenadas del primer punto
        lat2, lon2: Coordenadas del segundo punto
    
    Returns:
        Distancia en metros
    """
    if pd.isna(lat1) or pd.isna(lon1) or pd.isna(lat2) or pd.isna(lon2):
        return float('inf')
    
    # Convertir grados a radianes
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    
    # Fórmula de Haversine
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    
    # Radio de la Tierra en metros
    r = 6371000
    
    return c * r


def calculate_feature_score(row: pd.Series, feature_name: str, cluster_rows: Optional[List[pd.Series]] = None) -> float:
    """
    Calcula el puntaje de una característica específica para un alquiler.
    
    Características soportadas (relevantes para alquileres):
    - completitud_datos: Qué tan completo está el registro (0-100)
    - ubicacion_precisa: Si tiene coordenadas válidas (0-100)
    - precio_consistente: Si el precio es consistente con el cluster (0-100)
    - caracteristicas_completas: Si tiene dormitorios, baños, superficie (0-100)
    
    Args:
        row: Fila del DataFrame
        feature_name: Nombre de la característica
        cluster_rows: Lista de filas del cluster (para precio_consistente)
        
    Returns:
        Puntaje entre 0 y 100
    """
    if feature_name == 'completitud_datos':
        # Contar campos importantes que están presentes
        campos_importantes = ['titulo', 'ubicacion', 'precio_base_uyu', 'dorms', 'banos', 'superficie_m2']
        campos_presentes = sum(1 for campo in campos_importantes 
                             if campo in row.index and pd.notna(row.get(campo)))
        return (campos_presentes / len(campos_importantes)) * 100
    
    elif feature_name == 'ubicacion_precisa':
        # Verificar si tiene coordenadas válidas
        lat_cols = ['latitud', 'latitude', 'lat']
        lon_cols = ['longitud', 'longitude', 'lon', 'lng']
        
        has_lat = any(col in row.index and pd.notna(row.get(col)) and row.get(col) != 0 
                     for col in lat_cols)
        has_lon = any(col in row.index and pd.notna(row.get(col)) and row.get(col) != 0 
                     for col in lon_cols)
        
        if has_lat and has_lon:
            return 100.0
        elif 'ubicacion' in row.index and pd.notna(row.get('ubicacion')):
            return 50.0  # Tiene dirección pero no coordenadas
        else:
            return 0.0
    
    elif feature_name == 'precio_consistente':
        # Este se calcula en el contexto del cluster
        if cluster_rows is None:
            return 50.0
        
        precio_col = 'precio_base_uyu'
        if precio_col not in row.index or pd.isna(row[precio_col]):
            return 0.0
        
        try:
            precio = float(row[precio_col])
        except (ValueError, TypeError):
            return 0.0
        
        # Calcular precios del cluster
        precios = []
        for r in cluster_rows:
            if precio_col in r.index and pd.notna(r[precio_col]):
                try:
                    precios.append(float(r[precio_col]))
                except (ValueError, TypeError):
                    pass
        
        if not precios or len(precios) < 2:
            return 50.0
        
        # Calcular mediana y desviación
        precios_array = np.array(precios)
        mediana = np.median(precios_array)
        std = np.std(precios_array) if len(precios_array) > 1 else 0
        
        if std == 0:
            return 100.0 if precio == mediana else 0.0
        
        # Calcular distancia normalizada
        distancia = abs(precio - mediana) / std
        # Convertir a puntaje (menor distancia = mayor puntaje)
        score = max(0, 100 - (distancia * 30))
        
        return min(100, score)
    
    elif feature_name == 'caracteristicas_completas':
        # Verificar si tiene características físicas
        caracteristicas = ['dorms', 'dorms_imputado', 'banos', 'superficie_m2']
        presentes = sum(1 for car in caracteristicas 
                       if car in row.index and pd.notna(row.get(car)))
        return (presentes / len(caracteristicas)) * 100
    
    return 50.0  # Valor por defecto para características desconocidas


def calculate_article_score(row: pd.Series, cluster_rows: Optional[List[pd.Series]] = None, 
                            weights: Optional[Dict[str, float]] = None) -> float:
    """
    Calcula el puntaje total de confiabilidad de un alquiler.
    
    Función de scoring: S = Σ(Wi * Si)
    donde:
    - S: Puntaje total del alquiler
    - Wi: Peso de la característica i
    - Si: Puntaje de la característica i
    
    Args:
        row: Fila del DataFrame
        cluster_rows: Lista de filas del cluster (para precio_consistente)
        weights: Pesos para cada característica (default: pesos balanceados)
        
    Returns:
        Puntaje total entre 0 y 100
    """
    if weights is None:
        weights = {
            'completitud_datos': 0.25,
            'ubicacion_precisa': 0.30,
            'precio_consistente': 0.25,
            'caracteristicas_completas': 0.20
        }
    
    total_score = 0.0
    total_weight = 0.0
    
    for feature, weight in weights.items():
        feature_score = calculate_feature_score(row, feature, cluster_rows)
        total_score += weight * feature_score
        total_weight += weight
    
    # Normalizar por el peso total
    if total_weight > 0:
        return total_score / total_weight
    return 50.0


def compare_physical_features(row1: pd.Series, row2: pd.Series) -> float:
    """
    Compara características físicas entre dos alquileres.
    
    Compara: dormitorios, baños, superficie
    
    Args:
        row1: Primera fila
        row2: Segunda fila
        
    Returns:
        Similaridad entre 0 y 100
    """
    features = {
        'dorms': ['dorms', 'dorms_imputado'],
        'banos': ['banos', 'bathrooms'],
        'superficie': ['superficie_m2', 'superficie', 'area_m2']
    }
    
    matches = 0
    total = 0
    
    for feature_name, cols in features.items():
        val1 = None
        val2 = None
        
        # Buscar valor en row1
        for col in cols:
            if col in row1.index and pd.notna(row1[col]):
                try:
                    val1 = float(row1[col])
                    break
                except (ValueError, TypeError):
                    pass
        
        # Buscar valor en row2
        for col in cols:
            if col in row2.index and pd.notna(row2[col]):
                try:
                    val2 = float(row2[col])
                    break
                except (ValueError, TypeError):
                    pass
        
        if val1 is not None and val2 is not None:
            total += 1
            if abs(val1 - val2) <= 0.5:  # Permitir pequeña diferencia
                matches += 1
        elif val1 is None and val2 is None:
            # Ambos faltan, no penalizar
            pass
        else:
            # Uno tiene y otro no, penalizar ligeramente
            total += 1
    
    if total == 0:
        return 50.0  # No hay datos para comparar
    
    return (matches / total) * 100


def compare_location(row1: pd.Series, row2: pd.Series) -> float:
    """
    Compara ubicación entre dos alquileres.
    
    Usa coordenadas si están disponibles, sino usa similaridad de dirección.
    
    Args:
        row1: Primera fila
        row2: Segunda fila
        
    Returns:
        Similaridad entre 0 y 100 (100 = misma ubicación)
    """
    # Intentar usar coordenadas primero
    lat_cols = ['latitud', 'latitude', 'lat']
    lon_cols = ['longitud', 'longitude', 'lon', 'lng']
    
    lat1 = lon1 = lat2 = lon2 = None
    
    for col in lat_cols:
        if col in row1.index and pd.notna(row1[col]) and row1[col] != 0:
            lat1 = float(row1[col])
            break
    for col in lon_cols:
        if col in row1.index and pd.notna(row1[col]) and row1[col] != 0:
            lon1 = float(row1[col])
            break
    for col in lat_cols:
        if col in row2.index and pd.notna(row2[col]) and row2[col] != 0:
            lat2 = float(row2[col])
            break
    for col in lon_cols:
        if col in row2.index and pd.notna(row2[col]) and row2[col] != 0:
            lon2 = float(row2[col])
            break
    
    # Si ambos tienen coordenadas, usar distancia
    if all(x is not None for x in [lat1, lon1, lat2, lon2]):
        distance = haversine_distance(lat1, lon1, lat2, lon2)
        if distance <= DISTANCE_THRESHOLD_METERS:
            # Convertir distancia a similaridad (0-100 metros = 100-0 similaridad)
            similarity = max(0, 100 - (distance / DISTANCE_THRESHOLD_METERS) * 100)
            return similarity
        else:
            return 0.0
    
    # Si no hay coordenadas, comparar direcciones
    if 'ubicacion' in row1.index and 'ubicacion' in row2.index:
        ubi1 = str(row1['ubicacion']) if pd.notna(row1['ubicacion']) else ''
        ubi2 = str(row2['ubicacion']) if pd.notna(row2['ubicacion']) else ''
        
        if ubi1 and ubi2:
            similarity = fuzz.token_sort_ratio(ubi1.lower(), ubi2.lower())
            return similarity
    
    return 0.0


def compare_price(row1: pd.Series, row2: pd.Series) -> float:
    """
    Compara precios entre dos alquileres.
    
    Args:
        row1: Primera fila
        row2: Segunda fila
        
    Returns:
        Similaridad entre 0 y 100 (100 = mismo precio)
    """
    precio_col = 'precio_base_uyu'
    
    precio1 = None
    precio2 = None
    
    if precio_col in row1.index and pd.notna(row1[precio_col]):
        try:
            precio1 = float(row1[precio_col])
        except (ValueError, TypeError):
            pass
    
    if precio_col in row2.index and pd.notna(row2[precio_col]):
        try:
            precio2 = float(row2[precio_col])
        except (ValueError, TypeError):
            pass
    
    if precio1 is None or precio2 is None:
        return 0.0
    
    if precio1 == 0 or precio2 == 0:
        return 0.0
    
    # Calcular diferencia porcentual
    diff_pct = abs(precio1 - precio2) / max(precio1, precio2)
    
    if diff_pct <= PRICE_SIMILARITY_THRESHOLD:
        # Convertir a similaridad (0% diff = 100, 15% diff = 0)
        similarity = 100 - (diff_pct / PRICE_SIMILARITY_THRESHOLD) * 100
        return max(0, similarity)
    
    return 0.0


def calculate_combined_similarity(row1: pd.Series, row2: pd.Series, title_col: str = 'titulo') -> float:
    """
    Calcula la similaridad combinada entre dos alquileres.
    
    Combina múltiples factores:
    - Similaridad de título (peso: 0.25)
    - Similaridad de ubicación (peso: 0.30)
    - Similaridad de precio (peso: 0.20)
    - Similaridad de características físicas (peso: 0.25)
    
    Args:
        row1: Primera fila
        row2: Segunda fila
        title_col: Nombre de la columna de título
        
    Returns:
        Similaridad combinada entre 0 y 100
    """
    # Similaridad de título
    title_sim = lexical_similarity(
        row1.get(title_col, '') if title_col in row1.index else '',
        row2.get(title_col, '') if title_col in row2.index else ''
    )
    
    # Similaridad de ubicación
    location_sim = compare_location(row1, row2)
    
    # Similaridad de precio
    price_sim = compare_price(row1, row2)
    
    # Similaridad de características físicas
    features_sim = compare_physical_features(row1, row2)
    
    # Combinar con pesos
    weights = {
        'title': 0.25,
        'location': 0.30,
        'price': 0.20,
        'features': 0.25
    }
    
    combined = (
        title_sim * weights['title'] +
        location_sim * weights['location'] +
        price_sim * weights['price'] +
        features_sim * weights['features']
    )
    
    return combined


def build_similarity_matrix_optimized(df: pd.DataFrame, title_col: str = 'titulo', 
                                      logger=None) -> Dict[Tuple[int, int], float]:
    """
    Construye un diccionario de similaridad entre pares de alquileres (optimizado).
    
    Solo calcula similaridades para pares que tienen potencial de ser duplicados:
    - Misma ubicación aproximada (coordenadas cercanas)
    - O títulos muy similares
    
    Args:
        df: DataFrame con las ofertas
        title_col: Nombre de la columna de título
        logger: Logger opcional
        
    Returns:
        Diccionario {(i, j): similarity} para pares similares
    """
    n = len(df)
    similarity_dict = {}
    
    if logger:
        logger.info(f"Construyendo matriz de similaridad optimizada para {n} ofertas...")
    
    # Primero, agrupar por ubicación aproximada para reducir comparaciones
    # Crear índices espaciales simples
    lat_col = 'latitud'
    lon_col = 'longitud'
    
    has_coords = lat_col in df.columns and lon_col in df.columns
    
    # Si hay coordenadas, agrupar por cuadrícula aproximada
    if has_coords:
        # Redondear coordenadas a ~100m de precisión (0.001 grados ≈ 111m)
        df = df.copy()  # Trabajar en copia para no modificar el original
        # Primero rellenar NaN, luego convertir a int
        df['_lat_grid'] = (df[lat_col] / 0.001).round().fillna(-999).astype(int)
        df['_lon_grid'] = (df[lon_col] / 0.001).round().fillna(-999).astype(int)
        
        # Comparar solo dentro de la misma cuadrícula o adyacentes
        for i in range(n):
            row1 = df.iloc[i]
            
            # Si tiene coordenadas, buscar en cuadrícula
            if pd.notna(row1.get(lat_col)) and pd.notna(row1.get(lon_col)):
                lat_grid_i = row1['_lat_grid']
                lon_grid_i = row1['_lon_grid']
                
                # Comparar con otros en cuadrícula ±1
                for j in range(i + 1, n):
                    row2 = df.iloc[j]
                    if pd.notna(row2.get(lat_col)) and pd.notna(row2.get(lon_col)):
                        lat_grid_j = row2['_lat_grid']
                        lon_grid_j = row2['_lon_grid']
                        
                        # Si están en cuadrícula cercana (misma o adyacente)
                        if abs(lat_grid_i - lat_grid_j) <= 1 and abs(lon_grid_i - lon_grid_j) <= 1:
                            similarity = calculate_combined_similarity(row1, row2, title_col)
                            if similarity >= CLUSTERING_SIMILARITY_THRESHOLD * 0.5:  # Guardar solo si es prometedor
                                similarity_dict[(i, j)] = similarity
                                similarity_dict[(j, i)] = similarity
            else:
                # Sin coordenadas: comparar por título similar
                for j in range(i + 1, n):
                    row2 = df.iloc[j]
                    # Si ambos no tienen coordenadas, comparar por título
                    if pd.isna(row2.get(lat_col)) or pd.isna(row2.get(lon_col)):
                        title_sim = lexical_similarity(
                            row1.get(title_col, ''),
                            row2.get(title_col, '')
                        )
                        if title_sim >= 70:  # Solo si título es muy similar
                            similarity = calculate_combined_similarity(row1, row2, title_col)
                            if similarity >= CLUSTERING_SIMILARITY_THRESHOLD * 0.5:
                                similarity_dict[(i, j)] = similarity
                                similarity_dict[(j, i)] = similarity
    else:
        # Sin coordenadas: comparar todos con todos (más lento pero necesario)
        if logger:
            logger.warning("No hay coordenadas disponibles, comparando todos los pares (puede ser lento)")
        
        for i in range(n):
            for j in range(i + 1, n):
                similarity = calculate_combined_similarity(df.iloc[i], df.iloc[j], title_col)
                if similarity >= CLUSTERING_SIMILARITY_THRESHOLD * 0.5:
                    similarity_dict[(i, j)] = similarity
                    similarity_dict[(j, i)] = similarity
    
    # Limpiar columnas temporales (ya se trabajó en copia, no es necesario limpiar)
    
    if logger:
        logger.info(f"Calculadas {len(similarity_dict) // 2} comparaciones de similaridad")
    
    return similarity_dict


def hierarchical_clustering_bottom_up(
    df: pd.DataFrame,
    similarity_threshold: float = CLUSTERING_SIMILARITY_THRESHOLD,
    title_col: str = 'titulo',
    source_col: Optional[str] = None,  # No usado aquí, pero se mantiene para compatibilidad
    logger=None
) -> Dict[int, List[int]]:
    """
    Implementa clustering jerárquico bottom-up.
    
    Enfoque:
    1. Inicia con cada oferta como un cluster individual
    2. Itera fusionando los clusters más similares
    3. Solo fusiona si la similaridad promedio entre clusters supera el umbral
    4. Prioriza fusiones cross-portal (entre diferentes portales)
    
    Args:
        df: DataFrame con las ofertas
        similarity_threshold: Umbral de similaridad para fusionar clusters
        title_col: Nombre de la columna de título
        source_col: Nombre de la columna de fuente/portal
        logger: Logger opcional
        
    Returns:
        Diccionario {cluster_id: [índices de ofertas]}
    """
    if logger is None:
        from prefect import get_run_logger
        logger = get_run_logger()
    
    if df.empty:
        return {}
    
    n = len(df)
    df = df.reset_index(drop=True)
    
    # Construir diccionario de similaridad optimizado
    similarity_dict = build_similarity_matrix_optimized(df, title_col, logger)
    
    # Inicializar: cada oferta es su propio cluster
    clusters = {i: [i] for i in range(n)}
    cluster_scores = {i: calculate_article_score(df.iloc[i], cluster_rows=None) for i in range(n)}
    
    # Función para calcular similaridad promedio entre dos clusters
    def cluster_similarity(cluster1: List[int], cluster2: List[int]) -> float:
        """Calcula la similaridad promedio entre dos clusters."""
        similarities = []
        for i in cluster1:
            for j in cluster2:
                # Buscar en diccionario, si no está calculado, calcularlo
                if (i, j) in similarity_dict:
                    similarities.append(similarity_dict[(i, j)])
                elif (j, i) in similarity_dict:
                    similarities.append(similarity_dict[(j, i)])
                elif i != j:
                    # Calcular on-the-fly si no está en el diccionario
                    sim = calculate_combined_similarity(df.iloc[i], df.iloc[j], title_col)
                    similarities.append(sim)
        return np.mean(similarities) if similarities else 0.0
    
    # Función para verificar si dos clusters pueden fusionarse (cross-portal preferido)
    def can_merge(_cluster1: List[int], _cluster2: List[int]) -> bool:
        """Verifica si dos clusters pueden fusionarse."""
        # Permitir todas las fusiones si superan el umbral de similaridad
        # El filtrado cross-portal se hace después en el procesamiento de clusters
        return True
    
    # Algoritmo bottom-up
    logger.info("Iniciando clustering jerárquico bottom-up...")
    iterations = 0
    max_iterations = n * n  # Límite de seguridad
    
    while iterations < max_iterations:
        iterations += 1
        best_merge = None
        best_similarity = 0.0
        
        # Buscar el par de clusters más similares
        cluster_ids = list(clusters.keys())
        for i, cid1 in enumerate(cluster_ids):
            for cid2 in cluster_ids[i+1:]:
                if cid1 not in clusters or cid2 not in clusters:
                    continue
                
                sim = cluster_similarity(clusters[cid1], clusters[cid2])
                
                # Verificar si pueden fusionarse y si superan el umbral
                if sim >= similarity_threshold and can_merge(clusters[cid1], clusters[cid2]):
                    if sim > best_similarity:
                        best_similarity = sim
                        best_merge = (cid1, cid2)
        
        # Si no hay más fusiones posibles, terminar
        if best_merge is None:
            break
        
        # Fusionar los clusters
        cid1, cid2 = best_merge
        merged_cluster = clusters[cid1] + clusters[cid2]
        
        # Calcular nuevo score del cluster fusionado
        merged_rows = [df.iloc[idx] for idx in merged_cluster]
        # Recalcular scores con contexto del cluster
        for idx in merged_cluster:
            row = df.iloc[idx]
            cluster_scores[idx] = calculate_article_score(row, cluster_rows=merged_rows)
        
        # Mantener el cluster con mejor score promedio
        avg_score1 = np.mean([cluster_scores[idx] for idx in clusters[cid1]])
        avg_score2 = np.mean([cluster_scores[idx] for idx in clusters[cid2]])
        
        if avg_score1 >= avg_score2:
            clusters[cid1] = merged_cluster
            del clusters[cid2]
            del cluster_scores[cid2]
        else:
            clusters[cid2] = merged_cluster
            del clusters[cid1]
            del cluster_scores[cid1]
        
        if iterations % 10 == 0:
            logger.info(f"Iteración {iterations}: {len(clusters)} clusters restantes")
    
    # Filtrar clusters pequeños (solo mantener los que tienen al menos 2 elementos)
    final_clusters = {
        cid: indices for cid, indices in clusters.items()
        if len(indices) >= CLUSTERING_MIN_CLUSTER_SIZE
    }
    
    logger.info(f"Clustering completado: {len(final_clusters)} clusters encontrados después de {iterations} iteraciones")
    
    return final_clusters


@task(
    name="detect_duplicates_by_clustering",
    retries=1,
    retry_delay_seconds=5,
    log_prints=True,
    tags=["deduplication", "clustering", "hierarchical", "cross_portal"]
)
def detect_duplicates_by_clustering(
    df: pd.DataFrame,
    similarity_threshold: float = CLUSTERING_SIMILARITY_THRESHOLD,
    title_col: str = 'titulo',
    source_col: Optional[str] = None,
    logger=None
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Detecta duplicados usando clustering jerárquico bottom-up con scoring.
    
    Compara ofertas usando:
    1. Similaridad lexicográfica de títulos
    2. Sistema de scoring basado en características
    3. Agrupación jerárquica bottom-up
    
    Args:
        df: DataFrame con datos transformados
        similarity_threshold: Umbral de similaridad para clustering (0-100)
        title_col: Nombre de la columna de título
        source_col: Nombre de la columna de fuente/portal
        logger: Logger opcional
        
    Returns:
        Tuple de (df_final, df_clusters_info, df_duplicates_records)
        - df_final: DataFrame con todos los registros (no se eliminan)
        - df_clusters_info: DataFrame con metadatos de clusters detectados
        - df_duplicates_records: DataFrame con los registros completos de duplicados
    """
    if logger is None:
        logger = get_run_logger()
    
    start_time = time.time()
    
    if df.empty:
        logger.warning("DataFrame vacío para detección de duplicados por clustering")
        return df, pd.DataFrame(), pd.DataFrame()
    
    # Verificar que exista la columna de título
    if title_col not in df.columns:
        logger.warning(f"Columna {title_col} no encontrada. No se pueden detectar duplicados por clustering.")
        return df, pd.DataFrame(), pd.DataFrame()
    
    df = df.copy()
    df = df.reset_index(drop=True)
    
    # Buscar columna de fuente si no se especifica
    if source_col is None:
        for col in df.columns:
            if 'source' in str(col).lower() or col == '__source_file':
                source_col = col
                break
    
    logger.info(f"Analizando {len(df)} ofertas con clustering jerárquico...")
    
    # Aplicar clustering
    clusters = hierarchical_clustering_bottom_up(
        df,
        similarity_threshold=similarity_threshold,
        title_col=title_col,
        source_col=source_col,
        logger=logger
    )
    
    # Procesar clusters y crear información de duplicados
    clusters_info = []
    duplicate_indices = set()
    
    for cluster_id, indices in clusters.items():
        if len(indices) < 2:
            continue
        
        cluster_rows = [df.iloc[idx] for idx in indices]
        
        # Calcular scores para cada elemento del cluster
        scores = []
        for idx in indices:
            row = df.iloc[idx]
            # Calcular score con contexto del cluster
            final_score = calculate_article_score(row, cluster_rows=cluster_rows)
            scores.append((idx, final_score))
        
        # Ordenar por score (mayor = más confiable)
        scores.sort(key=lambda x: x[1], reverse=True)
        
        # El elemento con mayor score es el "primario"
        primary_idx = scores[0][0]
        duplicate_indices_in_cluster = [idx for idx, _ in scores[1:]]
        
        # Verificar si es cross-portal
        is_cross_portal = False
        if source_col and source_col in df.columns:
            sources = set(df.iloc[indices][source_col].dropna().unique())
            is_cross_portal = len(sources) > 1
        
        # Solo procesar clusters cross-portal
        if not is_cross_portal:
            continue
        
        # Marcar duplicados
        for dup_idx in duplicate_indices_in_cluster:
            duplicate_indices.add(dup_idx)
            
            primary_row = df.iloc[primary_idx]
            dup_row = df.iloc[dup_idx]
            
            # Calcular similaridad entre títulos
            similarity = lexical_similarity(
                primary_row.get(title_col, ''),
                dup_row.get(title_col, '')
            )
            
            cluster_info = {
                'cluster_id': cluster_id,
                'primary_id': primary_idx,
                'duplicate_id': dup_idx,
                'similarity_score': similarity,
                'primary_score': scores[0][1],
                'duplicate_score': next((s for idx, s in scores if idx == dup_idx), 0),
                'primary_source': primary_row.get(source_col, 'unknown') if source_col else 'unknown',
                'duplicate_source': dup_row.get(source_col, 'unknown') if source_col else 'unknown',
                'is_cross_portal': is_cross_portal,
                'cluster_size': len(indices),
                'primary_titulo': primary_row.get(title_col, ''),
                'duplicate_titulo': dup_row.get(title_col, ''),
                'primary_ubicacion': primary_row.get('ubicacion', ''),
                'duplicate_ubicacion': dup_row.get('ubicacion', ''),
            }
            clusters_info.append(cluster_info)
    
    # Crear DataFrames de resultados
    df_clusters_info = pd.DataFrame(clusters_info)
    
    # Extraer registros completos de duplicados
    df_duplicates_records = pd.DataFrame()
    if duplicate_indices:
        df_duplicates_records = df[df.index.isin(duplicate_indices)].copy()
        logger.info(f"Identificados {len(df_duplicates_records)} registros duplicados cross-portal por clustering")
    
    # NO eliminar duplicados del DataFrame original
    df_final = df.copy()
    
    execution_time = time.time() - start_time
    
    logger.info(
        f"Detección de duplicados por clustering completada: "
        f"{len(df_final)} registros totales, "
        f"{len(df_clusters_info)} pares de duplicados detectados, "
        f"{len(df_duplicates_records)} registros marcados como duplicados "
        f"en {execution_time:.2f}s"
    )
    
    # Registrar en provenance tracker
    tracker = get_provenance_tracker()
    tracker.log_duplicate_detection(
        source='hierarchical_clustering',
        total_rows=len(df),
        duplicates_found=len(df_duplicates_records),
        method='hierarchical_clustering_bottom_up',
        similarity_threshold=similarity_threshold,
        execution_time=execution_time,
        cross_portal_count=len(df_clusters_info),
        duplicates_moved=len(df_duplicates_records)
    )
    
    return df_final, df_clusters_info, df_duplicates_records

