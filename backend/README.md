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

- Añadir un job scheduler (Prefect Server/Cloud) para la orquestación centralizada.
- Añadir pruebas unitarias para las funciones de normalización y matching.
- Implementar fuzzy matching o un mapeo manual para mejorar el emparejado de barrios.
