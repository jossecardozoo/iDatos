"""
Funciones de carga de datos: CSV y SQL.

Convertidas en tasks de Prefect con trazabilidad completa.
"""
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone
from sqlalchemy import create_engine, inspect, text
from typing import List, Optional
import time

from prefect import task, get_run_logger

from .utils import normalize_text
from .config import SQLITE_PATH, RAW_DATA_DIR, PROCESSED_DATA_DIR
from .provenance import get_provenance_tracker, track_data_hash


def read_csv_header(path: Path) -> List[str]:
    """Lee solo el encabezado de un CSV de forma robusta."""
    try:
        df = pd.read_csv(path, nrows=0, dtype=str, encoding='utf-8')
    except Exception:
        df = pd.read_csv(path, nrows=0, dtype=str, encoding='latin-1')
    return list(df.columns)


@task(
    name="load_csv",
    retries=2,
    retry_delay_seconds=5,
    log_prints=True,
    tags=["extract", "csv"]
)
def load_csv(path: Path) -> pd.DataFrame:
    """
    Task de Prefect para cargar un CSV con manejo de encoding y trazabilidad.
    
    Args:
        path: Ruta al archivo CSV
        
    Returns:
        DataFrame con datos cargados y metadata de procedencia
    """
    logger = get_run_logger()
    start_time = time.time()
    
    logger.info(f"Cargando CSV: {path}")
    
    # Intentar cargar con diferentes encodings
    try:
        df = pd.read_csv(path, dtype=str, encoding='utf-8')
        encoding_used = 'utf-8'
    except Exception as e1:
        try:
            df = pd.read_csv(path, dtype=str, encoding='latin-1')
            encoding_used = 'latin-1'
            logger.warning(f"Fallback a encoding latin-1 para {path}")
        except Exception as e2:
            logger.error(f"Error cargando CSV {path}: {e1}, {e2}")
            raise
    
    # Agregar metadata de procedencia
    df['__source_file'] = path.name
    df['__source_path'] = str(path)
    df['__loaded_at'] = datetime.now(timezone.utc).isoformat()
    df['__encoding_used'] = encoding_used
    
    execution_time = time.time() - start_time
    rows_count = len(df)
    columns_count = len(df.columns)
    
    # Registrar en provenance tracker
    tracker = get_provenance_tracker()
    tracker.log_task(
        task_name="load_csv",
        input_data={
            'file_path': str(path),
            'file_size_bytes': path.stat().st_size if path.exists() else 0,
        },
        output_data={
            'rows': rows_count,
            'columns': columns_count,
            'data_hash': track_data_hash(df),
        },
        execution_time=execution_time,
        encoding=encoding_used
    )
    
    logger.info(f"CSV cargado: {rows_count} filas, {columns_count} columnas en {execution_time:.2f}s")
    
    return df


@task(
    name="create_canonical_tables",
    log_prints=True,
    tags=["setup", "database"]
)
def create_canonical_tables(engine, csv_paths: List[Path], transform_func=None):
    """
    Task de Prefect para crear tablas canónicas vacías.
    
    Args:
        engine: SQLAlchemy engine
        csv_paths: Lista de paths a CSVs para inferir esquema
        transform_func: Función opcional para inferir esquema transformado
    """
    logger = get_run_logger()
    logger.info("Creando tablas canónicas...")
    
    # Unión de columnas raw
    raw_cols = []
    for p in csv_paths:
        try:
            cols = read_csv_header(p)
        except Exception as e:
            logger.warning(f"No se pudo leer header de {p}: {e}")
            cols = []
        for c in cols:
            nc = normalize_text(str(c))
            if nc not in raw_cols:
                raw_cols.append(nc)

    # Asegurar columnas de metadata
    for extra in ['__source_file', '__source_path', '__loaded_at', '__encoding_used']:
        if extra not in raw_cols:
            raw_cols.append(extra)

    # Crear tabla raw vacía
    df_empty_raw = pd.DataFrame(columns=raw_cols)
    df_empty_raw.to_sql('raw_listings', engine, if_exists='replace', index=False)
    logger.info(f"Tabla raw_listings creada con {len(raw_cols)} columnas")

    # Inferir esquema transformado
    df_for_transform = pd.DataFrame(columns=raw_cols)
    if transform_func:
        try:
            df_transformed_sample = transform_func(df_for_transform)
            trans_cols = [normalize_text(str(c)) for c in df_transformed_sample.columns.tolist()]
        except Exception as e:
            logger.warning(f"Error inferiendo esquema transformado: {e}")
            trans_cols = ['url', 'titulo', 'ubicacion', 'precio_moneda', 'precio_valor', 'imagen_url', 'fuente']
    else:
        trans_cols = ['url', 'titulo', 'ubicacion', 'precio_moneda', 'precio_valor', 'imagen_url', 'fuente']

    # Asegurar columnas únicas preservando orden
    seen = set()
    trans_cols_unique = [x for x in trans_cols if not (x in seen or seen.add(x))]
    df_empty_trans = pd.DataFrame(columns=trans_cols_unique)
    df_empty_trans.to_sql('transformed_listings', engine, if_exists='replace', index=False)
    logger.info(f"Tabla transformed_listings creada con {len(trans_cols_unique)} columnas")


@task(
    name="write_raw_to_sql",
    retries=2,
    retry_delay_seconds=5,
    log_prints=True,
    tags=["load", "database", "raw"]
)
def write_raw_to_sql(df: pd.DataFrame, engine_url: str, logger=None) -> bool:
    """
    Task de Prefect para escribir DataFrame a la tabla raw_listings.
    
    Args:
        df: DataFrame a escribir
        engine_url: URL de conexión a la base de datos
        logger: Logger opcional (si no se usa como task)
        
    Returns:
        True si se escribió exitosamente
    """
    if logger is None:
        logger = get_run_logger()
    
    start_time = time.time()
    rows_before = len(df)
    data_hash_before = track_data_hash(df)
    
    logger.info(f"Escribiendo {rows_before} filas en tabla raw_listings")
    
    engine = create_engine(engine_url)
    inspector = None
    try:
        inspector = inspect(engine)
    except Exception:
        inspector = None

    if inspector is None or not inspector.has_table('raw_listings'):
        if logger:
            logger.info('Tabla raw_listings no existe: creando con esquema del DataFrame')
        df.columns = [normalize_text(str(c)) for c in df.columns]
        df.to_sql('raw_listings', engine, if_exists='replace', index=False)
        execution_time = time.time() - start_time
        
        # Registrar en provenance
        tracker = get_provenance_tracker()
        tracker.log_task(
            task_name="write_raw_to_sql",
            input_data={'rows': rows_before, 'data_hash': data_hash_before},
            output_data={'rows_written': rows_before, 'action': 'created_table'},
            execution_time=execution_time
        )
        
        return True

    # Manejo de esquema dinámico (código existente)
    with engine.connect() as conn:
        try:
            res = conn.execute(text("PRAGMA table_info('raw_listings')"))
            existing_cols = [row[1] for row in res.fetchall()]
        except Exception:
            existing_df = pd.read_sql('SELECT * FROM raw_listings LIMIT 0', conn)
            existing_cols = existing_df.columns.tolist()

        lower_existing = {c.lower(): c for c in existing_cols}
        new_cols = []
        for c in df.columns:
            nc = normalize_text(str(c))
            mapped = lower_existing.get(nc.lower())
            new_cols.append(mapped if mapped is not None else nc)
        df.columns = new_cols

        lower_cols = [c.lower() for c in df.columns]
        if len(lower_cols) != len(set(lower_cols)):
            if logger:
                logger.info('Columnas duplicadas detectadas. Consolidando...')
            df.columns = lower_cols
            df = df.groupby(level=0, axis=1).first()
            df.columns = [lower_existing.get(c, c) for c in df.columns]

        missing = [c for c in df.columns if c not in existing_cols]
        if missing and logger:
            logger.info(f"Columnas faltantes: {missing}. Agregando...")
        for c in missing:
            try:
                conn.execute(text(f'ALTER TABLE raw_listings ADD COLUMN "{c}" TEXT'))
                if logger:
                    logger.info(f'Columna agregada: {c}')
            except Exception as e:
                if logger:
                    logger.error(f'No se pudo agregar columna {c}: {e}')

        try:
            res = conn.execute(text("PRAGMA table_info('raw_listings')"))
            existing_cols = [row[1] for row in res.fetchall()]
        except Exception:
            existing_df = pd.read_sql('SELECT * FROM raw_listings LIMIT 0', conn)
            existing_cols = existing_df.columns.tolist()

    for c in existing_cols:
        if c not in df.columns:
            df[c] = None

    df = df.reindex(columns=existing_cols + [c for c in df.columns if c not in existing_cols])

    try:
        df.to_sql('raw_listings', engine, if_exists='append', index=False)
        execution_time = time.time() - start_time
        
        # Registrar en provenance
        tracker = get_provenance_tracker()
        tracker.log_task(
            task_name="write_raw_to_sql",
            input_data={'rows': rows_before, 'data_hash': data_hash_before},
            output_data={'rows_written': rows_before, 'columns_added': missing, 'action': 'append'},
            execution_time=execution_time
        )
        
        return True
    except Exception as e:
        if logger:
            logger.error(f'Error escribiendo a raw_listings: {e}')
        raise


@task(
    name="write_transformed_to_sql",
    retries=2,
    retry_delay_seconds=5,
    log_prints=True,
    tags=["load", "database", "transformed"]
)
def write_transformed_to_sql(df: pd.DataFrame, engine_url: str, logger=None) -> bool:
    """
    Task de Prefect para escribir DataFrame a la tabla transformed_listings.
    
    Args:
        df: DataFrame transformado a escribir
        engine_url: URL de conexión a la base de datos
        logger: Logger opcional
        
    Returns:
        True si se escribió exitosamente
    """
    if logger is None:
        logger = get_run_logger()
    
    start_time = time.time()
    rows_before = len(df)
    data_hash_before = track_data_hash(df)
    
    logger.info(f"Escribiendo {rows_before} filas en tabla transformed_listings")
    
    engine = create_engine(engine_url)
    inspector = None
    try:
        inspector = inspect(engine)
    except Exception:
        inspector = None

    df.columns = [normalize_text(str(c)) for c in df.columns]

    if inspector is None or not inspector.has_table('transformed_listings'):
        if logger:
            logger.info('Tabla transformed_listings no existe: creando con esquema del DataFrame')
        df.to_sql('transformed_listings', engine, if_exists='replace', index=False)
        execution_time = time.time() - start_time
        
        # Registrar en provenance
        tracker = get_provenance_tracker()
        tracker.log_task(
            task_name="write_transformed_to_sql",
            input_data={'rows': rows_before, 'data_hash': data_hash_before},
            output_data={'rows_written': rows_before, 'action': 'created_table'},
            execution_time=execution_time
        )
        
        return True

    # Manejo de esquema dinámico (código existente simplificado)
    with engine.connect() as conn:
        try:
            res = conn.execute(text("PRAGMA table_info('transformed_listings')"))
            existing_cols = [row[1] for row in res.fetchall()]
        except Exception:
            existing_df = pd.read_sql('SELECT * FROM transformed_listings LIMIT 0', conn)
            existing_cols = existing_df.columns.tolist()

        lower_existing = {c.lower(): c for c in existing_cols}
        new_cols = []
        for c in df.columns:
            nc = normalize_text(str(c))
            if nc.lower() in lower_existing:
                new_cols.append(lower_existing[nc.lower()])
            else:
                new_cols.append(nc)
        df.columns = new_cols

        lower_cols = [c.lower() for c in df.columns]
        if len(lower_cols) != len(set(lower_cols)):
            if logger:
                logger.info('Columnas duplicadas detectadas. Consolidando...')
            df.columns = lower_cols
            df = df.groupby(level=0, axis=1).first()
            final_cols = []
            for c in df.columns:
                if c in lower_existing:
                    final_cols.append(lower_existing[c])
                else:
                    final_cols.append(c)
            df.columns = final_cols

        missing = [c for c in df.columns if c not in existing_cols]
        if missing and logger:
            logger.info(f"Columnas faltantes: {missing}. Agregando...")
        for c in missing:
            try:
                conn.execute(text(f'ALTER TABLE transformed_listings ADD COLUMN "{c}" TEXT'))
                if logger:
                    logger.info(f'Columna agregada: {c}')
            except Exception as e:
                if logger:
                    logger.error(f'No se pudo agregar columna {c}: {e}')

        try:
            res = conn.execute(text("PRAGMA table_info('transformed_listings')"))
            existing_cols = [row[1] for row in res.fetchall()]
        except Exception:
            existing_df = pd.read_sql('SELECT * FROM transformed_listings LIMIT 0', conn)
            existing_cols = existing_df.columns.tolist()

    for c in existing_cols:
        if c not in df.columns:
            df[c] = None

    df = df.reindex(columns=existing_cols + [c for c in df.columns if c not in existing_cols])
    
    # Siempre hacer append (el pipeline principal limpia la tabla antes si es necesario)
    df.to_sql('transformed_listings', engine, if_exists='append', index=False)
    
    execution_time = time.time() - start_time
    
    # Registrar en provenance
    tracker = get_provenance_tracker()
    tracker.log_task(
        task_name="write_transformed_to_sql",
        input_data={'rows': rows_before, 'data_hash': data_hash_before},
        output_data={'rows_written': rows_before, 'columns_added': missing, 'action': 'append'},
        execution_time=execution_time
    )
    
    return True
