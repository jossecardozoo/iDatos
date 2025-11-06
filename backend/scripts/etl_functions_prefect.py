"""
etl_functions_prefect.py

Flujo Prefect refactorizado con trazabilidad completa (Data Provenance):
- Cargar datos crudos (CSV) en una base SQLite (datalake/raw)
- Detectar y eliminar duplicados dentro de cada portal
- Ejecutar transformaciones y guardar en otra tabla (datawarehouse/transformed)
- Tracking completo de todas las operaciones para auditoría y reproducibilidad

Este script está pensado para poder ejecutarse localmente o dentro de un contenedor Docker.
"""
from pathlib import Path
import subprocess
import shutil
from datetime import datetime
from typing import Optional

from prefect import flow, task, get_run_logger
from sqlalchemy import create_engine
import pandas as pd

# Importar módulos refactorizados
try:
    from scripts.etl import config
    from scripts.etl.loaders import (
        load_csv,
        create_canonical_tables,
        write_raw_to_sql,
        write_transformed_to_sql,
    )
    from scripts.etl.transformers import transform_df
    from scripts.etl.deduplication import detect_duplicates_by_coordinates, save_duplicates_to_table
    from scripts.etl.provenance import get_provenance_tracker
except ImportError:
    # Fallback para importaciones relativas cuando se ejecuta desde el directorio scripts
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from etl import config
    from etl.loaders import (
        load_csv,
        create_canonical_tables,
        write_raw_to_sql,
        write_transformed_to_sql,
    )
    from etl.transformers import transform_df
    from etl.deduplication import detect_duplicates_by_coordinates, save_duplicates_to_table
    from etl.provenance import get_provenance_tracker


@task(
    name="discover_csvs",
    log_prints=True,
    tags=["extract", "discovery"]
)
def discover_csvs() -> list:
    """
    Task de Prefect para descubrir archivos CSV a procesar.
    
    Busca en CSV_CANDIDATES y en el directorio actual.
    """
    logger = get_run_logger()
    existing = [p for p in config.CSV_CANDIDATES if p.exists()]
    if not existing:
        existing = list(Path('.').glob('*.csv'))
        # También buscar en raw/
        if config.RAW_DATA_DIR.exists():
            existing.extend(list(config.RAW_DATA_DIR.glob('*.csv')))
    logger.info(f"CSV descubiertos: {[str(p) for p in existing]}")
    return existing


@task(
    name="run_script",
    retries=2,
    retry_delay_seconds=10,
    log_prints=True,
    tags=["external", "script"]
)
def run_script(cmd: str):
    """
    Task de Prefect para ejecutar un script externo con trazabilidad.
    
    Args:
        cmd: Comando a ejecutar
        
    Returns:
        True si se ejecutó exitosamente
    """
    logger = get_run_logger()
    logger.info(f'Running: {cmd}')
    
    tracker = get_provenance_tracker()
    tracker.log_task(
        task_name="run_script",
        input_data={'command': cmd},
        output_data={},
    )
    
    try:
        proc = subprocess.run(cmd, check=True, capture_output=True, text=True, shell=True)
        if proc.stdout:
            logger.info(proc.stdout)
        if proc.stderr:
            logger.warning(proc.stderr)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f'Command failed: {e}; stderr: {e.stderr}')
        tracker.log_task(
            task_name="run_script",
            input_data={'command': cmd},
            output_data={'error': str(e)},
        )
        raise


@flow(
    name="etl_flow_prefect",
    log_prints=True,
    retries=1,
    retry_delay_seconds=30
)
def etl_flow(sqlite_path: Optional[str] = None):
    """
    Flujo ETL principal con trazabilidad completa.
    
    Pasos:
    1. Inicializar provenance tracking
    2. Descubrir y cargar CSVs
    3. Detectar y eliminar duplicados por portal
    4. Guardar datos crudos en SQLite
    5. Transformar los datos
    6. Guardar datos transformados en SQLite
    7. Finalizar tracking y guardar metadata
    
    Args:
        sqlite_path: Ruta opcional a la base de datos SQLite
    """
    logger = get_run_logger()
    
    # Inicializar provenance tracking
    tracker = get_provenance_tracker()
    run_id = tracker.start_run(
        flow_name="etl_flow_prefect",
        sqlite_path=sqlite_path
    )
    logger.info(f"Provenance tracking iniciado: run_id={run_id}")
    logger.info(f"Metadata flow: {config.METADATA}")

    try:
        # Asegurar carpetas de datos
        config.RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
        config.PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
        config.PROVENANCE_DIR.mkdir(parents=True, exist_ok=True)
        
        # Configurar ruta de SQLite
        if sqlite_path:
            engine_url = f"sqlite:///{Path(sqlite_path).as_posix()}"
        else:
            engine_url = f"sqlite:///{config.SQLITE_PATH.as_posix()}"

        # Descubrir CSVs
        csvs = discover_csvs()
        total_rows_raw = 0
        total_rows_transformed = 0
        
        # Lista para acumular todos los datos transformados
        all_transformed_data = []

        # Crear tablas canónicas antes de procesar
        engine = create_engine(engine_url)
        try:
            create_canonical_tables(engine, csvs, transform_func=transform_df)
            logger.info('Tablas canónicas creadas/recreadas en la base SQLite antes de la ingesta')
        except Exception as e:
            logger.error(f'No se pudieron crear tablas canónicas: {e}. Continuando con ingestión dinámica')

        # Procesar cada CSV (SIN detección de duplicados por portal)
        for p in csvs:
            logger.info(f"Procesando archivo: {p.name}")
            
            # Cargar CSV (task de Prefect)
            df_raw = load_csv(p)
            total_rows_raw += len(df_raw)
            
            # Persistir datos crudos directamente (sin detección de duplicados)
            write_raw_to_sql(df_raw, engine_url, logger=logger)

            # Transformar datos (task de Prefect)
            df_trans = transform_df(df_raw, logger=logger)
            
            # Asegurar que las columnas estén normalizadas y sean únicas antes de acumular
            from scripts.etl.utils import normalize_text
            df_trans.columns = [normalize_text(str(c)) for c in df_trans.columns]
            # Eliminar columnas duplicadas (case-insensitive)
            df_trans = df_trans.loc[:, ~df_trans.columns.duplicated(keep='first')]
            
            # Acumular datos transformados para detección final (NO escribir aún)
            all_transformed_data.append(df_trans)
            total_rows_transformed += len(df_trans)
            logger.info(f"Transformados {len(df_trans)} registros de {p.name} (acumulados para detección final)")
        
        # Concatenar todos los datos transformados
        if all_transformed_data:
            # Asegurar que todos los DataFrames tengan las mismas columnas antes de concatenar
            all_columns = set()
            for df in all_transformed_data:
                all_columns.update(df.columns)
            
            # Añadir columnas faltantes a cada DataFrame
            for df in all_transformed_data:
                for col in all_columns:
                    if col not in df.columns:
                        df[col] = None
            
            # Reordenar columnas para que sean consistentes
            all_columns_sorted = sorted(all_columns)
            for df in all_transformed_data:
                df = df.reindex(columns=all_columns_sorted)
            
            df_all_transformed = pd.concat(all_transformed_data, ignore_index=True)
            logger.info(f"Total de registros transformados antes de detección de duplicados: {len(df_all_transformed)}")
            
            # Detectar duplicados por coordenadas AL FINAL (cross-portal)
            logger.info("Iniciando detección de duplicados por coordenadas (cross-portal)...")
            df_final, df_duplicates_info, df_duplicates_records = detect_duplicates_by_coordinates(
                df_all_transformed,
                distance_threshold=config.DUPLICATE_DISTANCE_THRESHOLD,  # Usar configuración
                logger=logger
            )
            
            # Guardar metadatos de duplicados en tabla separada
            if not df_duplicates_info.empty:
                save_duplicates_to_table(df_duplicates_info, engine_url, table_name='duplicates_detected', logger=logger)
                logger.info(f"Metadatos de duplicados guardados en tabla 'duplicates_detected': {len(df_duplicates_info)} registros")
            
            # Mover registros completos de duplicados cross-portal a tabla separada
            if not df_duplicates_records.empty:
                from scripts.etl.deduplication import save_duplicate_records_to_table
                save_duplicate_records_to_table(df_duplicates_records, engine_url, table_name='duplicates_moved', logger=logger)
                logger.info(f"Registros duplicados cross-portal movidos a tabla 'duplicates_moved': {len(df_duplicates_records)} registros")
            
            # Guardar TODOS los datos en tabla transformed_listings (incluyendo duplicados, no se eliminan)
            logger.info("Guardando todos los registros en transformed_listings (incluyendo duplicados)...")
            from sqlalchemy import create_engine as ce, text
            from scripts.etl.utils import normalize_text
            engine_final = ce(engine_url)
            
            # Normalizar columnas
            df_final.columns = [normalize_text(str(c)) for c in df_final.columns]
            
            # Guardar todos los registros (reemplazar tabla completa para asegurar esquema correcto)
            df_final.to_sql('transformed_listings', engine_final, if_exists='replace', index=False)
            logger.info(f"Todos los registros guardados en transformed_listings: {len(df_final)} registros (incluyendo duplicados del mismo portal)")
            
            # Registrar en provenance
            tracker.log_task(
                task_name="write_transformed_to_sql_final",
                input_data={'rows': len(df_final)},
                output_data={
                    'rows_written': len(df_final), 
                    'action': 'replace',
                    'duplicates_moved': len(df_duplicates_records)
                },
            )
            
            total_duplicates_moved = len(df_duplicates_records)
        else:
            logger.warning("No hay datos transformados para procesar")
            total_duplicates_moved = 0
            df_final = pd.DataFrame()

        # Actualizar estadísticas finales
        tracker.update_statistics(
            total_rows_raw=total_rows_raw,
            total_rows_transformed=total_rows_transformed,
            total_duplicates_moved=total_duplicates_moved,
            files_processed=len(csvs)
        )
        
        logger.info(
            f"ETL finalizado. "
            f"Filas crudas: {total_rows_raw}, "
            f"Duplicados cross-portal movidos: {total_duplicates_moved}, "
            f"Transformadas: {total_rows_transformed}"
        )
        
        # Finalizar tracking
        tracker.end_run(status='completed')
        logger.info(f"Provenance metadata guardado para run_id={run_id}")
        
    except Exception as e:
        logger.error(f"Error en ETL flow: {e}")
        tracker.end_run(status='failed', error=str(e))
        raise


@flow(
    name='full_etl_pipeline_prefect',
    log_prints=True,
    retries=1,
    retry_delay_seconds=60
)
def full_etl_pipeline(db_path: Optional[str] = None, gallito_limit: Optional[int] = None, dry_run: bool = False):
    """
    Pipeline ETL completo orquestado con Prefect y trazabilidad completa.

    Pasos:
      1) Opcionalmente ejecutar scrapers para refrescar CSVs crudos
      2) Limpiar direcciones de Gallito
      3) Geocodificar en batch
      4) Ejecutar flujo ETL (ingesta + detección de duplicados + transformación -> transformed_listings)
      5) Ejecutar enriquecimiento contextual (si está disponible)
      6) Cargar denuncias y unir mapeo de criminalidad
      7) Archivar filas sin coordenadas
      
    Args:
        db_path: Ruta opcional a la base de datos
        gallito_limit: Límite opcional para scraper de Gallito
        dry_run: Si True, omite ejecución de scripts externos
    """
    logger = get_run_logger()
    
    # Inicializar provenance tracking
    tracker = get_provenance_tracker()
    run_id = tracker.start_run(
        flow_name="full_etl_pipeline_prefect",
        db_path=db_path,
        gallito_limit=gallito_limit,
        dry_run=dry_run
    )
    
    logger.info(f'Starting full ETL pipeline (Prefect) - run_id={run_id}')

    try:
        dbp = Path(db_path) if db_path else config.SQLITE_PATH

        PY = shutil.which('python') or 'python'

        # 1) Scrapers (opcional) -- ejecutar Mercadolibre y Gallito detail
        if not dry_run:
            run_script(f"{PY} iDatos/backend/scripts/01_mercadolibre_scraper.py")
            cmd_g = f"{PY} iDatos/backend/scripts/02_gallito_detail_scraper.py"
            if gallito_limit:
                cmd_g += f" --limit {gallito_limit}"
            run_script(cmd_g)
        else:
            logger.info('Dry-run: skipping scrapers')

        # 2) Limpiar direcciones de Gallito
        if not dry_run:
            run_script(
                f"{PY} iDatos/backend/scripts/03_clean_gallito_addresses.py "
                "--input gallito_alquileres_crudos.with_addr.csv"
            )
        else:
            logger.info('Dry-run: skipping clean_gallito_addresses')

        # 3) Geocodificar en batch
        if not dry_run:
            run_script(
                f"{PY} iDatos/backend/scripts/04_geocode_batch.py "
                "--delay 1.0 --sources gallito_alquileres_crudos.with_addr.cleaned.csv"
            )
            # Reintentar no resueltos usando geocode.xyz script
            run_script(
                f"{PY} iDatos/backend/scripts/05_geocode_xyz_retry.py "
                "--failed geocode_failed_*.csv --delay 1.2"
            )
        else:
            logger.info('Dry-run: skipping geocoding')

        # 4) Ejecutar el flujo ETL (ingesta + detección de duplicados + transformación)
        logger.info('Running etl_flow (ingest + deduplication + transform)')
        etl_flow(sqlite_path=dbp.as_posix())

        # 5) Enriquecimiento contextual (intentar ejecutar helper si está disponible)
        try:
            from scripts.transformaciones.datos_contextuales import enrich_with_contextual_data as helper_enrich_context
            logger.info('Attempting contextual enrichment via helper')
            import sqlite3
            import pandas as pd
            conn = sqlite3.connect(str(dbp))
            df = pd.read_sql_query('SELECT * FROM transformed_listings', conn)
            conn.close()
            df2 = helper_enrich_context(df)
            write_transformed_to_sql(df2, f"sqlite:///{dbp.as_posix()}", logger=logger)
        except Exception as e:
            logger.warning(f'Contextual enrichment failed: {e}')

        # 6) Cargar denuncias y unir
        if not dry_run:
            run_script(f"{PY} iDatos/backend/scripts/07_load_denuncias_crime.py --db {dbp.as_posix()}")
            run_script(f"{PY} iDatos/backend/scripts/08_join_crime_to_transformed.py --db {dbp.as_posix()}")
        else:
            logger.info('Dry-run: skipping load/join of denuncias')

        # 7) Archivar coordenadas nulas
        if not dry_run:
            run_script(f"{PY} iDatos/backend/scripts/09_archive_null_coords.py --db {dbp.as_posix()} --move")
        else:
            logger.info('Dry-run: skipping archive_null_coords')

        logger.info('Full ETL pipeline finished')
        tracker.end_run(status='completed')
        
    except Exception as e:
        logger.error(f"Error en full ETL pipeline: {e}")
        tracker.end_run(status='failed', error=str(e))
        raise


if __name__ == '__main__':
    etl_flow()
