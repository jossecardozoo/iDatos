"""
Exporta tablas SQLite a archivos de texto legibles para inspección rápida.

Genera los siguientes archivos en data/:
 - raw_listings.txt: Datos crudos de todos los portales
 - transformed_listings.txt: Datos transformados y enriquecidos

Ejecutar desde el directorio backend/ o desde la raíz del repositorio.
El script encuentra automáticamente la ruta data/ relativa a su ubicación.

Uso:
    python scripts/dump_db_to_txt.py
"""
from pathlib import Path
import pandas as pd
import sqlite3

BASE = Path(__file__).resolve().parents[1]
# Prefer backend/data, but fall back to repository root data/ (where the ETL was previously executed)
DB_PATH = BASE / 'data' / 'etl_datalake.db'
if not DB_PATH.exists():
    # repo root is one level above backend
    repo_root_db = BASE.parents[1] / 'data' / 'etl_datalake.db'
    if repo_root_db.exists():
        DB_PATH = repo_root_db

OUT_DIR = DB_PATH.parent
OUT_DIR.mkdir(parents=True, exist_ok=True)

if not DB_PATH.exists():
    print(f"DB not found: {DB_PATH}")
    raise SystemExit(1)

conn = sqlite3.connect(str(DB_PATH))

tables = ['raw_listings', 'transformed_listings']
for t in tables:
    try:
        df = pd.read_sql_query(f"SELECT * FROM {t}", conn)
    except Exception as e:
        print(f"Could not read table {t}: {e}")
        continue

    out = OUT_DIR / f"{t}.txt"
    with open(out, 'w', encoding='utf-8') as fh:
        fh.write(f"Table: {t}\nRows: {len(df)}\nColumns: {', '.join(df.columns.tolist())}\n\n")
        fh.write(df.to_string(index=False))

    print(f"Wrote {out} ({len(df)} rows)")

conn.close()
