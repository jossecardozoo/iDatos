"""
Utilidades para el pipeline ETL: normalización, geocodificación y cache.
"""
import unicodedata
import re
import sqlite3
from pathlib import Path
from typing import Tuple, Optional
from datetime import datetime, timezone

from .config import (
    GEOCODE_CACHE_TABLE,
    GEOCODE_USER_AGENT,
    GEOCODE_TIMEOUT,
    GEOCODE_MIN_DELAY,
)


def normalize_text(s: str) -> str:
    """Normaliza texto eliminando acentos y caracteres especiales."""
    if not isinstance(s, str):
        return ''
    s = s.lower().strip()
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", '_', s)
    s = re.sub(r'_+', '_', s)
    return s.strip('_')


def normalize_for_match(s: str) -> str:
    """Normaliza texto para comparación fuzzy (preserva espacios)."""
    if not isinstance(s, str):
        return ''
    t = unicodedata.normalize('NFKD', s)
    t = ''.join(c for c in t if not unicodedata.combining(c))
    t = t.lower()
    t = re.sub(r'[^a-z0-9 ]+', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def limpiar_ubicacion_para_geocodificacion(direccion: str) -> str:
    """Limpia la dirección para mejorar la tasa de éxito de geocodificación."""
    if not isinstance(direccion, str):
        return ''
    parte_principal = direccion.split(',')[0].strip()
    parte_principal = re.sub(r'\s*/\s*\d+\s*$', '', parte_principal)
    parte_principal = re.sub(r'\s*Esq\.?\s*', ' and ', parte_principal, flags=re.IGNORECASE)
    parte_principal = re.sub(r'\s*esquina\s*', ' and ', parte_principal, flags=re.IGNORECASE)
    parte_principal = re.sub(r'\s{2,}', ' ', parte_principal).strip()
    return parte_principal.strip()


def _get_geocode_db_path() -> Path:
    """Retorna la ruta a la base de datos SQLite del datalake para el cache de geocodificación."""
    p1 = Path('iDatos') / 'backend' / 'data' / 'etl_datalake.db'
    p2 = Path('data') / 'etl_datalake.db'
    if p1.exists():
        return p1
    return p2


def get_cached_coords(address: str) -> Tuple[Optional[float], Optional[float]]:
    """Retorna (lat, lon) desde la tabla geocode_cache si existe, sino (None, None)."""
    if not address:
        return None, None
    p = _get_geocode_db_path()
    try:
        conn = sqlite3.connect(str(p))
        cur = conn.cursor()
        cur.execute(
            f'CREATE TABLE IF NOT EXISTS {GEOCODE_CACHE_TABLE} '
            '(address TEXT PRIMARY KEY, lat REAL, lon REAL, geocoded_at TEXT)'
        )
        cur.execute(
            f'SELECT lat, lon FROM {GEOCODE_CACHE_TABLE} WHERE address = ? LIMIT 1',
            (address,)
        )
        r = cur.fetchone()
        conn.close()
        if r:
            return r[0], r[1]
    except Exception:
        return None, None
    return None, None


def set_cached_coords(address: str, lat: float, lon: float) -> None:
    """Guarda coordenadas en el cache de geocodificación."""
    p = _get_geocode_db_path()
    try:
        conn = sqlite3.connect(str(p))
        cur = conn.cursor()
        cur.execute(
            f'CREATE TABLE IF NOT EXISTS {GEOCODE_CACHE_TABLE} '
            '(address TEXT PRIMARY KEY, lat REAL, lon REAL, geocoded_at TEXT)'
        )
        cur.execute(
            f'REPLACE INTO {GEOCODE_CACHE_TABLE}(address, lat, lon, geocoded_at) VALUES(?,?,?,?)',
            (address, lat, lon, datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def try_geocode(ubic: str, use_cache: bool = True) -> Tuple[Optional[float], Optional[float]]:
    """Intenta geocodificar una ubicación usando cache y Nominatim."""
    try:
        from geopy.geocoders import Nominatim
        from geopy.extra.rate_limiter import RateLimiter
    except ImportError:
        return None, None

    q = limpiar_ubicacion_para_geocodificacion(ubic) + ', Montevideo, Uruguay'
    
    # Verificar cache primero
    if use_cache:
        latc, lonc = get_cached_coords(q)
        if latc is not None and lonc is not None:
            return latc, lonc

    try:
        geolocator = Nominatim(user_agent=GEOCODE_USER_AGENT, timeout=GEOCODE_TIMEOUT)
        geocode_rate = RateLimiter(geolocator.geocode, min_delay_seconds=GEOCODE_MIN_DELAY)
        loc = geocode_rate(q)
        if loc:
            lat, lon = loc.latitude, loc.longitude
            if use_cache:
                set_cached_coords(q, lat, lon)
            return lat, lon
    except Exception:
        pass
    return None, None

