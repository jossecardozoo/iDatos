"""
etl_functions_prefect.py

Flujo Prefect sencillo para:
- Cargar datos crudos (CSV) en una base SQLite (datalake/raw)
- Ejecutar transformaciones ligeras y guardar en otra tabla (datawarehouse/transformed)

Este script está pensado para poder ejecutarse localmente o dentro de un contenedor Docker.
"""
from pathlib import Path
import json
import unicodedata
import re
from datetime import datetime

import pandas as pd
from sqlalchemy import create_engine

from prefect import flow, task, get_run_logger

# Config
DATA_DIR = Path(".")
SQLITE_PATH = DATA_DIR / "data" / "etl_datalake.db"
CSV_CANDIDATES = [
    Path("mercadolibre_alquileres_con_imagen.csv"),
    Path("gallito_alquileres_crudos.csv"),
    Path("infocasas_datos.csv"),
    Path("datos_transformados_final.csv"),
]

# Metadata for the flow
METADATA = {
    "name": "etl_functions_prefect",
    "description": "ETL que carga crudos a SQLite (datalake) y guarda transformados (datawarehouse)",
    "author": "iDatos team",
    "date_created": "2025-11-04",
    "version": "1.0",
}

# Conversion rates (same idea que script_transformaciones)
TASAS_DE_CAMBIO = {
    'UYU': 1.0,
    'USD': 39.93,
    'U$S': 39.93,
    '$': 1.0,
    'ARS': 0.0278,
    'N/A': 1.0,
}


def normalize_text(s: str) -> str:
    if not isinstance(s, str):
        return ''
    s = s.lower().strip()
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", '_', s)
    s = re.sub(r'_+', '_', s)
    return s.strip('_')


def _read_csv_header(path: Path):
    """Read only the header of a CSV robustly, returning list of column names."""
    try:
        df = pd.read_csv(path, nrows=0, dtype=str, encoding='utf-8')
    except Exception:
        df = pd.read_csv(path, nrows=0, dtype=str, encoding='latin-1')
    return list(df.columns)


def create_canonical_tables(engine, csv_paths: list):
    """Create canonical empty tables for raw_listings and transformed_listings.

    - raw: union of all CSV headers (normalized)
    - transformed: apply transform_df to an empty DataFrame with raw columns to infer transformed schema
    """
    # union raw columns
    raw_cols = []
    for p in csv_paths:
        try:
            cols = _read_csv_header(p)
        except Exception:
            cols = []
        for c in cols:
            nc = normalize_text(str(c))
            if nc not in raw_cols:
                raw_cols.append(nc)

    # ensure metadata columns
    for extra in ['__source_file', '__loaded_at']:
        if extra not in raw_cols:
            raw_cols.append(extra)

    # create empty raw table with canonical columns
    df_empty_raw = pd.DataFrame(columns=raw_cols)
    df_empty_raw.to_sql('raw_listings', engine, if_exists='replace', index=False)

    # infer transformed schema by running transform_df on an empty df with raw columns
    df_for_transform = pd.DataFrame(columns=raw_cols)
    try:
        df_transformed_sample = transform_df(df_for_transform)
        trans_cols = [normalize_text(str(c)) for c in df_transformed_sample.columns.tolist()]
    except Exception:
        # fallback to a reasonable default if transform fails
        trans_cols = ['url', 'titulo', 'ubicacion', 'precio_moneda', 'precio_valor', 'imagen_url', 'fuente']

    # ensure trans cols unique while preserving order
    seen = set()
    trans_cols_unique = [x for x in trans_cols if not (x in seen or seen.add(x))]
    df_empty_trans = pd.DataFrame(columns=trans_cols_unique)
    df_empty_trans.to_sql('transformed_listings', engine, if_exists='replace', index=False)


@task
def discover_csvs() -> list:
    """Devuelve la lista de CSV existentes a partir de CSV_CANDIDATES o buscando *.csv"""
    logger = get_run_logger()
    existing = [p for p in CSV_CANDIDATES if p.exists()]
    if not existing:
        existing = list(Path('.').glob('*.csv'))
    logger.info(f"CSV descubiertos: {[str(p) for p in existing]}")
    return existing


@task
def load_csv(path: Path) -> pd.DataFrame:
    logger = get_run_logger()
    logger.info(f"Cargando CSV: {path}")
    try:
        # Intentamos UTF-8 primero
        df = pd.read_csv(path, dtype=str, encoding='utf-8')
    except Exception:
        # Fallback a latin-1 si falla la decodificación UTF-8
        df = pd.read_csv(path, dtype=str, encoding='latin-1')
    df['__source_file'] = path.name
    df['__loaded_at'] = datetime.utcnow().isoformat()
    return df


@task
def write_raw_to_sql(df: pd.DataFrame, engine_url: str):
    logger = get_run_logger()
    engine = create_engine(engine_url)
    logger.info(f"Escribiendo {len(df)} filas en tabla raw_listings")
    # Si la tabla no existe, crearla (replace crea la tabla con las columnas del DF)
    from sqlalchemy import inspect, text
    inspector = None
    try:
        inspector = inspect(engine)
    except Exception:
        inspector = None

    if inspector is None or not inspector.has_table('raw_listings'):
        logger.info('Tabla raw_listings no existe: creando con esquema del DataFrame')
        # normalize df columns first
        df.columns = [normalize_text(str(c)) for c in df.columns]
        df.to_sql('raw_listings', engine, if_exists='replace', index=False)
        return True

    # Si la tabla ya existe: obtener columnas actuales vía PRAGMA y agregar las que falten
    with engine.connect() as conn:
        try:
            res = conn.execute(text("PRAGMA table_info('raw_listings')"))
            existing_cols = [row[1] for row in res.fetchall()]
        except Exception:
            # Fallback: leer 0 filas y obtener columnas
            existing_df = pd.read_sql('SELECT * FROM raw_listings LIMIT 0', conn)
            existing_cols = existing_df.columns.tolist()

        # map lowercase existing to original (to avoid case/accents duplicate issues)
        lower_existing = {c.lower(): c for c in existing_cols}
        # normalize df column names and, if column exists by lower-case, rename to existing exact
        new_cols = []
        for c in df.columns:
            nc = normalize_text(str(c))
            mapped = lower_existing.get(nc.lower())
            new_cols.append(mapped if mapped is not None else nc)
        df.columns = new_cols

        # Consolidate duplicates (case-insensitive) by taking first non-null across duplicates
        lower_cols = [c.lower() for c in df.columns]
        if len(lower_cols) != len(set(lower_cols)):
            logger.info('Columnas duplicadas detectadas en DataFrame (case-insensitive). Consolidando...')
            df.columns = lower_cols
            df = df.groupby(level=0, axis=1).first()
            # map back to existing exact names where possible
            df.columns = [lower_existing.get(c, c) for c in df.columns]

        missing = [c for c in df.columns if c not in existing_cols]
        if missing:
            logger.info(f"Columnas faltantes en raw_listings: {missing}. Intentando agregarlas...")
        for c in missing:
            try:
                conn.execute(text(f'ALTER TABLE raw_listings ADD COLUMN "{c}" TEXT'))
                logger.info(f'Columna agregada: {c}')
            except Exception as e:
                logger.error(f'No se pudo agregar columna {c}: {e}')

        # Volver a leer columnas después de intentos de ALTER
        try:
            res = conn.execute(text("PRAGMA table_info('raw_listings')"))
            existing_cols = [row[1] for row in res.fetchall()]
        except Exception:
            existing_df = pd.read_sql('SELECT * FROM raw_listings LIMIT 0', conn)
            existing_cols = existing_df.columns.tolist()

    # Asegurar que el DataFrame tenga todas las columnas esperadas
    for c in existing_cols:
        if c not in df.columns:
            df[c] = None

    # Reordenar columnas para evitar errores con to_sql
    df = df.reindex(columns=existing_cols + [c for c in df.columns if c not in existing_cols])

    # Intentar escribir; si falla por esquema, volver a intentar agregar columnas detectadas en la excepción
    try:
        df.to_sql('raw_listings', engine, if_exists='append', index=False)
        return True
    except Exception as e:
        logger.error(f'Primer intento de append falló: {e}')
        # intentar extraer columnas faltantes desde el mensaje de error o re-inspeccionar
        with engine.connect() as conn:
            res = conn.execute(text("PRAGMA table_info('raw_listings')"))
            existing_cols = [row[1] for row in res.fetchall()]
            missing = [c for c in df.columns if c not in existing_cols]
            for c in missing:
                try:
                    conn.execute(text(f'ALTER TABLE raw_listings ADD COLUMN "{c}" TEXT'))
                    logger.info(f'Columna agregada en retry: {c}')
                except Exception as e2:
                    logger.error(f'No se pudo agregar columna {c} en retry: {e2}')

        # último intento
        df = df.reindex(columns=existing_cols + [c for c in df.columns if c not in existing_cols])
        df.to_sql('raw_listings', engine, if_exists='append', index=False)
        return True


@task
def transform_df(df: pd.DataFrame) -> pd.DataFrame:
    logger = get_run_logger()
    if df.empty:
        return df

    df = df.copy()

    # Normalize column names early
    df.columns = [normalize_text(str(c)) for c in df.columns]

    # --- Step 1: Keep only entries in Montevideo ---
    if 'ubicacion' in df.columns:
        mask = df['ubicacion'].astype(str).str.lower().str.contains('montevideo')
        logger.info(f"Filtrando filas: conservando {mask.sum()} de {len(df)} con 'Montevideo' en ubicacion")
        df = df[mask].reset_index(drop=True)
        df['ubicacion'] = df['ubicacion'].astype(str).str.replace(r',?\s*montevideo\b', '', flags=re.IGNORECASE, regex=True).str.strip()

    # Also remove the literal 'Montevideo' from titulo if present
    title_cols = [c for c in df.columns if 'titulo' in c or 'title' in c]
    if title_cols:
        tcol = title_cols[0]
        df[tcol] = df[tcol].astype(str).str.replace(r'\bmontevideo\b', '', flags=re.IGNORECASE, regex=True).str.strip()

    # --- Step 2: Geocoding (before barrio imputation) ---
    def limpiar_ubicacion_para_geocodificacion(direccion):
        if not isinstance(direccion, str):
            return ''
        parte_principal = direccion.split(',')[0].strip()
        parte_principal = re.sub(r'\s*/\s*\d+\s*$', '', parte_principal)
        parte_principal = re.sub(r'\s*Esq\.?\s*', ' and ', parte_principal, flags=re.IGNORECASE)
        parte_principal = re.sub(r'\s*esquina\s*', ' and ', parte_principal, flags=re.IGNORECASE)
        parte_principal = re.sub(r'\s{2,}', ' ', parte_principal).strip()
        return parte_principal.strip()

    df['latitud'] = None
    df['longitud'] = None
    try:
        from geopy.geocoders import Nominatim
        from geopy.extra.rate_limiter import RateLimiter
        geolocator = Nominatim(user_agent='idatos_etl_geocoder', timeout=10)
        geocode_rate = RateLimiter(geolocator.geocode, min_delay_seconds=1.0)

        def try_geocode(ubic):
            q = limpiar_ubicacion_para_geocodificacion(ubic) + ', Montevideo, Uruguay'
            try:
                loc = geocode_rate(q)
                if loc:
                    return loc.latitude, loc.longitude
            except Exception:
                return None, None
            return None, None

        for idx, val in df['ubicacion'].astype(str).items():
            lat, lon = try_geocode(val)
            df.at[idx, 'latitud'] = lat
            df.at[idx, 'longitud'] = lon
    except Exception:
        logger.info('geopy no disponible o error en geocodificación — continuando sin coordenadas')

    # --- Step 3: Price normalization / numeric extraction ---
    for col in ['precio_valor', 'price', 'valor']:
        if col in df.columns:
            df['precio_valor_num'] = pd.to_numeric(df[col].astype(str).str.replace(r"[^0-9]", '', regex=True), errors='coerce')
            break
    if 'precio_valor_num' not in df.columns:
        df['precio_valor_num'] = pd.Series([None] * len(df))

    moneda_col = None
    for c in ['precio_moneda', 'moneda', 'currency']:
        if c in df.columns:
            moneda_col = c
            break
    df['precio_moneda_normalizada'] = df[moneda_col].astype(str).str.upper().fillna('N/A') if moneda_col else 'N/A'

    def convertir_a_base(row):
        moneda = str(row.get('precio_moneda_normalizada', 'N/A')).upper().strip()
        moneda = moneda.replace('$', 'UYU') if moneda == '$' else moneda
        tasa = TASAS_DE_CAMBIO.get(moneda, 1.0)
        val = row.get('precio_valor_num')
        try:
            return float(val) * float(tasa) if pd.notna(val) else None
        except Exception:
            return None

    df['precio_base_uyu'] = df.apply(convertir_a_base, axis=1)

    # --- Step 4: Dorms imputation from title ---
    def extraer_dorms(titulo):
        if not isinstance(titulo, str):
            return None
        t = titulo.lower()
        if 'monoambiente' in t or 'mono ambiente' in t or 'studio' in t:
            return 1
        m = re.search(r'(\d+)\s*(dorm|hab|amb)', t)
        if m:
            return int(m.group(1))
        m2 = re.search(r'\b(un|uno|una|dos|tres|cuatro)\b', t)
        map_num = {'un':1,'uno':1,'una':1,'dos':2,'tres':3,'cuatro':4}
        if m2:
            return map_num.get(m2.group(1), None)
        return None

    if title_cols:
        df['dorms_imputado'] = df[title_cols[0]].apply(extraer_dorms)
    else:
        df['dorms_imputado'] = None

    # --- Step 5: Barrio imputation using denuncias JSON aliases ---
    barrio_norm = []
    try:
        jpath = Path('datos') / 'denuncias_hurtos_por_10000_hab_montevideo.json'
        if jpath.exists():
            with open(jpath, 'r', encoding='utf-8') as fh:
                payload = json.load(fh)
            data = payload.get('data', {})
            alias_map = {}
            label_map = {}
            for key, item in data.items():
                label = item.get('label')
                norm_key = normalize_text(label)
                label_map[norm_key] = label
                alias_map[norm_key] = norm_key
                for a in item.get('aliases', []):
                    alias_map[normalize_text(a)] = norm_key
        else:
            alias_map = {}
    except Exception:
        alias_map = {}

    def guess_barrio(ubic, lat, lon):
        if not isinstance(ubic, str) or not ubic:
            return None
        parts = [p.strip() for p in ubic.split(',') if p.strip()]
        for idx in [0, 1, 2, -1]:
            if len(parts) > idx and idx >= -len(parts):
                cand = normalize_text(parts[idx])
                if cand in alias_map:
                    return alias_map[cand]
        u_norm = normalize_text(ubic)
        for a, v in alias_map.items():
            if a and a in u_norm:
                return v
        return None

    for idx, row in df.iterrows():
        barrio = None
        ubic = row.get('ubicacion') if 'ubicacion' in df.columns else None
        lat = row.get('latitud')
        lon = row.get('longitud')
        barrio = guess_barrio(ubic, lat, lon)
        barrio_norm.append(barrio)

    df['barrio_guess'] = barrio_norm

    # Final normalization of column names
    df.columns = [normalize_text(str(c)) for c in df.columns]
    return df


@task
def write_transformed_to_sql(df: pd.DataFrame, engine_url: str):
    logger = get_run_logger()
    engine = create_engine(engine_url)
    logger.info(f"Escribiendo {len(df)} filas en tabla transformed_listings")
    from sqlalchemy import inspect, text
    inspector = None
    try:
        inspector = inspect(engine)
    except Exception:
        inspector = None

    # Normalize df columns first
    df.columns = [normalize_text(str(c)) for c in df.columns]

    if inspector is None or not inspector.has_table('transformed_listings'):
        logger.info('Tabla transformed_listings no existe: creando con esquema del DataFrame')
        df.to_sql('transformed_listings', engine, if_exists='replace', index=False)
        return True

    with engine.connect() as conn:
        try:
            res = conn.execute(text("PRAGMA table_info('transformed_listings')"))
            existing_cols = [row[1] for row in res.fetchall()]
        except Exception:
            existing_df = pd.read_sql('SELECT * FROM transformed_listings LIMIT 0', conn)
            existing_cols = existing_df.columns.tolist()

        # Avoid case/accent duplicate issues by mapping lower -> exact existing
        lower_existing = {c.lower(): c for c in existing_cols}
        new_cols = []
        for c in df.columns:
            nc = normalize_text(str(c))
            if nc.lower() in lower_existing:
                new_cols.append(lower_existing[nc.lower()])
            else:
                new_cols.append(nc)
        df.columns = new_cols

        # If mapping produced duplicate column labels (case-insensitive duplicates), coalesce them
        lower_cols = [c.lower() for c in df.columns]
        if len(lower_cols) != len(set(lower_cols)):
            logger.info('Columnas duplicadas detectadas en DataFrame (case-insensitive). Consolidando...')
            # Temporarily set lower-case columns and take the first non-null per group
            df.columns = lower_cols
            df = df.groupby(level=0, axis=1).first()
            # after grouping, rename back to existing exact names when possible
            final_cols = []
            for c in df.columns:
                if c in lower_existing:
                    final_cols.append(lower_existing[c])
                else:
                    final_cols.append(c)
            df.columns = final_cols

        missing = [c for c in df.columns if c not in existing_cols]
        if missing:
            logger.info(f"Columnas faltantes en transformed_listings: {missing}. Intentando agregarlas...")
        for c in missing:
            try:
                conn.execute(text(f'ALTER TABLE transformed_listings ADD COLUMN "{c}" TEXT'))
                logger.info(f'Columna agregada en transformed_listings: {c}')
            except Exception as e:
                logger.error(f'No se pudo agregar columna {c} en transformed_listings: {e}')

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

    df.to_sql('transformed_listings', engine, if_exists='append', index=False)
    return True


@flow(name="etl_flow_prefect")
def etl_flow():
    logger = get_run_logger()
    logger.info(f"Metadata flow: {METADATA}")

    # asegurar carpeta de datos
    (DATA_DIR / 'data').mkdir(exist_ok=True)
    engine_url = f"sqlite:///{SQLITE_PATH.as_posix()}"

    csvs = discover_csvs()
    total_rows_raw = 0
    total_rows_transformed = 0

    # Crear tablas canónicas (union de columnas) antes de procesar para evitar ALTERs repetidos
    engine = create_engine(engine_url)
    try:
        create_canonical_tables(engine, csvs)
        logger.info('Tablas canónicas creadas/recreadas en la base SQLite antes de la ingesta')
    except Exception as e:
        logger.error(f'No se pudieron crear tablas canónicas: {e}. Continuando con ingestión dinámica')

    for p in csvs:
        df_raw = load_csv(p)
        # persistir raw
        write_raw_to_sql(df_raw, engine_url)
        total_rows_raw += len(df_raw)

        df_trans = transform_df(df_raw)
        write_transformed_to_sql(df_trans, engine_url)
        total_rows_transformed += len(df_trans)

    logger.info(f"ETL finalizado. Filas crudas: {total_rows_raw}, transformadas: {total_rows_transformed}")


if __name__ == '__main__':
    etl_flow()
