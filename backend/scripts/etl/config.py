"""
Configuración y constantes para el pipeline ETL.
"""
from pathlib import Path

# Directorio base
DATA_DIR = Path(".")
BASE_DIR = DATA_DIR.parent if DATA_DIR.name == 'backend' else DATA_DIR

# Estructura de carpetas organizada
RAW_DATA_DIR = BASE_DIR / "data" / "raw"          # Datos crudos de scraping
PROCESSED_DATA_DIR = BASE_DIR / "data" / "processed"  # Datos transformados
INTERMEDIATE_DATA_DIR = BASE_DIR / "data" / "intermediate"  # Archivos intermedios
ARCHIVE_DATA_DIR = BASE_DIR / "data" / "archive"   # Archivos archivados
PROVENANCE_DIR = BASE_DIR / "data" / "provenance"  # Metadata de trazabilidad

# Crear carpetas si no existen
for dir_path in [RAW_DATA_DIR, PROCESSED_DATA_DIR, INTERMEDIATE_DATA_DIR, ARCHIVE_DATA_DIR, PROVENANCE_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

# Base de datos SQLite
SQLITE_PATH = BASE_DIR / "data" / "etl_datalake.db"

# Archivos CSV candidatos para procesamiento
# Busca en múltiples ubicaciones: raíz, raw/, y processed/
CSV_CANDIDATES = []
# Agregar archivos desde raw/
if RAW_DATA_DIR.exists():
    CSV_CANDIDATES.extend(list(RAW_DATA_DIR.glob("*.csv")))
# Agregar archivos legacy desde raíz (para compatibilidad)
BASE_DIR_CSVS = [
    "mercadolibre_alquileres_con_imagen.csv",
    "gallito_alquileres_crudos.csv",
    "infocasas_datos.csv",
]
CSV_CANDIDATES.extend([BASE_DIR / f for f in BASE_DIR_CSVS])

# Metadata del pipeline
METADATA = {
    "name": "etl_functions_prefect",
    "description": "ETL que carga crudos a SQLite (datalake) y guarda transformados (datawarehouse)",
    "author": "iDatos team",
    "date_created": "2025-11-04",
    "version": "2.1.0",
    "principles": ["FAIR", "Data Provenance", "Traceability"],
}

# Tasas de conversión de monedas a UYU
TASAS_DE_CAMBIO = {
    'UYU': 1.0,
    'USD': 39.93,
    'U$S': 39.93,
    '$': 1.0,
    'ARS': 0.0278,
    'N/A': 1.0,
}

# Configuración de detección de duplicados
DUPLICATE_SIMILARITY_THRESHOLD = 85  # Umbral de similaridad (0-100) - No usado en detección por coordenadas
DUPLICATE_DISTANCE_THRESHOLD = 50  # Distancia en metros para considerar duplicados por coordenadas

# Configuración de geocodificación
GEOCODE_CACHE_TABLE = 'geocode_cache'
GEOCODE_USER_AGENT = 'idatos_etl_geocoder'
GEOCODE_TIMEOUT = 10
GEOCODE_MIN_DELAY = 1.0

# Rutas de datos contextuales
DENUNCIAS_JSON_PATH = Path('datos') / 'denuncias_hurtos_por_10000_hab_montevideo.json'

# Configuración Prefect
PREFECT_RETRY_ATTEMPTS = 3
PREFECT_RETRY_DELAY = 5  # segundos
PREFECT_TASK_TIMEOUT = 3600  # 1 hora en segundos
