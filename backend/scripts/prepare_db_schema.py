"""Prepare DB schema: create barrio_criminalidad table and add crime columns to transformed_listings.

Use before running pipeline to ensure required tables/columns exist.
"""
from pathlib import Path
import sqlite3


DEFAULT_DB = Path('iDatos') / 'backend' / 'data' / 'etl_datalake.db'


def ensure_table(conn):
    cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS barrio_criminalidad (barrio_norm TEXT PRIMARY KEY, barrio_label TEXT, hurtos_10k REAL, nivel TEXT, aliases TEXT)')
    conn.commit()


def add_columns_to_transformed(conn):
    cur = conn.cursor()
    # Fetch existing columns
    try:
        cur.execute("PRAGMA table_info('transformed_listings')")
        cols = [r[1] for r in cur.fetchall()]
    except Exception:
        cols = []

    # Add columns if missing
    if 'hurtos_10k' not in cols:
        try:
            cur.execute('ALTER TABLE transformed_listings ADD COLUMN hurtos_10k REAL')
            print('Added column hurtos_10k to transformed_listings')
        except Exception:
            print('Could not add hurtos_10k (table may not exist yet)')
    else:
        print('Column hurtos_10k already present')

    if 'nivel_criminalidad' not in cols:
        try:
            cur.execute('ALTER TABLE transformed_listings ADD COLUMN nivel_criminalidad TEXT')
            print('Added column nivel_criminalidad to transformed_listings')
        except Exception:
            print('Could not add nivel_criminalidad (table may not exist yet)')
    else:
        print('Column nivel_criminalidad already present')

    conn.commit()


def main():
    dbp = DEFAULT_DB
    dbp.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(dbp))
    ensure_table(conn)
    add_columns_to_transformed(conn)
    conn.close()


if __name__ == '__main__':
    import sqlite3
    main()
