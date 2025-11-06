"""Retry geocoding using a trimmed candidate (part before first comma) for the failed list.

Reads the most recent geocode_failed_*.csv in repo root and tries a simple trimmed candidate
for each failed address (usually removes neighborhood fragments). Writes a new failures CSV
with remaining unresolved addresses.
"""
from pathlib import Path
import sqlite3
from datetime import datetime, timezone
import csv
import glob

try:
    from geopy.geocoders import Nominatim
    from geopy.extra.rate_limiter import RateLimiter
except Exception as e:
    print('geopy is required for batch geocoding retry:', e)
    raise


def get_db_path():
    p1 = Path('iDatos') / 'backend' / 'data' / 'etl_datalake.db'
    p2 = Path('data') / 'etl_datalake.db'
    return p1 if p1.exists() else p2


def ensure_table(conn):
    cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS geocode_cache (address TEXT PRIMARY KEY, lat REAL, lon REAL, geocoded_at TEXT)')
    conn.commit()


def already_cached(conn, address):
    cur = conn.cursor()
    cur.execute('SELECT lat, lon FROM geocode_cache WHERE address = ? LIMIT 1', (address,))
    r = cur.fetchone()
    return (r[0], r[1]) if r else None


def write_cache(conn, address, lat, lon):
    cur = conn.cursor()
    cur.execute('REPLACE INTO geocode_cache(address, lat, lon, geocoded_at) VALUES(?,?,?,?)', (address, lat, lon, datetime.now(timezone.utc).isoformat()))
    conn.commit()


def find_latest_failed():
    files = sorted(glob.glob('geocode_failed_*.csv'))
    return Path(files[-1]) if files else None


def main():
    f = find_latest_failed()
    if not f:
        print('No geocode_failed_*.csv found in repo root')
        return
    print('Retrying from', f)

    rows = []
    with f.open('r', encoding='utf-8') as fh:
        r = csv.DictReader(fh)
        for row in r:
            rows.append(row)

    dbp = get_db_path()
    print('Using DB:', dbp)
    conn = sqlite3.connect(str(dbp))
    ensure_table(conn)

    geolocator = Nominatim(user_agent='idatos_batch_geocoder_retry', timeout=10)
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.0)

    failed_new = []
    for i, r in enumerate(rows, 1):
        orig = r.get('original') or ''
        cand = orig.split(',')[0].strip()
        if not cand:
            failed_new.append(r)
            continue
        if 'montevideo' not in cand.lower():
            cand2 = f"{cand}, Montevideo, Uruguay"
        else:
            cand2 = cand

        print(f'[{i}/{len(rows)}] trying: "{cand2}" (from original: {orig})')
        cached = already_cached(conn, cand2)
        if cached:
            print('  cached ->', cached)
            continue
        try:
            loc = geocode(cand2)
        except Exception as e:
            print('  error geocoding', cand2, e)
            loc = None
        if loc:
            lat, lon = loc.latitude, loc.longitude
            write_cache(conn, cand2, lat, lon)
            print('  found ->', lat, lon)
        else:
            print('  still not found')
            failed_new.append(r)

    if failed_new:
        outp = Path('geocode_failed_retry_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.csv')
        with outp.open('w', newline='', encoding='utf-8') as fh:
            w = csv.DictWriter(fh, fieldnames=['original', 'source_col', 'tried'])
            w.writeheader()
            for rr in failed_new:
                w.writerow(rr)
        print('Wrote new failed list to', outp)
    else:
        print('No failures remaining after retry pass')

    conn.close()


if __name__ == '__main__':
    main()
