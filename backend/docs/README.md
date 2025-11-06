# Documentación del Pipeline ETL

## Estructura del Proyecto

```
backend/
├── scripts/
│   ├── etl/                      # Módulos ETL refactorizados
│   │   ├── __init__.py
│   │   ├── config.py             # Configuración y constantes
│   │   ├── utils.py              # Utilidades (normalización, geocodificación)
│   │   ├── loaders.py            # Carga de datos (CSV, SQL)
│   │   ├── transformers.py       # Transformaciones de datos
│   │   ├── deduplication.py      # Detección de duplicados cross-portal
│   │   └── provenance.py         # Trazabilidad (Data Provenance)
│   ├── etl_functions_prefect.py  # Pipeline principal con Prefect
│   ├── 01_mercadolibre_scraper.py
│   ├── 02_gallito_detail_scraper.py
│   ├── 03_clean_gallito_addresses.py
│   ├── 04_geocode_batch.py
│   ├── 05_geocode_xyz_retry.py
│   ├── 07_load_denuncias_crime.py
│   ├── 08_join_crime_to_transformed.py
│   ├── 09_archive_null_coords.py
│   └── organize_data_files.py    # Utilidad para organizar CSVs
├── data/
│   ├── raw/                      # Datos crudos de scraping
│   ├── processed/                # Datos transformados
│   ├── intermediate/             # Archivos intermedios
│   ├── archive/                  # Archivos archivados
│   ├── provenance/               # Metadata de trazabilidad
│   └── etl_datalake.db           # Base de datos SQLite
├── docs/
│   ├── README.md                 # Este archivo
│   └── TECNICAS_INTEGRACION.md   # Documentación técnica
└── README.md                     # README principal
```

## Uso del Pipeline

### Ejecución Básica

El pipeline ETL básico procesa CSVs existentes en `data/raw/`:

```bash
# Ejecutar pipeline básico (usa data/etl_datalake.db por defecto)
cd backend
python scripts/run_etl.py

# Con ruta personalizada de base de datos
python scripts/run_etl.py --db-path data/custom_database.db
```

### Pipeline Completo

El pipeline completo incluye scrapers y geocodificación:

```bash
# Ejecutar pipeline completo (incluye scrapers)
python scripts/run_full_pipeline.py

# Con límite de registros para Gallito
python scripts/run_full_pipeline.py --gallito-limit 50

# Modo dry-run (sin scrapers ni geocodificación, solo procesa CSVs existentes)
python scripts/run_full_pipeline.py --dry-run

# Combinar opciones
python scripts/run_full_pipeline.py --db-path data/test_db.db --gallito-limit 100 --dry-run
```

### Exportar Datos a Texto

Después de ejecutar el pipeline, puedes generar archivos de texto para visualización:

```bash
# Exportar todas las tablas principales
python scripts/dump_db_to_txt.py

# Exportar solo duplicados cross-portal
python scripts/export_cross_portal_duplicates.py

# Ver información de duplicados en consola
python scripts/view_duplicates.py
```


### Scripts de Visualización

- `scripts/view_duplicates.py`: Muestra información sobre duplicados detectados en la consola
- `scripts/export_cross_portal_duplicates.py`: Exporta duplicados cross-portal a `data/duplicados_cross_portal.txt`
- `scripts/dump_db_to_txt.py`: Exporta todas las tablas principales a archivos de texto

## Archivos de Texto Exportados

En la carpeta `data/` se generan automáticamente archivos de texto para visualización:

### Archivos Generados por `dump_db_to_txt.py`

- **`raw_listings.txt`**: Datos crudos de todos los portales (tabla `raw_listings`)
  - Contiene: URL, título, ubicación, precio, imagen, fuente, metadatos de carga
  - Uso: Revisar datos originales antes de transformación

- **`transformed_listings.txt`**: Datos transformados y enriquecidos (tabla `transformed_listings`)
  - Contiene: Todos los campos transformados, coordenadas geocodificadas, datos contextuales, precio normalizado
  - Uso: Ver datos finales listos para análisis y visualización

### Archivos Generados por `export_cross_portal_duplicates.py`

- **`duplicados_cross_portal.txt`**: Reporte detallado de duplicados entre portales
  - Contiene: Registros movidos, pares de duplicados, estadísticas por fuente
  - Uso: Análisis de duplicados cross-portal, verificación de calidad de datos


## Trazabilidad (Data Provenance)

El sistema registra automáticamente:

- **Runs**: Cada ejecución tiene un ID único
- **Tasks**: Todas las tareas registran entrada/salida
- **Transformaciones**: Cambios en datos (filas, columnas)
- **Duplicados**: Detección y movimiento de duplicados cross-portal
- **Estadísticas**: Métricas de cada ejecución

Los metadatos se guardan en `data/provenance/` como archivos JSON.

### Consultar Trazabilidad

```python
from scripts.etl.provenance import get_provenance_tracker
import json

# Cargar metadata de un run
run_id = "etl_flow_prefect_abc123"
metadata_file = Path("data/provenance") / f"{run_id}_metadata.json"

with open(metadata_file) as f:
    metadata = json.load(f)
    
print(json.dumps(metadata, indent=2))
```

## Estructura de la Base de Datos

La base de datos SQLite (`data/etl_datalake.db`) contiene:

### Tablas Principales

- **`raw_listings`**: Datos crudos de todos los portales (Data Lake)
  - Preserva datos originales sin modificar
  - Incluye metadatos de carga (fuente, fecha, encoding)

- **`transformed_listings`**: Datos transformados y enriquecidos (Data Warehouse)
  - Datos listos para análisis y visualización
  - Incluye coordenadas, datos contextuales, precios normalizados
  - Contiene todos los registros (incluyendo duplicados del mismo portal)

- **`duplicates_moved`**: Registros de duplicados cross-portal movidos
  - Solo contiene duplicados entre diferentes portales
  - Incluye campos `moved_at` y `reason` para trazabilidad
  - Estos registros fueron detectados por coordenadas exactamente iguales

- **`duplicates_detected`**: Metadatos de duplicados cross-portal detectados
  - Información sobre pares de duplicados (primary/duplicate)
  - Distancias, fuentes, títulos, ubicaciones
  - Solo contiene duplicados cross-portal (ignora duplicados del mismo portal)

- **`geocode_cache`**: Cache de geocodificación para optimizar llamadas
  - Reduce llamadas repetidas a servicios de geocodificación
  - Mejora performance del pipeline

## Configuración

Editar `scripts/etl/config.py` para:

- Cambiar rutas de carpetas
- Ajustar tasas de conversión de monedas
- Modificar umbral de distancia para detección (actualmente solo coordenadas exactas)
- Configurar parámetros de geocodificación

## Referencias

- [Documentación Técnica](./TECNICAS_INTEGRACION.md)
- [Prefect Documentation](https://docs.prefect.io/)
- [Principios FAIR](https://www.go-fair.org/fair-principles/)

