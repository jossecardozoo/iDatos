"""
Transformaciones de datos: limpieza, normalización, geocodificación, enriquecimiento.

Todas las transformaciones están implementadas como funciones que pueden ser llamadas
dentro de tasks de Prefect para mejor trazabilidad.
"""
import json
import re
import pandas as pd
from pathlib import Path
from typing import Optional
import time

from prefect import task, get_run_logger

from .config import TASAS_DE_CAMBIO, DENUNCIAS_JSON_PATH
from .provenance import get_provenance_tracker, track_data_hash
from .utils import (
    normalize_text,
    normalize_for_match,
    limpiar_ubicacion_para_geocodificacion,
    try_geocode,
)

# Intentar importar helpers opcionales
HAVE_HELPERS = False
HAVE_CONTEXT_HELPER = False

try:
    from scripts.transformaciones.transform_helpers import (
        load_denuncias_aliases,
        guess_barrio as helper_guess_barrio,
        extraer_dorms as helper_extraer_dorms,
    )
    HAVE_HELPERS = True
except Exception:
    try:
        # Fallback: intentar importar desde la ruta relativa
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from transform_helpers import (
            load_denuncias_aliases,
            guess_barrio as helper_guess_barrio,
            extraer_dorms as helper_extraer_dorms,
        )
        HAVE_HELPERS = True
    except Exception:
        HAVE_HELPERS = False

# Intentar importar enriquecimiento contextual
try:
    from scripts.transformaciones.datos_contextuales import enrich_with_contextual_data as helper_enrich_context
    HAVE_CONTEXT_HELPER = True
except Exception:
    try:
        from scripts.datos_contextuales import enrich_with_contextual_data as helper_enrich_context
        HAVE_CONTEXT_HELPER = True
    except Exception:
        try:
            # Fallback: intentar importar desde la ruta relativa
            import sys
            from pathlib import Path
            if 'scripts' not in sys.path:
                sys.path.insert(0, str(Path(__file__).parent.parent))
            from datos_contextuales import enrich_with_contextual_data as helper_enrich_context
            HAVE_CONTEXT_HELPER = True
        except Exception:
            HAVE_CONTEXT_HELPER = False


def filter_montevideo_properties(df: pd.DataFrame, barrio_tokens: set, logger=None) -> pd.DataFrame:
    """Filtra propiedades que están en Montevideo o tienen un barrio reconocido."""
    if df.empty or 'ubicacion' not in df.columns:
        return df

    u_raw = df['ubicacion'].astype(str)
    mask_montevideo = u_raw.str.lower().str.contains('montevideo')

    def _has_barrio_token(u):
        up = normalize_for_match(u)
        for tok in barrio_tokens:
            if not tok:
                continue
            if tok in up:
                return True
        # Manejar patrones como 'apartamentos en pocitos'
        m = re.search(r'\ben\s+(?P<b>[^,\n]+)', u.lower())
        if m:
            cand = normalize_for_match(m.group('b'))
            for tok in barrio_tokens:
                if tok and tok in cand:
                    return True
        return False

    mask_alias = u_raw.apply(_has_barrio_token)
    mask = mask_montevideo | mask_alias
    
    if logger:
        logger.info(f"Filtrando filas: conservando {mask.sum()} de {len(df)} con Montevideo o barrio conocido en ubicacion")
    
    df = df[mask].reset_index(drop=True)

    # Limpiar prefijos comunes
    df['ubicacion'] = df['ubicacion'].astype(str).str.replace(
        r'^(casas|apartamentos|locales|oficinas|apartamento|apto|alquiler)\s+en\s+',
        '', flags=re.IGNORECASE, regex=True
    )
    df['ubicacion'] = df['ubicacion'].astype(str).str.replace(
        r',?\s*montevideo\b', '', flags=re.IGNORECASE, regex=True
    ).str.strip()

    # Remover 'Montevideo' del título
    title_cols = [c for c in df.columns if 'titulo' in c or 'title' in c]
    if title_cols:
        tcol = title_cols[0]
        df[tcol] = df[tcol].astype(str).str.replace(
            r'\bmontevideo\b', '', flags=re.IGNORECASE, regex=True
        ).str.strip()

    return df


def geocode_addresses(df: pd.DataFrame, logger=None) -> pd.DataFrame:
    """Geocodifica direcciones en el DataFrame."""
    if df.empty or 'ubicacion' not in df.columns:
        return df

    df = df.copy()
    df['latitud'] = None
    df['longitud'] = None

    for idx, val in df['ubicacion'].astype(str).items():
        lat, lon = try_geocode(val, use_cache=True)
        df.at[idx, 'latitud'] = lat
        df.at[idx, 'longitud'] = lon

    if logger:
        geocoded_count = df['latitud'].notna().sum()
        logger.info(f'Geocodificadas {geocoded_count} de {len(df)} direcciones')

    return df


def enrich_with_contextual_data(df: pd.DataFrame, logger=None) -> pd.DataFrame:
    """Enriquece el DataFrame con datos contextuales (distancias, zonas)."""
    if HAVE_CONTEXT_HELPER:
        try:
            if logger:
                logger.info('Intentando enrich_with_contextual_data (contextual)')
            return helper_enrich_context(df)
        except Exception as e:
            if logger:
                logger.info(f'enrich_with_contextual_data falló: {e} -- continuando')
    return df


def normalize_prices(df: pd.DataFrame, logger=None) -> pd.DataFrame:
    """Normaliza precios extrayendo valores numéricos y convirtiendo a UYU."""
    if df.empty:
        return df

    df = df.copy()

    # Extraer valor numérico del precio
    for col in ['precio_valor', 'price', 'valor']:
        if col in df.columns:
            df['precio_valor_num'] = pd.to_numeric(
                df[col].astype(str).str.replace(r"[^0-9]", '', regex=True),
                errors='coerce'
            )
            break
    if 'precio_valor_num' not in df.columns:
        df['precio_valor_num'] = pd.Series([None] * len(df))

    # Normalizar moneda
    moneda_col = None
    for c in ['precio_moneda', 'moneda', 'currency']:
        if c in df.columns:
            moneda_col = c
            break
    df['precio_moneda_normalizada'] = (
        df[moneda_col].astype(str).str.upper().fillna('N/A')
        if moneda_col else 'N/A'
    )

    # Convertir a UYU
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
    return df


def impute_dorms(df: pd.DataFrame, logger=None) -> pd.DataFrame:
    """Imputa cantidad de dormitorios desde el título."""
    if df.empty:
        return df

    df = df.copy()

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
        map_num = {'un': 1, 'uno': 1, 'una': 1, 'dos': 2, 'tres': 3, 'cuatro': 4}
        if m2:
            return map_num.get(m2.group(1), None)
        return None

    title_cols = [c for c in df.columns if 'titulo' in c or 'title' in c]
    if title_cols:
        df['dorms_imputado'] = df[title_cols[0]].apply(extraer_dorms)
    else:
        df['dorms_imputado'] = None

    return df


def impute_barrio(df: pd.DataFrame, logger=None) -> pd.DataFrame:
    """Imputa barrio usando aliases de denuncias."""
    if df.empty:
        return df

    df = df.copy()

    # Cargar aliases
    alias_map = {}
    fuzzy_choices = []
    barrio_tokens = set()
    label_map = {}

    if HAVE_HELPERS:
        try:
            alias_map, fuzzy_choices, barrio_tokens, label_map = load_denuncias_aliases(DENUNCIAS_JSON_PATH)
        except Exception:
            pass

    if not alias_map:
        try:
            if DENUNCIAS_JSON_PATH.exists():
                with open(DENUNCIAS_JSON_PATH, 'r', encoding='utf-8') as fh:
                    payload = json.load(fh)
                data = payload.get('data', {})
                for key, item in data.items():
                    label = item.get('label')
                    if label:
                        norm_key = normalize_text(label)
                        label_map[norm_key] = label
                        alias_map[norm_key] = norm_key
                        barrio_tokens.add(normalize_for_match(label))
                        for a in item.get('aliases', []):
                            alias_map[normalize_text(a)] = norm_key
        except Exception:
            pass

    if not fuzzy_choices:
        fuzzy_choices = list(alias_map.keys()) if alias_map else []

    def _local_guess_barrio(ubic):
        if not isinstance(ubic, str) or not ubic:
            return None
        u_norm = normalize_for_match(ubic)

        # Match exacto/substring
        parts = [p.strip() for p in ubic.split(',') if p.strip()]
        for idx in [0, 1, 2, -1]:
            if len(parts) > idx and idx >= -len(parts):
                cand = normalize_text(parts[idx])
                if cand in alias_map:
                    return alias_map[cand]
        for a, v in alias_map.items():
            if a and a in u_norm:
                return v

        # Fuzzy matching
        if HAVE_HELPERS:
            try:
                return helper_guess_barrio(ubic, alias_map, fuzzy_choices, logger)
            except Exception:
                pass

        # Fallback con rapidfuzz
        try:
            from rapidfuzz import process as rf_process, fuzz as rf_fuzz
            if fuzzy_choices:
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

    barrio_norm = []
    for idx, row in df.iterrows():
        ubic = row.get('ubicacion') if 'ubicacion' in df.columns else None
        barrio = _local_guess_barrio(ubic)
        barrio_norm.append(barrio)

    df['barrio_guess'] = barrio_norm
    return df


def assign_crime_level(df: pd.DataFrame, logger=None) -> pd.DataFrame:
    """Asigna nivel de criminalidad (baja/media/alta) usando datos de denuncias."""
    if df.empty:
        return df

    df = df.copy()

    try:
        if DENUNCIAS_JSON_PATH.exists():
            with open(DENUNCIAS_JSON_PATH, 'r', encoding='utf-8') as fh:
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
                    # thresholds: baja <= 70, media <= 140, alta > 140
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

    return df


def extract_url_from_image(df: pd.DataFrame, logger=None) -> pd.DataFrame:
    """Extrae URL desde imagen cuando falta (para MercadoLibre)."""
    if df.empty:
        return df

    df = df.copy()

    try:
        if 'url' not in df.columns:
            df['url'] = None

        if df['url'].isna().all():
            def _extract_ml_item(img_url):
                if not isinstance(img_url, str):
                    return None
                m = re.search(r'(MLU\d+)', img_url)
                if m:
                    return f'https://articulo.mercadolibre.com.uy/{m.group(1)}'
                return None

            df['url'] = df.apply(
                lambda r: r['url'] if pd.notna(r.get('url')) and str(r.get('url')).strip()
                else _extract_ml_item(r.get('imagen_url')),
                axis=1
            )
    except Exception:
        pass

    return df


@task(
    name="transform_df",
    retries=1,
    retry_delay_seconds=10,
    log_prints=True,
    tags=["transform", "data_quality"]
)
def transform_df(df: pd.DataFrame, logger=None) -> pd.DataFrame:
    """
    Task de Prefect que aplica todas las transformaciones al DataFrame.
    
    Transformaciones aplicadas:
    1. Filtrado de propiedades en Montevideo
    2. Geocodificación de direcciones
    3. Enriquecimiento contextual (distancias, zonas)
    4. Normalización de precios a UYU
    5. Imputación de dormitorios desde título
    6. Imputación de barrio usando aliases
    7. Asignación de nivel de criminalidad
    8. Extracción de URL desde imagen
    
    Args:
        df: DataFrame con datos crudos
        logger: Logger opcional
        
    Returns:
        DataFrame transformado
    """
    if logger is None:
        logger = get_run_logger()
    
    start_time = time.time()
    rows_before = len(df)
    data_hash_before = track_data_hash(df) if not df.empty else None
    
    if df.empty:
        logger.warning("DataFrame vacío recibido para transformación")
        return df

    df = df.copy()

    # Normalizar nombres de columnas
    df.columns = [normalize_text(str(c)) for c in df.columns]

    # Cargar barrio tokens para filtrado
    barrio_tokens = set()
    if HAVE_HELPERS:
        try:
            _, _, barrio_tokens, _ = load_denuncias_aliases(DENUNCIAS_JSON_PATH)
        except Exception:
            pass
    else:
        try:
            if DENUNCIAS_JSON_PATH.exists():
                with open(DENUNCIAS_JSON_PATH, 'r', encoding='utf-8') as fh:
                    payload = json.load(fh)
                data = payload.get('data', {})
                for key, item in data.items():
                    label = item.get('label', '')
                    if label:
                        barrio_tokens.add(normalize_for_match(label))
                    for a in item.get('aliases', []):
                        barrio_tokens.add(normalize_for_match(a))
        except Exception:
            pass

    # Paso 1: Filtrar propiedades de Montevideo
    df = filter_montevideo_properties(df, barrio_tokens, logger)

    # Paso 2: Geocodificación
    df = geocode_addresses(df, logger)

    # Paso 2b: Enriquecimiento contextual
    df = enrich_with_contextual_data(df, logger)

    # Paso 3: Normalización de precios
    df = normalize_prices(df, logger)

    # Paso 4: Imputación de dormitorios
    df = impute_dorms(df, logger)

    # Paso 5: Imputación de barrio
    df = impute_barrio(df, logger)

    # Paso 6: Asignar nivel de criminalidad
    df = assign_crime_level(df, logger)

    # Paso 7: Extraer URL desde imagen
    df = extract_url_from_image(df, logger)

    # Preservar columnas de metadata antes de normalizar
    metadata_cols = ['__source_file', '__source_path', '__loaded_at', '__encoding_used']
    preserved_metadata = {}
    for col in metadata_cols:
        if col in df.columns:
            preserved_metadata[col] = df[col].copy()
    
    # Normalización final de columnas
    df.columns = [normalize_text(str(c)) for c in df.columns]
    
    # Restaurar columnas de metadata con nombres normalizados
    for orig_col in metadata_cols:
        norm_col = normalize_text(orig_col)
        if orig_col in preserved_metadata and norm_col not in df.columns:
            df[norm_col] = preserved_metadata[orig_col]
    
    execution_time = time.time() - start_time
    rows_after = len(df)
    data_hash_after = track_data_hash(df) if not df.empty else None
    
    # Registrar transformación en provenance
    tracker = get_provenance_tracker()
    tracker.log_data_transformation(
        operation='full_transform_pipeline',
        source_file=df.get('__source_file').iloc[0] if '__source_file' in df.columns and len(df) > 0 else 'unknown',
        rows_before=rows_before,
        rows_after=rows_after,
        columns_added=[c for c in df.columns if c not in ['__source_file', '__loaded_at']],
        filters_applied={'montevideo_filter': rows_before - rows_after}
    )
    
    tracker.log_task(
        task_name="transform_df",
        input_data={'rows': rows_before, 'data_hash': data_hash_before},
        output_data={
            'rows': rows_after,
            'data_hash': data_hash_after,
            'columns_count': len(df.columns),
            'filters_applied': rows_before - rows_after
        },
        execution_time=execution_time
    )
    
    logger.info(
        f"Transformación completada: {rows_after} filas "
        f"(filtradas {rows_before - rows_after}) en {execution_time:.2f}s"
    )

    return df

