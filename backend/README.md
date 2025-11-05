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
    3. Ejecuta transformaciones ligeras (normaliza nombres, convierte precio a numérico, unifica moneda a UYU) y guarda
       el resultado en la tabla `transformed_listings` (datawarehouse).

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

3) Ejecutar el flujo ETL (ejecución local, correrá sequencialmente)

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
-----------------------------------------------------

Aquí se explica con más detalle qué hace cada paso del ETL y las utilidades principales del repositorio. Sirve como referencia rápida para entender el flujo y depurar si hace falta.

1. Descubrimiento de CSVs (`discover_csvs` dentro de `scripts/etl_functions_prefect.py`)
  - Busca los archivos CSV a procesar. Por defecto detecta archivos conocidos del proyecto (ej. `mercadolibre_alquileres*.csv`, `gallito*.csv`, `datos_transformados_final.csv`) y puede ampliarse para aceptar un path.

2. Carga de CSVs (`load_csv` task)
  - Lee cada CSV a un DataFrame de pandas.
  - Añade columnas de metadatos como `__source_file` y `__loaded_at` para trazabilidad.

3. Creación de tablas canónicas (`create_canonical_tables`)
  - Antes de la ingesta pre-crea (o recrea) tablas vacías canónicas en la base SQLite: `raw_listings` y `transformed_listings`.
  - Esto reduce la necesidad de ALTER TABLE excesivos al unificar un esquema base desde la unión de cabeceras de CSV.

4. Escritura de crudos a SQLite (`write_raw_to_sql`)
  - Normaliza nombres de columnas (snake_case, sin acentos, lowercase) para consistencia.
  - Detecta columnas faltantes en la tabla SQLite y las agrega con `ALTER TABLE` cuando es necesario (ingesta schema-adaptativa).
  - Consolida columnas duplicadas que difieren solo en mayúsculas/acentos.
  - Escribe las filas en la tabla `raw_listings` (append).

5. Transformaciones principales (`transform_df`)
  - Ejecuta las transformaciones de negocio y normalizaciones sobre los datos crudos para producir la tabla final:
    - Geocoding (primer paso): intenta resolver `ubicacion` a `latitud`/`longitud` cuando `geopy` está disponible.
    - Filtrado por Montevideo: por ahora se conservan filas cuya `ubicacion` contiene la palabra "Montevideo" y se limpia ese sufijo del `titulo` y `ubicacion`.
    - Normalización de precio: extrae valor numérico y moneda, convierte a `precio_base_uyu` cuando es posible (heurístico de monedas).
    - Imputación de dormitorios (`dorms_imputado`) a partir del título si falta en la columna original.
    - `barrio_guess`: imputación de barrio usando el JSON `datos/denuncias_hurtos_por_10000_hab_montevideo.json` (usa aliases y heurísticas sobre `ubicacion`).
    - Otras transformaciones ligeras tomadas de `scripts/transformaciones/script_transformaciones.py` (normalizaciones adicionales, limpieza de strings, extracción de superficies, etc.).

6. Escritura de transformados a SQLite (`write_transformed_to_sql`)
  - Similar a `write_raw_to_sql`: normaliza columnas, agrega columnas faltantes si hacen falta, consolida duplicados y escribe en `transformed_listings`.

7. Unión con denuncias (`scripts/merge_denuncias.py`)
  - Usa `datos/denuncias_hurtos_por_10000_hab_montevideo.json` y su lista de `aliases` para mapear barrios sobre los CSVs y generar archivos `<csv>_with_denuncias.csv` con las métricas de denuncias unidas.

8. Inspección de la base (`scripts/db_inspect.py`)
  - Herramienta de diagnóstico que muestra las tablas, columnas y el conteo de filas en `data/etl_datalake.db`.

9. Dump a TXT para revisión rápida (`scripts/dump_db_to_txt.py`)
  - Escribe versiones planas `.txt` de las tablas `raw_listings` y `transformed_listings` para revisión humana rápida.

10. Comprobación rápida de sintaxis (`scripts/run_py_compile.py`)
   - Ejecuta un `py_compile` sobre los módulos críticos para detectar errores de sintaxis antes de ejecutar el ETL.

11. Contenedores (Docker)
   - `Dockerfile` y `docker-compose.yml` permiten empaquetar el ETL en un contenedor reproducible. Montar `./data` como volumen para persistir `data/etl_datalake.db`.

Salida esperada
---------------

- `data/etl_datalake.db`: base SQLite con tablas `raw_listings` (crudos) y `transformed_listings` (datawarehouse).
- Dumps legibles en `data/*.txt` si ejecutas `scripts/dump_db_to_txt.py`.

Consejos rápidos
----------------
- Para evitar duplicar CSVs entre el repo raíz y `iDatos/backend`, puedes apuntar `discover_csvs` a una ruta absoluta o relativa común en lugar de copiar archivos.
- Si quieres geocoding robusto en producción, instala `geopy` y revisa límites y políticas del proveedor (Nominatim u otros). Para cargas grandes, usar un servicio con clave o una base de POI local es recomendable.

