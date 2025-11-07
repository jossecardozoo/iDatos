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
import glob
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
def run_script(cmd: str, cwd: Optional[Path] = None):
    """
    Task de Prefect para ejecutar un script externo con trazabilidad.
    
    Args:
        cmd: Comando a ejecutar
        cwd: Directorio de trabajo (default: directorio backend/)
        
    Returns:
        True si se ejecutó exitosamente
    """
    logger = get_run_logger()
    
    # Si no se especifica cwd, usar el directorio backend/ (un nivel arriba de scripts/)
    if cwd is None:
        backend_dir = Path(__file__).resolve().parent.parent
        cwd = backend_dir
    
    logger.info(f'Running: {cmd} (cwd: {cwd})')
    
    tracker = get_provenance_tracker()
    tracker.log_task(
        task_name="run_script",
        input_data={'command': cmd, 'cwd': str(cwd)},
        output_data={},
    )
    
    try:
        proc = subprocess.run(
            cmd, 
            check=True, 
            capture_output=True, 
            text=True, 
            shell=True,
            cwd=str(cwd)
        )
        if proc.stdout:
            logger.info(proc.stdout)
        if proc.stderr:
            logger.warning(proc.stderr)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f'Command failed: {e}; stderr: {e.stderr}')
        tracker.log_task(
            task_name="run_script",
            input_data={'command': cmd, 'cwd': str(cwd)},
            output_data={'error': str(e)},
        )
        raise


@flow(
    name="etl_flow_prefect",
    log_prints=True,
    retries=1,
    retry_delay_seconds=30
)
def etl_flow(sqlite_path: Optional[str] = None, duplicate_method: str = 'coordinates'):
    """
    Flujo ETL principal con trazabilidad completa.
    
    Pasos:
    1. Inicializar provenance tracking
    2. Descubrir y cargar CSVs
    3. Detectar y eliminar duplicados por portal
    4. Guardar datos crudos en SQLite
    5. Transformar los datos
    6. Detectar duplicados cross-portal (según método seleccionado)
    7. Guardar datos transformados en SQLite
    8. Finalizar tracking y guardar metadata
    
    Args:
        sqlite_path: Ruta opcional a la base de datos SQLite
        duplicate_method: Método de detección de duplicados cross-portal
            - 'coordinates': Detección por coordenadas exactas (default, rápido)
            - 'dbscan': Detección con DBSCAN (rápido, recomendado)
            - 'hierarchical': Detección con clustering jerárquico (lento, preciso)
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
        try:
            create_canonical_tables(engine_url, csvs, transform_func=transform_df)
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
            
            # Detectar duplicados AL FINAL (cross-portal) según método seleccionado
            if duplicate_method == 'dbscan':
                logger.info("Iniciando detección de duplicados con DBSCAN (cross-portal)...")
                from scripts.etl.clustering_fast import detect_duplicates_by_dbscan
                df_final, df_duplicates_info, df_duplicates_records = detect_duplicates_by_dbscan(
                    df_all_transformed,
                    eps=0.3,
                    min_samples=2,
                    title_col='titulo',
                    source_col=None,
                    logger=logger
                )
            elif duplicate_method == 'hierarchical':
                logger.info("Iniciando detección de duplicados con clustering jerárquico (cross-portal)...")
                from scripts.etl.clustering import detect_duplicates_by_clustering
                df_final, df_duplicates_info, df_duplicates_records = detect_duplicates_by_clustering(
                    df_all_transformed,
                    similarity_threshold=75.0,
                    title_col='titulo',
                    source_col=None,
                    logger=logger
                )
            else:  # 'coordinates' (default)
                logger.info("Iniciando detección de duplicados por coordenadas (cross-portal)...")
                df_final, df_duplicates_info, df_duplicates_records = detect_duplicates_by_coordinates(
                    df_all_transformed,
                    distance_threshold=config.DUPLICATE_DISTANCE_THRESHOLD,
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
        
        # Obtener directorios: backend/ y scripts/
        backend_dir = Path(__file__).resolve().parent.parent
        scripts_dir = backend_dir / "scripts"
        
        # 1) Scrapers (opcional) -- ejecutar Mercadolibre y Gallito detail
        if not dry_run:
            scraper_ml = scripts_dir / "01_mercadolibre_scraper.py"
            run_script(f'{PY} "{scraper_ml.as_posix()}"', cwd=backend_dir)
            
            # Ejecutar scraper de Gallito para generar archivo .with_addr.csv
            scraper_g = scripts_dir / "02_gallito_detail_scraper.py"
            
            # Buscar archivo de entrada en múltiples ubicaciones
            gallito_input_paths = [
                backend_dir / "data" / "raw" / "gallito_alquileres_crudos.csv",  # Primero en data/raw/
                backend_dir / "gallito_alquileres_crudos.csv",  # Luego en raíz de backend/
            ]
            
            gallito_input = None
            gallito_input_rel = None
            for path in gallito_input_paths:
                if path.exists():
                    gallito_input = path
                    # Ruta relativa desde backend_dir para el comando
                    gallito_input_rel = path.relative_to(backend_dir).as_posix()
                    break
            
            gallito_output_rel = "gallito_alquileres_crudos.with_addr.csv"
            gallito_output = backend_dir / gallito_output_rel
            
            if gallito_input and gallito_input.exists():
                try:
                    cmd_g = f'{PY} "{scraper_g.as_posix()}" --input "{gallito_input_rel}" --output "{gallito_output_rel}"'
                    if gallito_limit:
                        cmd_g += f" --limit {gallito_limit}"
                    logger.info(f'Ejecutando scraper de Gallito para generar {gallito_output_rel}')
                    logger.info(f'  Input: {gallito_input_rel}')
                    run_script(cmd_g, cwd=backend_dir)
                    
                    # Verificar que se generó el archivo
                    if gallito_output.exists():
                        logger.info(f'✓ Archivo generado exitosamente: {gallito_output_rel}')
                    else:
                        logger.warning(f'⚠ El scraper no generó el archivo esperado: {gallito_output_rel}')
                except Exception as e:
                    logger.warning(f'Error ejecutando scraper de Gallito: {e}. Continuando...')
            else:
                logger.warning(f'Archivo de entrada gallito_alquileres_crudos.csv no encontrado en {[str(p) for p in gallito_input_paths]}. Saltando scraper de Gallito.')
        else:
            logger.info('Dry-run: skipping scrapers')

        # 2) Limpiar direcciones de Gallito (solo si existe el archivo de entrada)
        if not dry_run:
            gallito_with_addr = backend_dir / "gallito_alquileres_crudos.with_addr.csv"
            if gallito_with_addr.exists():
                clean_script = scripts_dir / "03_clean_gallito_addresses.py"
                run_script(
                    f'{PY} "{clean_script.as_posix()}" '
                    f"--input {gallito_with_addr.name}",
                    cwd=backend_dir
                )
            else:
                logger.warning(f'Archivo {gallito_with_addr.name} no encontrado. Saltando limpieza de direcciones de Gallito.')
        else:
            logger.info('Dry-run: skipping clean_gallito_addresses')

        # 3) Geocodificar en batch (solo si existe el archivo de entrada)
        if not dry_run:
            gallito_cleaned = backend_dir / "gallito_alquileres_crudos.with_addr.cleaned.csv"
            if gallito_cleaned.exists():
                geocode_script = scripts_dir / "04_geocode_batch.py"
                run_script(
                    f'{PY} "{geocode_script.as_posix()}" '
                    f"--delay 1.0 --sources {gallito_cleaned.name}",
                    cwd=backend_dir
                )
                # Reintentar no resueltos usando geocode.xyz script (solo si hay archivos fallidos)
                failed_files = glob.glob(str(backend_dir / "geocode_failed_*.csv"))
                if failed_files:
                    geocode_xyz_script = scripts_dir / "05_geocode_xyz_retry.py"
                    run_script(
                        f'{PY} "{geocode_xyz_script.as_posix()}" '
                        "--failed geocode_failed_*.csv --delay 1.2",
                        cwd=backend_dir
                    )
                else:
                    logger.info('No hay archivos de geocodificación fallidos. Saltando reintento con geocode.xyz')
            else:
                logger.warning(f'Archivo {gallito_cleaned.name} no encontrado. Saltando geocodificación en batch.')
        else:
            logger.info('Dry-run: skipping geocoding')

        # 4) Ejecutar el flujo ETL (ingesta + detección de duplicados + transformación)
        logger.info('Running etl_flow (ingest + deduplication + transform)')
        etl_flow(sqlite_path=dbp.as_posix())

        # 5) Enriquecimiento contextual (intentar ejecutar helper si está disponible)
        try:
            from scripts.datos_contextuales import enrich_with_contextual_data as helper_enrich_context
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
            load_denuncias_script = scripts_dir / "07_load_denuncias_crime.py"
            run_script(f'{PY} "{load_denuncias_script.as_posix()}" --db {dbp.as_posix()}', cwd=backend_dir)
            join_crime_script = scripts_dir / "08_join_crime_to_transformed.py"
            run_script(f'{PY} "{join_crime_script.as_posix()}" --db {dbp.as_posix()}', cwd=backend_dir)
        else:
            logger.info('Dry-run: skipping load/join of denuncias')

        # 7) Archivar coordenadas nulas
        if not dry_run:
            archive_script = scripts_dir / "09_archive_null_coords.py"
            run_script(f'{PY} "{archive_script.as_posix()}" --db {dbp.as_posix()} --move', cwd=backend_dir)
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
