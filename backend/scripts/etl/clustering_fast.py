"""
Clustering rápido usando DBSCAN para detección de alquileres repetidos.

DBSCAN es mucho más rápido que clustering jerárquico:
- Complejidad: O(n log n) vs O(n²)
- No requiere calcular todas las distancias de antemano
- Ideal para encontrar clusters de densidad variable (duplicados)
"""
import pandas as pd
import numpy as np
from typing import Optional, Tuple, List, Dict
import time
from rapidfuzz import fuzz
from math import radians, cos, sin, asin, sqrt

from prefect import task, get_run_logger

from .config import DUPLICATE_SIMILARITY_THRESHOLD
from .provenance import get_provenance_tracker
from .utils import normalize_text, normalize_for_match

try:
    from sklearn.cluster import DBSCAN
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics.pairwise import cosine_similarity
    HAVE_SKLEARN = True
except ImportError:
    HAVE_SKLEARN = False

# Configuración
DBSCAN_EPS = 0.3  # Distancia máxima entre puntos en un cluster (ajustable)
DBSCAN_MIN_SAMPLES = 2  # Mínimo de puntos para formar cluster
DISTANCE_THRESHOLD_METERS = 100  # Distancia máxima en metros para misma ubicación
PRICE_SIMILARITY_THRESHOLD = 0.15  # 15% diferencia máxima en precio


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calcula distancia entre dos puntos geográficos en metros."""
    if pd.isna(lat1) or pd.isna(lon1) or pd.isna(lat2) or pd.isna(lon2):
        return float('inf')
    
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    r = 6371000  # Radio de la Tierra en metros
    return c * r


def normalize_title_for_clustering(title: str) -> str:
    """Normaliza un título para comparación."""
    if pd.isna(title) or not isinstance(title, str):
        return ""
    normalized = normalize_for_match(title)
    return ' '.join(normalized.split()).lower().strip()


def lexical_similarity(title1: str, title2: str) -> float:
    """Calcula similaridad lexicográfica entre dos títulos (0-100)."""
    norm1 = normalize_title_for_clustering(title1)
    norm2 = normalize_title_for_clustering(title2)
    
    if not norm1 or not norm2:
        return 0.0
    
    ratio = fuzz.ratio(norm1, norm2)
    token_sort = fuzz.token_sort_ratio(norm1, norm2)
    token_set = fuzz.token_set_ratio(norm1, norm2)
    
    return (ratio * 0.3 + token_sort * 0.3 + token_set * 0.4)


def create_feature_vector(row: pd.Series, title_col: str = 'titulo') -> np.ndarray:
    """
    Crea un vector de características para un alquiler.
    
    Características:
    1. Similaridad de título (normalizada)
    2. Coordenadas (lat, lon normalizadas)
    3. Precio normalizado
    4. Dormitorios normalizados
    5. Baños normalizados
    6. Superficie normalizada
    """
    features = []
    
    # 1. Título: usar hash del título normalizado como feature
    title = str(row.get(title_col, ''))
    title_norm = normalize_title_for_clustering(title)
    # Usar hash simple para representar título
    title_hash = hash(title_norm) % 10000 / 10000.0  # Normalizar a 0-1
    features.append(title_hash)
    
    # 2. Coordenadas (normalizadas)
    lat = row.get('latitud', 0)
    lon = row.get('longitud', 0)
    if pd.notna(lat) and pd.notna(lon) and lat != 0 and lon != 0:
        # Normalizar coordenadas de Montevideo aproximadamente
        # Lat: -34.9 a -34.7, Lon: -56.3 a -56.0
        lat_norm = (lat + 34.9) / 0.2  # Normalizar a 0-1
        lon_norm = (lon + 56.3) / 0.3  # Normalizar a 0-1
        features.extend([lat_norm, lon_norm])
    else:
        features.extend([0.5, 0.5])  # Valor por defecto
    
    # 3. Precio normalizado
    precio = row.get('precio_base_uyu', 0)
    try:
        precio = float(precio) if pd.notna(precio) else 0
        if precio > 0:
            # Normalizar precios típicos de alquiler (5000-50000 UYU)
            precio_norm = min(1.0, max(0.0, (precio - 5000) / 45000))
            features.append(precio_norm)
        else:
            features.append(0.5)
    except (ValueError, TypeError):
        features.append(0.5)
    
    # 4. Dormitorios normalizados
    dorms = row.get('dorms') or row.get('dorms_imputado')
    try:
        if pd.notna(dorms):
            dorms = float(dorms)
            dorms_norm = min(1.0, dorms / 5.0)  # Máx 5 dormitorios
            features.append(dorms_norm)
        else:
            features.append(0.5)
    except (ValueError, TypeError):
        features.append(0.5)
    
    # 5. Baños normalizados
    banos = row.get('banos', 0)
    try:
        if pd.notna(banos):
            banos = float(banos)
            banos_norm = min(1.0, banos / 4.0)  # Máx 4 baños
            features.append(banos_norm)
        else:
            features.append(0.5)
    except (ValueError, TypeError):
        features.append(0.5)
    
    # 6. Superficie normalizada
    superficie = row.get('superficie_m2', 0)
    try:
        superficie = float(superficie) if pd.notna(superficie) else 0
        if superficie > 0:
            superficie_norm = min(1.0, superficie / 200.0)  # Máx 200 m²
            features.append(superficie_norm)
        else:
            features.append(0.5)
    except (ValueError, TypeError):
        features.append(0.5)
    
    return np.array(features)


def custom_distance(row1_vec: np.ndarray, row2_vec: np.ndarray, 
                   row1: pd.Series, row2: pd.Series) -> float:
    """
    Calcula distancia personalizada entre dos alquileres.
    
    Combina distancia euclidiana de features con distancias específicas:
    - Distancia geográfica (si hay coordenadas)
    - Diferencia de precio
    - Similaridad de título
    """
    # Distancia euclidiana de features vectorizadas
    euclidean_dist = np.linalg.norm(row1_vec - row2_vec)
    
    # Ajustar con distancias específicas
    adjustments = []
    
    # 1. Distancia geográfica (peso alto)
    lat1 = row1.get('latitud')
    lon1 = row1.get('longitud')
    lat2 = row2.get('latitud')
    lon2 = row2.get('longitud')
    
    if all(pd.notna(x) and x != 0 for x in [lat1, lon1, lat2, lon2]):
        geo_dist = haversine_distance(lat1, lon1, lat2, lon2)
        # Normalizar a 0-1 (100m = 1.0)
        geo_dist_norm = min(1.0, geo_dist / DISTANCE_THRESHOLD_METERS)
        adjustments.append(geo_dist_norm * 0.4)  # Peso 40%
    else:
        adjustments.append(0.5)  # Sin coordenadas = distancia media
    
    # 2. Diferencia de precio (peso medio)
    precio1 = row1.get('precio_base_uyu', 0)
    precio2 = row2.get('precio_base_uyu', 0)
    if pd.notna(precio1) and pd.notna(precio2) and precio1 > 0 and precio2 > 0:
        price_diff = abs(precio1 - precio2) / max(precio1, precio2)
        adjustments.append(min(1.0, price_diff / PRICE_SIMILARITY_THRESHOLD) * 0.3)
    else:
        adjustments.append(0.5)
    
    # 3. Similaridad de título (peso bajo, ya está en vector)
    title_sim = lexical_similarity(
        row1.get('titulo', ''),
        row2.get('titulo', '')
    )
    title_dist = 1.0 - (title_sim / 100.0)  # Convertir a distancia
    adjustments.append(title_dist * 0.3)
    
    # Combinar distancias
    adjusted_dist = euclidean_dist * 0.5 + np.mean(adjustments) * 0.5
    
    return adjusted_dist


def dbscan_clustering_fast(
    df: pd.DataFrame,
    eps: float = DBSCAN_EPS,
    min_samples: int = DBSCAN_MIN_SAMPLES,
    title_col: str = 'titulo',
    logger=None
) -> Dict[int, List[int]]:
    """
    Aplica DBSCAN para clustering rápido de alquileres.
    
    Args:
        df: DataFrame con las ofertas
        eps: Distancia máxima entre puntos en un cluster
        min_samples: Mínimo de puntos para formar cluster
        title_col: Nombre de la columna de título
        logger: Logger opcional
        
    Returns:
        Diccionario {cluster_id: [índices de ofertas]}
    """
    if not HAVE_SKLEARN:
        raise ImportError("scikit-learn no está instalado. Instala con: pip install scikit-learn")
    
    if logger is None:
        from prefect import get_run_logger
        logger = get_run_logger()
    
    if df.empty:
        return {}
    
    n = len(df)
    df = df.reset_index(drop=True)
    
    logger.info(f"Aplicando DBSCAN a {n} ofertas (eps={eps}, min_samples={min_samples})...")
    
    # Crear matriz de features
    logger.info("Creando vectores de características...")
    feature_vectors = []
    for idx in range(n):
        vec = create_feature_vector(df.iloc[idx], title_col)
        feature_vectors.append(vec)
    
    feature_matrix = np.array(feature_vectors)
    
    # Normalizar features
    scaler = StandardScaler()
    feature_matrix_scaled = scaler.fit_transform(feature_matrix)
    
    # Calcular matriz de distancias usando métrica personalizada
    # Para DBSCAN, necesitamos una matriz de distancias o usar métrica precomputed
    # Opción más rápida: usar distancia euclidiana normalizada
    logger.info("Calculando distancias...")
    
    # Usar DBSCAN con métrica euclidiana (más rápido)
    # Para mejor precisión, podríamos usar métrica personalizada pero es más lento
    dbscan = DBSCAN(eps=eps, min_samples=min_samples, metric='euclidean', n_jobs=-1)
    cluster_labels = dbscan.fit_predict(feature_matrix_scaled)
    
    # Organizar clusters
    clusters = {}
    for idx, label in enumerate(cluster_labels):
        if label != -1:  # -1 es ruido (no asignado a cluster)
            if label not in clusters:
                clusters[label] = []
            clusters[label].append(idx)
    
    # Filtrar clusters pequeños
    final_clusters = {
        cid: indices for cid, indices in clusters.items()
        if len(indices) >= min_samples
    }
    
    noise_count = sum(1 for label in cluster_labels if label == -1)
    logger.info(f"DBSCAN completado: {len(final_clusters)} clusters, {noise_count} puntos de ruido")
    
    return final_clusters


def calculate_article_score(row: pd.Series, cluster_rows: Optional[List[pd.Series]] = None) -> float:
    """Calcula puntaje de confiabilidad de un alquiler (0-100)."""
    # Completitud de datos
    campos_importantes = ['titulo', 'ubicacion', 'precio_base_uyu', 'dorms', 'banos', 'superficie_m2']
    campos_presentes = sum(1 for campo in campos_importantes 
                         if campo in row.index and pd.notna(row.get(campo)))
    completitud = (campos_presentes / len(campos_importantes)) * 100
    
    # Ubicación precisa
    has_coords = (pd.notna(row.get('latitud')) and row.get('latitud') != 0 and
                  pd.notna(row.get('longitud')) and row.get('longitud') != 0)
    ubicacion_score = 100.0 if has_coords else (50.0 if pd.notna(row.get('ubicacion')) else 0.0)
    
    # Características completas
    caracteristicas = ['dorms', 'dorms_imputado', 'banos', 'superficie_m2']
    presentes = sum(1 for car in caracteristicas 
                   if car in row.index and pd.notna(row.get(car)))
    caracteristicas_score = (presentes / len(caracteristicas)) * 100
    
    # Score combinado
    score = (completitud * 0.25 + ubicacion_score * 0.30 + caracteristicas_score * 0.20 + 50.0 * 0.25)
    
    return score


@task(
    name="detect_duplicates_by_dbscan",
    retries=1,
    retry_delay_seconds=5,
    log_prints=True,
    tags=["deduplication", "clustering", "dbscan", "fast", "cross_portal"]
)
def detect_duplicates_by_dbscan(
    df: pd.DataFrame,
    eps: float = DBSCAN_EPS,
    min_samples: int = DBSCAN_MIN_SAMPLES,
    title_col: str = 'titulo',
    source_col: Optional[str] = None,
    logger=None
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Detecta duplicados usando DBSCAN (método rápido).
    
    DBSCAN es mucho más rápido que clustering jerárquico:
    - Complejidad: O(n log n) vs O(n²)
    - No requiere calcular todas las distancias de antemano
    - Ideal para encontrar clusters de densidad variable
    
    Args:
        df: DataFrame con datos transformados
        eps: Distancia máxima entre puntos en un cluster (default: 0.3)
        min_samples: Mínimo de puntos para formar cluster (default: 2)
        title_col: Nombre de la columna de título
        source_col: Nombre de la columna de fuente/portal
        logger: Logger opcional
        
    Returns:
        Tuple de (df_final, df_clusters_info, df_duplicates_records)
    """
    if logger is None:
        logger = get_run_logger()
    
    start_time = time.time()
    
    if not HAVE_SKLEARN:
        logger.error("scikit-learn no está instalado. Instala con: pip install scikit-learn")
        return df, pd.DataFrame(), pd.DataFrame()
    
    if df.empty:
        logger.warning("DataFrame vacío para detección de duplicados por DBSCAN")
        return df, pd.DataFrame(), pd.DataFrame()
    
    if title_col not in df.columns:
        logger.warning(f"Columna {title_col} no encontrada.")
        return df, pd.DataFrame(), pd.DataFrame()
    
    df = df.copy()
    df = df.reset_index(drop=True)
    
    # Buscar columna de fuente
    if source_col is None:
        for col in df.columns:
            if 'source' in str(col).lower() or col == '__source_file':
                source_col = col
                break
    
    logger.info(f"Analizando {len(df)} ofertas con DBSCAN (método rápido)...")
    
    # Aplicar DBSCAN
    clusters = dbscan_clustering_fast(
        df,
        eps=eps,
        min_samples=min_samples,
        title_col=title_col,
        logger=logger
    )
    
    # Procesar clusters
    clusters_info = []
    duplicate_indices = set()
    
    for cluster_id, indices in clusters.items():
        if len(indices) < 2:
            continue
        
        cluster_rows = [df.iloc[idx] for idx in indices]
        
        # Calcular scores
        scores = []
        for idx in indices:
            row = df.iloc[idx]
            score = calculate_article_score(row, cluster_rows)
            scores.append((idx, score))
        
        scores.sort(key=lambda x: x[1], reverse=True)
        
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
    
    # Crear DataFrames
    df_clusters_info = pd.DataFrame(clusters_info)
    
    df_duplicates_records = pd.DataFrame()
    if duplicate_indices:
        df_duplicates_records = df[df.index.isin(duplicate_indices)].copy()
        logger.info(f"Identificados {len(df_duplicates_records)} registros duplicados cross-portal por DBSCAN")
    
    df_final = df.copy()
    
    execution_time = time.time() - start_time
    
    logger.info(
        f"Detección de duplicados por DBSCAN completada: "
        f"{len(df_final)} registros totales, "
        f"{len(df_clusters_info)} pares de duplicados detectados, "
        f"{len(df_duplicates_records)} registros marcados como duplicados "
        f"en {execution_time:.2f}s"
    )
    
    # Registrar en provenance tracker
    tracker = get_provenance_tracker()
    tracker.log_duplicate_detection(
        source='dbscan_clustering',
        total_rows=len(df),
        duplicates_found=len(df_duplicates_records),
        method='dbscan_fast',
        similarity_threshold=eps,
        execution_time=execution_time,
        cross_portal_count=len(df_clusters_info),
        duplicates_moved=len(df_duplicates_records)
    )
    
    return df_final, df_clusters_info, df_duplicates_records

