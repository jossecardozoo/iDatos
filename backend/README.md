# iDatos — ETL, normalización y carga a SQLite (datalake & datawarehouse)

Este repositorio contiene scrapers, transformaciones y utilidades para integrar anuncios de alquiler
(en particular MercadoLibre, Gallito e InfoCasas) y datos auxiliares (ej. denuncias por barrio).

Contenido relevante añadido ahora:

- `datos/denuncias_hurtos_por_10000_hab_montevideo.json`
  - JSON con `metadata` y `data` donde las claves están normalizadas (snake_case sin acentos).
  - Cada entrada incluye `label`, `value` y `aliases` para facilitar el matching.

- `scripts/merge_denuncias.py`
  - Script que une el JSON de denuncias con CSVs de anuncios, generando `<csv>_with_denuncias.csv`.

- `scripts/etl_functions_prefect.py`
  - Flujo Prefect que:
    1. Descubre CSVs a procesar (por defecto busca archivos conocidos y/o `*.csv`).
    2. Carga cada CSV y guarda los datos crudos en SQLite (`data/etl_datalake.db`, tabla `raw_listings`).
    3. Ejecuta transformaciones (normaliza nombres, geocodifica direcciones, unifica moneda a UYU, enriquece con datos contextuales) y guarda el resultado en la tabla `transformed_listings` (datawarehouse).
    4. Detecta duplicados cross-portal (solo entre diferentes portales) por coordenadas exactamente iguales y los mueve a la tabla `duplicates_moved`.

### Scripts de Visualización y Exportación

- `scripts/dump_db_to_txt.py`: Exporta tablas principales a archivos de texto legibles
  - Genera `data/raw_listings.txt` y `data/transformed_listings.txt`
  - Útil para revisar datos sin necesidad de consultar la base de datos

- `scripts/export_cross_portal_duplicates.py`: Exporta duplicados cross-portal a texto
  - Genera `data/duplicados_cross_portal.txt` con reporte detallado
  - Incluye estadísticas y detalles de cada par de duplicados

- `scripts/view_duplicates.py`: Muestra información de duplicados en consola
  - Consulta y muestra estadísticas de la tabla `duplicates_detected`

- `requirements.txt` — dependencias Python mínimas.
- `Dockerfile` — imagen para ejecutar el ETL en un contenedor.
- `docker-compose.yml` — ayuda para levantar el contenedor y persistir la carpeta `data/`.


Requisitos previos
------------------

- Python 3.10+ (si vas a ejecutar localmente)
- pip
- Docker (si vas a usar la imagen)

Pasos para ejecutar localmente (sin Docker)
-------------------------------------------

1) Crear y activar un entorno virtual (opcional pero recomendado)

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
```

2) Instalar dependencias

```powershell
pip install -r requirements.txt
```

3) Ejecutar el flujo ETL

**Opción A: Pipeline básico** (procesa CSVs existentes en `data/raw/`):
```bash
python scripts/run_etl.py
```

**Opción B: Pipeline completo** (incluye scrapers y geocodificación):
```bash
python scripts/run_full_pipeline.py
```

**Opciones adicionales para el pipeline completo:**
```bash
# Limitar registros de Gallito
python scripts/run_full_pipeline.py --gallito-limit 50

# Modo dry-run (sin scrapers, solo procesa CSVs existentes)
python scripts/run_full_pipeline.py --dry-run

# Base de datos personalizada
python scripts/run_full_pipeline.py --db-path data/custom_db.db
```

4) (Opcional) Exportar datos a archivos de texto para visualización

```bash
# Exportar todas las tablas
python scripts/dump_db_to_txt.py

# Exportar solo duplicados cross-portal
python scripts/export_cross_portal_duplicates.py

# Ver duplicados en consola
python scripts/view_duplicates.py
```

Los archivos se generarán en `data/`:
- `raw_listings.txt`: Datos crudos
- `transformed_listings.txt`: Datos transformados
- `duplicados_cross_portal.txt`: Reporte de duplicados entre portales

## Detección de Duplicados

El pipeline detecta **únicamente duplicados cross-portal** (entre diferentes portales):

- **Método**: Comparación por coordenadas exactamente iguales (latitud y longitud idénticas)
- **Solo cross-portal**: Los duplicados dentro del mismo portal se ignoran
- **Movimiento**: Los duplicados cross-portal se mueven a la tabla `duplicates_moved`
- **Preservación**: Todos los registros (incluyendo duplicados del mismo portal) permanecen en `transformed_listings`

## Estructura de Datos

### Tablas de la Base de Datos

- **`raw_listings`**: Datos crudos (Data Lake)
- **`transformed_listings`**: Datos transformados y enriquecidos (Data Warehouse)
- **`duplicates_moved`**: Duplicados cross-portal movidos
- **`duplicates_detected`**: Metadatos de duplicados cross-portal detectados
- **`geocode_cache`**: Cache de geocodificación

### Archivos de Texto Exportados

Los scripts de exportación generan archivos `.txt` en `data/` para facilitar la revisión:

- `raw_listings.txt`: Vista legible de datos crudos
- `transformed_listings.txt`: Vista legible de datos transformados
- `duplicados_cross_portal.txt`: Reporte detallado de duplicados entre portales

```powershell
python .\scripts\etl_functions_prefect.py
```

Salida: se crea `data/etl_datalake.db` (SQLite) con tablas `raw_listings` y `transformed_listings`.


Ejecutar con Docker (recomendado para reproducibilidad)
-------------------------------------------------------

1) Construir la imagen

```powershell
docker build -t idatos_etl:latest .
```

2) Ejecutar el contenedor (montando volumen para persistir `data/`)

```powershell
docker run --rm -v ${PWD}:/app -v ${PWD}/data:/app/data idatos_etl:latest
```

O con docker-compose:

```powershell
docker-compose up --build
```

Esto ejecuta `scripts/etl_functions_prefect.py` dentro del contenedor. El archivo `data/etl_datalake.db` quedará en tu carpeta local `./data`.

Notas y limitaciones
--------------------

- El flujo hace transformaciones ligeras (sin geocodificación ni llamadas externas pesadas). Si quieres geocodificar
  o ejecutar operaciones que requieren red (ej. GeoPy), añade `geopy` a `requirements.txt` y adapta `etl_functions_prefect.py`.

- El script de unión `merge_denuncias.py` usa heurísticas simples para inferir barrios desde el campo `ubicacion`. Para
  mayor fiabilidad, agrega aliases adicionales en el JSON o habilita fuzzy matching.

- En los scripts existentes se han añadido diccionarios `METADATA` para facilitar orquestación y auditoría.

Siguientes mejoras sugeridas
---------------------------

- Implementar fuzzy matching o un mapeo manual para mejorar el emparejado de barrios.


Descripción paso a paso (qué hace cada script y etapa)

# iDatos — Backend ETL (resumen y pasos implementados)

Este directorio (`iDatos/backend/`) contiene la implementación canónica del pipeline ETL que carga crudos, transforma y persiste
datos en un SQLite local (`data/etl_datalake.db`). A continuación describo los pasos ya implementados, cómo ejecutarlos y mejoras pendientes.

## Qué hay en `iDatos/backend/scripts`

- `mercadolibre_scraper.py`, `gallito_detail_scraper.py`, `infocasas_alquiler_Gallito.py`: scrapers (backend-copies) que producen CSVs de anuncios.
- `clean_gallito_addresses.py`: normalización de direcciones extraídas de Gallito (genera `*.cleaned.csv`).
- `geocode_batch.py`, `geocode_batch_improved.py`, `geocode_xyz_retry.py`: etapas de geocodificación por lotes con cache en SQLite (`geocode_cache`).
- `etl_functions_prefect.py`: flujo Prefect con `etl_flow()` (ingesta + transformaciones) y `full_etl_pipeline()` que orquesta pasos externos.
- `persist_transformed_concat.py`: reconstrucción atómica/segura de la tabla `transformed_listings` cuando hay esquemas variables.
- `load_denuncias_crime.py`, `join_crime_to_transformed.py`: carga del JSON de denuncias y mapeo de `barrio -> nivel_criminalidad`.
- `datos_contextuales.py`: enriquecimiento espacial (distancias a bicis/paradas, etc.) cuando hay geometrías disponibles.
- `archive_null_coords.py`: mueve o exporta las filas sin coordenadas a la tabla `transformed_listings_no_coords`.
- utilidades: `db_inspect.py`, `run_py_compile.py`, `prepare_db_schema.py`, entre otras.

> Nota: los scripts en `iDatos/backend/scripts` son la fuente de verdad; he eliminado las copias duplicadas en el directorio `scripts/` para evitar confusión.

## Estado actual (pasos implementados)

1. Ingesta de CSVs a `raw_listings` en SQLite (tabla adaptativa que añade columnas según los CSVs).
2. Transformaciones principales (`transform_df`) que producen `transformed_listings`:
   - Filtrado para Montevideo y limpieza de `ubicacion`/`titulo`.
   - Extracción y normalización de precios y moneda; conversión a UYU mediante `TASAS_DE_CAMBIO`.
   - Extracción de dormitorios (`dorms_imputado`) desde el título.
   - Geocoding básico con `geopy` (si instalado) con cache persistente en `geocode_cache`.
   - `barrio_guess` usando el JSON de denuncias y alias (con fallback fuzzy via rapidfuzz si está instalado).
3. Batch geocoding con reintentos y uso de `geocode.xyz` como fallback para casos difíciles.
4. Archiving de filas sin coordenadas a `transformed_listings_no_coords`.
5. Loader y join de denuncias por barrio (`barrio_criminalidad`) y unión con transformados (LEFT JOIN) para preservar filas.
6. Un flujo Prefect `full_etl_pipeline()` que orquesta scrapers, limpieza, geocoding, transformaciones, enriquecimiento y archivado.

## Cómo ejecutar (desde la raíz del repo, Powershell)

1) Ejecución completa con Prefect (recomendado):

```powershell
python -c "from iDatos.backend.scripts.etl_functions_prefect import full_etl_pipeline; full_etl_pipeline(db_path='', gallito_limit=0, dry_run=False)"
```

2) Dry-run (sin scrapers ni geocoding; útil para validar flujo sin llamadas externas):

```powershell
python -c "from iDatos.backend.scripts.etl_functions_prefect import full_etl_pipeline; full_etl_pipeline(db_path='data/tmp_etl_dryrun.db', gallito_limit=0, dry_run=True)"
```

3) Ejecutar sólo la ingesta/transform (sin Prefect orchestration externa):

```powershell
python iDatos/backend/scripts/etl_functions_prefect.py
```

4) Ejecutar el runner secuencial (si prefieres scripts independientes):

```powershell
python scripts/00_run_full_pipeline.py --dry-run
```

## Recomendaciones y mejoras pendientes

- Añadir API key y control de rate limits para `geocode.xyz` y/o migrar a un geocodificador con plan (para evitar throttling).
- Refactorizar `transform_df` para reducir complejidad: dividir en helpers testables y añadir unit tests (pytest).
- Añadir pruebas automáticas (unit + integration quick smoke) que ejecuten el flujo sobre un mini dataset y verifiquen `transformed_listings`.
- Mejorar el mapeo de barrios con una lista curada y reglas adicionales (actualmente se usan aliases + fuzzy heuristics).

## Cambios realizados ahora

- Eliminadas copias duplicadas en `scripts/` y consolidado el código activo en `iDatos/backend/scripts/`.
- Añadido `full_etl_pipeline()` en `etl_functions_prefect.py` para orquestar todo el pipeline bajo Prefect (con `dry_run`).

Si quieres, puedo:

- Mover o renombrar los scripts en `iDatos/backend/scripts` a un esquema numerado `00_*`, `01_*`, ... con nombres descriptivos para que sea fácil seguir el pipeline.
- Añadir una lista de comandos en este README con ejemplos concretos para cada etapa (scrape, clean, geocode, transform, enrich, archive).

Dime si deseas que realice el renombrado numerado dentro de `iDatos/backend/scripts` ahora; lo puedo hacer y actualizar automáticamente los `run_script(...)` dentro de `etl_functions_prefect.py` para que llamen a los nuevos nombres.

