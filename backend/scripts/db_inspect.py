"""
Utility: db_inspect.py

Prints SQLite table schemas and row counts for the ETL database.
Optional modes:
  - --db PATH          : path to sqlite DB (default: data/etl_datalake.db)
  - --save-snapshot P  : save current schema snapshot to JSON file P
  - --compare P        : compare current schema to snapshot in P and list added columns

Example:
  python scripts/db_inspect.py --db data/etl_datalake.db
  python scripts/db_inspect.py --compare snapshots/old_schema.json
  python scripts/db_inspect.py --save-snapshot snapshots/current.json

"""
import argparse
import json
import sqlite3
from pathlib import Path
from typing import Dict, List


def get_tables(conn: sqlite3.Connection) -> List[str]:
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    return [r[0] for r in cur.fetchall()]


def get_table_info(conn: sqlite3.Connection, table: str):
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info('{table}')")
    cols = []
    for row in cur.fetchall():
        # row: cid, name, type, notnull, dflt_value, pk
        cols.append({
            'name': row[1],
            'type': row[2],
            'notnull': bool(row[3]),
            'default': row[4],
            'pk': bool(row[5])
        })
    return cols


def row_count(conn: sqlite3.Connection, table: str) -> int:
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT COUNT(*) FROM '{table}'")
        return cur.fetchone()[0]
    except Exception:
        return -1


def snapshot_schema(conn: sqlite3.Connection) -> Dict[str, List[str]]:
    out = {}
    for t in get_tables(conn):
        cols = get_table_info(conn, t)
        out[t] = [c['name'] for c in cols]
    return out


def pretty_print_schema(conn: sqlite3.Connection):
    tables = get_tables(conn)
    if not tables:
        print('No tables found in DB.')
        return
    for t in tables:
        print(f"Table: {t}")
        cols = get_table_info(conn, t)
        for c in cols:
            print(f"  - {c['name']} ({c['type']}) notnull={c['notnull']} pk={c['pk']} default={c['default']}")
        cnt = row_count(conn, t)
        print(f"  rows: {cnt}\n")


def compare_snapshot(old: Dict[str, List[str]], new: Dict[str, List[str]]):
    # report tables added, columns added per table
    added_tables = [t for t in new.keys() if t not in old]
    common = [t for t in new.keys() if t in old]
    added_cols = {}
    for t in common:
        old_cols = set(old[t])
        new_cols = set(new[t])
        added = sorted(list(new_cols - old_cols))
        if added:
            added_cols[t] = added
    return added_tables, added_cols


def main():
    p = argparse.ArgumentParser(description='Inspect SQLite ETL DB schemas and counts')
    p.add_argument('--db', default='data/etl_datalake.db', help='Path to sqlite DB')
    p.add_argument('--save-snapshot', dest='save_snapshot', help='Save current schema to JSON file')
    p.add_argument('--compare', dest='compare_snapshot', help='Compare current schema to snapshot JSON file')
    args = p.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"DB not found: {db_path}. Run the ETL first to create the DB.")
        return

    conn = sqlite3.connect(str(db_path))

    print(f"Inspecting DB: {db_path}\n")
    pretty_print_schema(conn)

    current = snapshot_schema(conn)

    if args.save_snapshot:
        outp = Path(args.save_snapshot)
        outp.parent.mkdir(parents=True, exist_ok=True)
        with open(outp, 'w', encoding='utf-8') as fh:
            json.dump(current, fh, indent=2, ensure_ascii=False)
        print(f"Saved snapshot to {outp}")

    if args.compare_snapshot:
        snap = Path(args.compare_snapshot)
        if not snap.exists():
            print(f"Snapshot to compare not found: {snap}")
        else:
            with open(snap, 'r', encoding='utf-8') as fh:
                old = json.load(fh)
            added_tables, added_cols = compare_snapshot(old, current)
            if not added_tables and not added_cols:
                print('No schema additions since snapshot.')
            else:
                if added_tables:
                    print('\nTables added since snapshot:')
                    for t in added_tables:
                        print(f"  - {t}")
                if added_cols:
                    print('\nColumns added since snapshot:')
                    for t, cols in added_cols.items():
                        print(f"  {t}:")
                        for c in cols:
                            print(f"    - {c}")

    conn.close()


if __name__ == '__main__':
    main()
