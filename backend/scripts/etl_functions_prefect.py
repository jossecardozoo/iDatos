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
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import create_engine

from prefect import flow, task, get_run_logger
import subprocess
import shlex
import shutil
# optional fuzzy matching
try:
    from rapidfuzz import process as rf_process, fuzz as rf_fuzz
    HAVE_RAPIDFUZZ = True
except Exception:
    HAVE_RAPIDFUZZ = False

# optional local transform helpers (normalize, guess_barrio, geocode helpers)
try:
    from scripts.transformaciones.transform_helpers import (
        load_denuncias_aliases,
        guess_barrio as helper_guess_barrio,
        limpiar_ubicacion_para_geocodificacion as helper_limpiar_ubicacion_para_geocodificacion,
        extraer_dorms as helper_extraer_dorms,
        normalize_for_match as helper_normalize_for_match,
    )
    HAVE_HELPERS = True
except Exception:
    HAVE_HELPERS = False

# optional contextual enrichment (backend copy)
try:
    from scripts.transformaciones.datos_contextuales import enrich_with_contextual_data as helper_enrich_context
    HAVE_CONTEXT_HELPER = True
except Exception:
    # Try alternative imports; sometimes package layout prevents a normal import.
    loaded = False
    try:
        from iDatos.backend.scripts.datos_contextuales import enrich_with_contextual_data as helper_enrich_context
        HAVE_CONTEXT_HELPER = True
        loaded = True
    except Exception:
        # final fallback: try loading by file path using importlib (works when running from repo root)
        try:
            import importlib.util
            from pathlib import Path
            helper_path = Path('iDatos') / 'backend' / 'scripts' / 'datos_contextuales.py'
            if helper_path.exists():
                spec = importlib.util.spec_from_file_location('backend_contextual_helper', str(helper_path))
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                helper_enrich_context = getattr(mod, 'enrich_with_contextual_data')
                HAVE_CONTEXT_HELPER = True
                loaded = True
        except Exception:
            HAVE_CONTEXT_HELPER = False
    if not loaded:
        HAVE_CONTEXT_HELPER = False

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


def _get_geocode_db_path():
    """Return the path to the sqlite datalake where we store geocode_cache.

    Prefer backend/data/etl_datalake.db, fallback to repo-root data/etl_datalake.db
    """
    from pathlib import Path
    p1 = Path('iDatos') / 'backend' / 'data' / 'etl_datalake.db'
    p2 = Path('data') / 'etl_datalake.db'
    if p1.exists():
        return p1
    return p2


def get_cached_coords(address: str):
    """Return (lat, lon) from geocode_cache table if present, else (None, None)."""
    if not address:
        return None, None
    import sqlite3
    p = _get_geocode_db_path()
    try:
        conn = sqlite3.connect(str(p))
        cur = conn.cursor()
        cur.execute('CREATE TABLE IF NOT EXISTS geocode_cache (address TEXT PRIMARY KEY, lat REAL, lon REAL, geocoded_at TEXT)')
        cur.execute('SELECT lat, lon FROM geocode_cache WHERE address = ? LIMIT 1', (address,))
        r = cur.fetchone()
        conn.close()
        if r:
            return r[0], r[1]
    except Exception:
        return None, None
    return None, None


def set_cached_coords(address: str, lat, lon):
    import sqlite3
    p = _get_geocode_db_path()
    try:
        conn = sqlite3.connect(str(p))
        cur = conn.cursor()
        cur.execute('CREATE TABLE IF NOT EXISTS geocode_cache (address TEXT PRIMARY KEY, lat REAL, lon REAL, geocoded_at TEXT)')
        from datetime import datetime, timezone
        cur.execute('REPLACE INTO geocode_cache(address, lat, lon, geocoded_at) VALUES(?,?,?,?)', (address, lat, lon, datetime.now(timezone.utc).isoformat()))
        conn.commit()
        conn.close()
    except Exception:
        pass


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
    df['__loaded_at'] = datetime.now(timezone.utc).isoformat()
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

    # --- Prepare barrio alias map early (used to detect Montevideo barrios) ---
    barrio_tokens = set()
    alias_map = {}
    fuzzy_choices = []
    label_map = {}
    if HAVE_HELPERS:
        try:
            alias_map, fuzzy_choices, barrio_tokens, label_map = load_denuncias_aliases(Path('datos') / 'denuncias_hurtos_por_10000_hab_montevideo.json')
        except Exception:
            barrio_tokens = set()
            alias_map = {}
            fuzzy_choices = []
    else:
        try:
            jpath = Path('datos') / 'denuncias_hurtos_por_10000_hab_montevideo.json'
            if jpath.exists():
                with open(jpath, 'r', encoding='utf-8') as fh:
                    payload = json.load(fh)
                data = payload.get('data', {})
                for key, item in data.items():
                    label = item.get('label', '')
                    if label:
                        barrio_tokens.add(re.sub(r"[^a-z0-9 ]+", ' ', normalize_text(label)).replace('_', ' '))
                    for a in item.get('aliases', []):
                        tok = re.sub(r"[^a-z0-9 ]+", ' ', normalize_text(a)).replace('_', ' ')
                        barrio_tokens.add(tok)
        except Exception:
            barrio_tokens = set()

    def _normalize_for_match(s):
        if HAVE_HELPERS:
            return helper_normalize_for_match(s)
        if not isinstance(s, str):
            return ''
        t = unicodedata.normalize('NFKD', s)
        t = ''.join(c for c in t if not unicodedata.combining(c))
        t = t.lower()
        t = re.sub(r'[^a-z0-9 ]+', ' ', t)
        t = re.sub(r'\s+', ' ', t).strip()
        return t

    # --- Step 1: Keep entries in Montevideo OR with a recognized barrio token ---
    if 'ubicacion' in df.columns:
        u_raw = df['ubicacion'].astype(str)
        mask_montevideo = u_raw.str.lower().str.contains('montevideo')

        def _has_barrio_token(u):
            up = _normalize_for_match(u)
            for tok in barrio_tokens:
                if not tok:
                    continue
                if tok in up:
                    return True
            # also handle patterns like 'apartamentos en pocitos' or 'casas en villa espanola'
            m = re.search(r'\ben\s+(?P<b>[^,\n]+)', u.lower())
            if m:
                cand = _normalize_for_match(m.group('b'))
                for tok in barrio_tokens:
                    if tok and tok in cand:
                        return True
            return False

        mask_alias = u_raw.apply(_has_barrio_token)
        mask = mask_montevideo | mask_alias
        logger.info(f"Filtrando filas: conservando {mask.sum()} de {len(df)} con Montevideo o barrio conocido en ubicacion")
        df = df[mask].reset_index(drop=True)

        # Clean common prefixes like 'Casas en', 'Apartamentos en' and remove literal 'Montevideo'
        df['ubicacion'] = df['ubicacion'].astype(str).str.replace(r'^(casas|apartamentos|locales|oficinas|apartamento|apto|alquiler)\s+en\s+', '', flags=re.IGNORECASE, regex=True)
        df['ubicacion'] = df['ubicacion'].astype(str).str.replace(r',?\s*montevideo\b', '', flags=re.IGNORECASE, regex=True).str.strip()

    # Also remove the literal 'Montevideo' from titulo if present
    title_cols = [c for c in df.columns if 'titulo' in c or 'title' in c]
    if title_cols:
        tcol = title_cols[0]
        df[tcol] = df[tcol].astype(str).str.replace(r'\bmontevideo\b', '', flags=re.IGNORECASE, regex=True).str.strip()

    # --- Step 2: Geocoding (before barrio imputation) ---
    def limpiar_ubicacion_para_geocodificacion(direccion):
        if HAVE_HELPERS:
            try:
                return helper_limpiar_ubicacion_para_geocodificacion(direccion)
            except Exception:
                pass
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
            # check cache first
            latc, lonc = get_cached_coords(q)
            if latc is not None and lonc is not None:
                return latc, lonc
            try:
                loc = geocode_rate(q)
                if loc:
                    lat, lon = loc.latitude, loc.longitude
                    # store in cache
                    try:
                        set_cached_coords(q, lat, lon)
                    except Exception:
                        pass
                    return lat, lon
            except Exception:
                return None, None
            return None, None

        for idx, val in df['ubicacion'].astype(str).items():
            lat, lon = try_geocode(val)
            df.at[idx, 'latitud'] = lat
            df.at[idx, 'longitud'] = lon
    except Exception:
        logger.info('geopy no disponible o error en geocodificación — continuando sin coordenadas')

    # --- Step 2b: contextual enrichment (distancias, zonas) if helper available ---
    if HAVE_CONTEXT_HELPER:
        try:
            logger.info('Intentando enrich_with_contextual_data (contextual)')
            df = helper_enrich_context(df)
        except Exception as e:
            logger.info(f'enrich_with_contextual_data falló: {e} -- continuando')

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
        if HAVE_HELPERS:
            try:
                return helper_extraer_dorms(titulo)
            except Exception:
                pass
        if not isinstance(titulo, str):
            return None
        t = titulo.lower()
        if 'monoambiente' in t or 'mono ambiente' in t or 'studio' in t:
            return 1
        m = re.search(r'(\d+)\s*(dorm|hab|amb)', t)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                return None
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
    # ensure alias_map and fuzzy_choices exist (may have been loaded above)
    if not alias_map:
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
        except Exception:
            alias_map = {}

    if not fuzzy_choices:
        fuzzy_choices = list(alias_map.keys()) if alias_map else []

    def _local_guess_barrio(ubic):
        if not isinstance(ubic, str) or not ubic:
            return None
        u_norm = _normalize_for_match(ubic)

        # 1) Exact/substring match (fast)
        parts = [p.strip() for p in ubic.split(',') if p.strip()]
        for idx in [0, 1, 2, -1]:
            if len(parts) > idx and idx >= -len(parts):
                cand = normalize_text(parts[idx])
                if cand in alias_map:
                    return alias_map[cand]
        for a, v in alias_map.items():
            if a and a in u_norm:
                return v

        # 2) fallback: prefer helper fuzzy then local rapidfuzz
        if HAVE_HELPERS:
            try:
                return helper_guess_barrio(ubic, alias_map, fuzzy_choices, logger)
            except Exception:
                pass
        if HAVE_RAPIDFUZZ and fuzzy_choices:
            try:
                best = rf_process.extractOne(u_norm, fuzzy_choices, scorer=rf_fuzz.partial_ratio)
                if best and best[1] >= 78:
                    return alias_map.get(best[0])
                for tok in u_norm.split():
                    if len(tok) < 3:
                        continue
                    best = rf_process.extractOne(tok, fuzzy_choices, scorer=rf_fuzz.partial_ratio)
                    if best and best[1] >= 85:
                        return alias_map.get(best[0])
            except Exception:
                pass

        return None

    for idx, row in df.iterrows():
        ubic = row.get('ubicacion') if 'ubicacion' in df.columns else None
        barrio = _local_guess_barrio(ubic)
        barrio_norm.append(barrio)

    df['barrio_guess'] = barrio_norm

    # --- Step 6: asignar nivel_criminalidad (baja/media/alta) usando datos de denuncias ---
    try:
        jpath = Path('datos') / 'denuncias_hurtos_por_10000_hab_montevideo.json'
        if jpath.exists():
            with open(jpath, 'r', encoding='utf-8') as fh:
                payload = json.load(fh)
            denuncia_data = payload.get('data', {})
        else:
            denuncia_data = {}

        niveles = []
        for idx, row in df.iterrows():
            barrio = row.get('barrio_guess')
            nivel = None
            if barrio and barrio in denuncia_data:
                try:
                    v = float(denuncia_data[barrio].get('value', denuncia_data[barrio].get('valor', None)))
                    # thresholds: baja <= 70, media <= 140, alta > 140 (tunable)
                    if v <= 70:
                        nivel = 'baja'
                    elif v <= 140:
                        nivel = 'media'
                    else:
                        nivel = 'alta'
                except Exception:
                    nivel = None
            niveles.append(nivel)
        df['nivel_criminalidad'] = niveles
    except Exception:
        df['nivel_criminalidad'] = None

    # --- Step 7: fallback para 'url' cuando falta — intentar extraer item id desde imagen (MLU...)
    try:
        if 'url' not in df.columns:
            df['url'] = None

        # If url column is entirely null/empty, try to build a plausible MercadoLibre item URL
        if df['url'].isna().all():
            def _extract_ml_item(img_url):
                if not isinstance(img_url, str):
                    return None
                m = re.search(r'(MLU\d+)', img_url)
                if m:
                    return f'https://articulo.mercadolibre.com.uy/{m.group(1)}'
                return None

            df['url'] = df.apply(lambda r: r['url'] if pd.notna(r.get('url')) and str(r.get('url')).strip() else _extract_ml_item(r.get('imagen_url')), axis=1)
    except Exception:
        # don't block the rest of the transform if something goes wrong here
        pass

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
def etl_flow(sqlite_path: str = None):
    logger = get_run_logger()
    logger.info(f"Metadata flow: {METADATA}")

    # asegurar carpeta de datos
    (DATA_DIR / 'data').mkdir(exist_ok=True)
    # allow overriding the sqlite path for testing / dry-run
    if sqlite_path:
        engine_url = f"sqlite:///{Path(sqlite_path).as_posix()}"
    else:
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


@task
def run_script(cmd: str):
    """Run an external script/command and stream output to logger."""
    logger = get_run_logger()
    logger.info(f'Running: {cmd}')
    try:
        # Use shell=True to avoid Windows path/tokenization issues and allow full command strings.
        # This is acceptable because the commands we run are internal project scripts.
        proc = subprocess.run(cmd, check=True, capture_output=True, text=True, shell=True)
        if proc.stdout:
            logger.info(proc.stdout)
        if proc.stderr:
            logger.warning(proc.stderr)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f'Command failed: {e}; stderr: {e.stderr}')
        return False


@flow(name='full_etl_pipeline_prefect')
def full_etl_pipeline(db_path: str = None, gallito_limit: int = None, dry_run: bool = False):
    """Full ETL pipeline orchestrated with Prefect.

    Steps:
      1) Optionally run scrapers to refresh raw CSVs
      2) Clean Gallito addresses
      3) Batch geocode cleaned addresses (uses geocode_cache)
      4) Run ETL flow (ingest + transform -> transformed_listings)
      5) Run contextual enrichment (if available)
      6) Load denuncias and join crime mapping
      7) Archive rows without coordinates
    """
    logger = get_run_logger()
    logger.info('Starting full ETL pipeline (Prefect)')

    dbp = Path(db_path) if db_path else SQLITE_PATH

    PY = shutil.which('python') or 'python'

    # 1) Scrapers (optional) -- run Mercadolibre and Gallito detail
    if not dry_run:
        # numeric-prefixed wrappers under iDatos/backend/scripts
        run_script(f"{PY} iDatos/backend/scripts/01_mercadolibre_scraper.py")
        cmd_g = f"{PY} iDatos/backend/scripts/02_gallito_detail_scraper.py"
        if gallito_limit:
            cmd_g += f" --limit {gallito_limit}"
        run_script(cmd_g)
    else:
        logger.info('Dry-run: skipping scrapers')

    # 2) Clean Gallito addresses
    if not dry_run:
        run_script(f"{PY} iDatos/backend/scripts/03_clean_gallito_addresses.py --input gallito_alquileres_crudos.with_addr.csv")
    else:
        logger.info('Dry-run: skipping clean_gallito_addresses')

    # 3) Geocode batch
    if not dry_run:
        run_script(f"{PY} iDatos/backend/scripts/04_geocode_batch.py --delay 1.0 --sources gallito_alquileres_crudos.with_addr.cleaned.csv")
        # retry unresolved using geocode.xyz script
        run_script(f"{PY} iDatos/backend/scripts/05_geocode_xyz_retry.py --failed geocode_failed_*.csv --delay 1.2")
    else:
        logger.info('Dry-run: skipping geocoding')

    # 4) Run the ETL flow (ingest + transform)
    logger.info('Running etl_flow (ingest + transform)')
    # pass the db path used by the full pipeline to ensure both write/read use same DB
    etl_flow(sqlite_path=dbp.as_posix())

    # 5) Contextual enrichment (attempt to run helper if available)
    if HAVE_CONTEXT_HELPER:
        try:
            logger.info('Attempting contextual enrichment via helper')
            import sqlite3
            import pandas as pd
            conn = sqlite3.connect(str(dbp))
            df = pd.read_sql_query('SELECT * FROM transformed_listings', conn)
            conn.close()
            df2 = helper_enrich_context(df)
            engine_url = f"sqlite:///{dbp.as_posix()}"
            write_transformed_to_sql(df2, engine_url)
        except Exception as e:
            logger.warning(f'Contextual enrichment failed: {e}')

    # 6) Load denuncias and join
    if not dry_run:
        run_script(f"{PY} iDatos/backend/scripts/07_load_denuncias_crime.py --db {dbp.as_posix()}")
        run_script(f"{PY} iDatos/backend/scripts/08_join_crime_to_transformed.py --db {dbp.as_posix()}")
    else:
        logger.info('Dry-run: skipping load/join of denuncias')

    # 7) Archive null coords
    if not dry_run:
        run_script(f"{PY} iDatos/backend/scripts/09_archive_null_coords.py --db {dbp.as_posix()} --move")
    else:
        logger.info('Dry-run: skipping archive_null_coords')

    logger.info('Full ETL pipeline finished')


if __name__ == '__main__':
    etl_flow()
