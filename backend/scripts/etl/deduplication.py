"""
Detección de duplicados por coordenadas geográficas (cross-portal).

Implementa detección de duplicados entre diferentes portales basándose en:
- Proximidad geográfica (coordenadas lat/lon)
- Distancia máxima entre coordenadas (threshold en metros)
- Comparación adicional de atributos para confirmación
"""
import pandas as pd
import numpy as np
from typing import Optional, Tuple, List, Dict
import time
from math import radians, cos, sin, asin, sqrt

from prefect import task, get_run_logger

from .config import DUPLICATE_SIMILARITY_THRESHOLD
from .provenance import get_provenance_tracker

# Umbral de distancia en metros para considerar propiedades como duplicados
DISTANCE_THRESHOLD_METERS = 50  # 50 metros de radio


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


@task(
    name="detect_duplicates_by_coordinates",
    retries=1,
    retry_delay_seconds=5,
    log_prints=True,
    tags=["deduplication", "coordinates", "cross_portal"]
)
def detect_duplicates_by_coordinates(
    df: pd.DataFrame,
    distance_threshold: float = DISTANCE_THRESHOLD_METERS,
    lat_col: str = 'latitud',
    lon_col: str = 'longitud',
    logger=None
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Detecta duplicados CROSS-PORTAL basándose en coordenadas EXACTAMENTE iguales.
    
    Compara todas las propiedades entre sí y las marca como duplicadas si:
    1. Tienen coordenadas válidas
    2. Las coordenadas son EXACTAMENTE iguales (lat1 == lat2 AND lon1 == lon2)
    3. Son de DIFERENTES portales (cross-portal) - REQUISITO OBLIGATORIO
    
    NOTA: Solo detecta y procesa duplicados cross-portal (entre diferentes portales).
    Los duplicados dentro del mismo portal se ignoran completamente.
    Solo se consideran duplicados aquellos con coordenadas idénticas,
    no por proximidad dentro de un umbral de distancia.
    
    Args:
        df: DataFrame con datos transformados (debe tener latitud y longitud)
        distance_threshold: NO USADO - se mantiene por compatibilidad pero no se aplica
        lat_col: Nombre de la columna de latitud
        lon_col: Nombre de la columna de longitud
        logger: Logger opcional
    
    Returns:
        Tuple de (df_final, df_duplicados_con_info, df_duplicados_records)
        - df_final: DataFrame con todos los registros (no se eliminan)
        - df_duplicados_con_info: DataFrame con metadatos de duplicados detectados
        - df_duplicados_records: DataFrame con los registros completos de duplicados cross-portal
    """
    if logger is None:
        logger = get_run_logger()
    
    start_time = time.time()
    
    if df.empty:
        logger.warning("DataFrame vacío para detección de duplicados por coordenadas")
        return df, pd.DataFrame(), pd.DataFrame()
    
    # Verificar que existan las columnas necesarias
    if lat_col not in df.columns or lon_col not in df.columns:
        logger.warning(f"Columnas {lat_col} o {lon_col} no encontradas. No se pueden detectar duplicados por coordenadas.")
        return df, pd.DataFrame(), pd.DataFrame()
    
    df = df.copy()
    
    # Separar registros con y sin coordenadas válidas
    mask_valid_coords = (
        df[lat_col].notna() & 
        df[lon_col].notna() &
        (df[lat_col] != 0) &
        (df[lon_col] != 0)
    )
    
    df_with_coords = df[mask_valid_coords].copy()
    df_no_coords = df[~mask_valid_coords].copy()
    
    if df_with_coords.empty:
        logger.warning("No hay registros con coordenadas válidas para detectar duplicados")
        return df, pd.DataFrame(), pd.DataFrame()
    
    logger.info(f"Analizando {len(df_with_coords)} registros con coordenadas válidas de {len(df)} totales")
    
    # Almacenar información de duplicados
    duplicates_groups = []
    removed_indices = set()
    duplicate_records_indices = set()  # Índices de registros duplicados cross-portal a mover
    
    # Obtener columnas de fuente para identificar portales (verificar nombres normalizados)
    source_col = None
    for col in df_with_coords.columns:
        if 'source_file' in str(col).lower() or col == '__source_file':
            source_col = col
            break
    
    logger.info("Iniciando comparación de coordenadas EXACTAS (no por proximidad)...")
    
    # Usar índices numéricos del DataFrame para acceso consistente
    df_with_coords = df_with_coords.reset_index(drop=True)
    
    # Crear índice único para cada registro
    df_with_coords['__temp_id'] = range(len(df_with_coords))
    
    # Asegurar que las coordenadas sean numéricas
    df_with_coords[lat_col] = pd.to_numeric(df_with_coords[lat_col], errors='coerce')
    df_with_coords[lon_col] = pd.to_numeric(df_with_coords[lon_col], errors='coerce')
    
    # Eliminar filas que no se pudieron convertir a numérico
    df_with_coords = df_with_coords[
        df_with_coords[lat_col].notna() & 
        df_with_coords[lon_col].notna() &
        (df_with_coords[lat_col] != 0) &
        (df_with_coords[lon_col] != 0)
    ].copy()
    
    # Agrupar por coordenadas EXACTAMENTE iguales (sin redondeo)
    # Usar groupby directamente en las coordenadas sin redondear
    # Solo se consideran duplicados aquellos con coordenadas completamente idénticas
    coord_groups = df_with_coords.groupby([lat_col, lon_col], as_index=False)
    
    # Comparar cada grupo de coordenadas iguales
    for (lat_val, lon_val), group_df in coord_groups:
        if len(group_df) > 1:
            # Hay múltiples registros con las mismas coordenadas exactas
            group_indices = group_df.index.tolist()
            primary_idx = group_indices[0]
            duplicates_indices = group_indices[1:]
            
            # Obtener filas del grupo
            primary_row = df_with_coords.iloc[primary_idx]
            
            for dup_idx in duplicates_indices:
                dup_row = df_with_coords.iloc[dup_idx]
                
                # Verificar si son de diferentes portales (cross-portal)
                is_cross_portal = False
                if source_col:
                    source_i = primary_row.get(source_col, 'unknown')
                    source_j = dup_row.get(source_col, 'unknown')
                    is_cross_portal = (source_i != source_j)
                
                # SOLO procesar duplicados cross-portal - ignorar los del mismo portal
                if not is_cross_portal:
                    continue  # Ignorar duplicados del mismo portal
                
                # Marcar duplicados cross-portal para moverlos a tabla separada
                if dup_idx not in removed_indices:
                    removed_indices.add(dup_idx)
                    duplicate_records_indices.add(dup_idx)  # Marcar para mover
                
                # Calcular distancia (debería ser 0 o muy cercana a 0)
                distance = haversine_distance(
                    primary_row[lat_col], primary_row[lon_col],
                    dup_row[lat_col], dup_row[lon_col]
                )
                
                # Crear registro de duplicado cross-portal
                dup_record = {
                    'primary_id': primary_row.get('__temp_id', primary_idx),
                    'duplicate_id': dup_row.get('__temp_id', dup_idx),
                    'distance_meters': distance,
                    'primary_source': primary_row.get(source_col, 'unknown') if source_col else 'unknown',
                    'duplicate_source': dup_row.get(source_col, 'unknown') if source_col else 'unknown',
                    'is_cross_portal': True,  # Siempre True ya que solo procesamos cross-portal
                    'primary_titulo': primary_row.get('titulo', ''),
                    'duplicate_titulo': dup_row.get('titulo', ''),
                    'primary_ubicacion': primary_row.get('ubicacion', ''),
                    'duplicate_ubicacion': dup_row.get('ubicacion', ''),
                    'primary_lat': primary_row[lat_col],
                    'primary_lon': primary_row[lon_col],
                    'duplicate_lat': dup_row[lat_col],
                    'duplicate_lon': dup_row[lon_col],
                }
                duplicates_groups.append(dup_record)
    
    
    # Crear DataFrame con información de duplicados (metadatos)
    df_duplicates_info = pd.DataFrame(duplicates_groups)
    
    # Extraer registros completos de duplicados cross-portal para mover a tabla separada
    df_duplicates_records = pd.DataFrame()
    if duplicate_records_indices:
        df_duplicates_records = df_with_coords[df_with_coords.index.isin(duplicate_records_indices)].copy()
        df_duplicates_records = df_duplicates_records.drop(columns=['__temp_id'], errors='ignore')
        logger.info(f"Identificados {len(df_duplicates_records)} registros duplicados cross-portal para mover a tabla separada")
    
    # NO eliminar duplicados del DataFrame original - mantener todos los registros
    # Solo remover la columna temporal
    df_with_coords = df_with_coords.drop(columns=['__temp_id'], errors='ignore')
    
    # Combinar todos los registros (incluyendo duplicados)
    df_final = pd.concat([df_with_coords, df_no_coords], ignore_index=True)
    
    execution_time = time.time() - start_time
    
    total_duplicates = len(removed_indices)  # Todos son cross-portal
    cross_portal_count = total_duplicates  # Simplificado ya que solo procesamos cross-portal
    
    logger.info(
        f"Detección de duplicados CROSS-PORTAL por coordenadas EXACTAS completada: "
        f"{len(df_final)} registros totales de {len(df)} originales "
        f"({total_duplicates} duplicados cross-portal detectados para mover) "
        f"en {execution_time:.2f}s"
    )
    
    # Registrar en provenance tracker
    tracker = get_provenance_tracker()
    tracker.log_duplicate_detection(
        source='cross_portal_coordinates',
        total_rows=len(df),
        duplicates_found=total_duplicates,
        method='exact_coordinates',
        similarity_threshold=0.0,  # Coordenadas exactas = distancia 0
        execution_time=execution_time,
        cross_portal_count=cross_portal_count,
        duplicates_moved=len(df_duplicates_records)
    )
    
    return df_final, df_duplicates_info, df_duplicates_records


@task(
    name="save_duplicates_to_table",
    retries=1,
    retry_delay_seconds=5,
    log_prints=True,
    tags=["deduplication", "database"]
)
def save_duplicates_to_table(
    df_duplicates: pd.DataFrame,
    engine_url: str,
    table_name: str = 'duplicates_detected',
    logger=None
) -> bool:
    """
    Guarda información de duplicados detectados en una tabla separada.
    
    Args:
        df_duplicates: DataFrame con información de duplicados
        engine_url: URL de conexión a la base de datos
        table_name: Nombre de la tabla donde guardar
        logger: Logger opcional
    
    Returns:
        True si se guardó exitosamente
    """
    if logger is None:
        logger = get_run_logger()
    
    if df_duplicates.empty:
        logger.info("No hay duplicados para guardar")
        return True
    
    try:
        from sqlalchemy import create_engine
        engine = create_engine(engine_url)
        
        # Agregar timestamp
        from datetime import datetime, timezone
        df_duplicates['detected_at'] = datetime.now(timezone.utc).isoformat()
        
        # Guardar en tabla
        df_duplicates.to_sql(table_name, engine, if_exists='replace', index=False)
        
        logger.info(f"Guardados {len(df_duplicates)} registros de duplicados en tabla {table_name}")
        return True
    
    except Exception as e:
        logger.error(f"Error guardando duplicados en tabla {table_name}: {e}")
        return False


@task(
    name="save_duplicate_records_to_table",
    retries=1,
    retry_delay_seconds=5,
    log_prints=True,
    tags=["deduplication", "database", "move_duplicates"]
)
def save_duplicate_records_to_table(
    df_duplicates: pd.DataFrame,
    engine_url: str,
    table_name: str = 'duplicates_moved',
    logger=None
) -> bool:
    """
    Guarda los registros completos de duplicados cross-portal en una tabla separada.
    Estos registros se mueven de transformed_listings a esta tabla.
    
    Args:
        df_duplicates: DataFrame con los registros completos de duplicados
        engine_url: URL de conexión a la base de datos
        table_name: Nombre de la tabla donde guardar (default: 'duplicates_moved')
        logger: Logger opcional
    
    Returns:
        True si se guardó exitosamente
    """
    if logger is None:
        logger = get_run_logger()
    
    if df_duplicates.empty:
        logger.info("No hay registros duplicados para mover")
        return True
    
    try:
        from sqlalchemy import create_engine
        from scripts.etl.utils import normalize_text
        
        engine = create_engine(engine_url)
        
        # Normalizar columnas
        df_duplicates = df_duplicates.copy()
        df_duplicates.columns = [normalize_text(str(c)) for c in df_duplicates.columns]
        
        # Agregar timestamp y motivo
        from datetime import datetime, timezone
        df_duplicates['moved_at'] = datetime.now(timezone.utc).isoformat()
        df_duplicates['reason'] = 'duplicate_cross_portal_exact_coordinates'
        
        # Guardar en tabla (reemplazar contenido previo)
        df_duplicates.to_sql(table_name, engine, if_exists='replace', index=False)
        
        logger.info(f"Movidos {len(df_duplicates)} registros duplicados cross-portal a tabla {table_name}")
        return True
    
    except Exception as e:
        logger.error(f"Error moviendo duplicados a tabla {table_name}: {e}")
        return False
