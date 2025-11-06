"""Improved batch geocoder that tries multiple address variants per input.

Writes results to the same `geocode_cache` SQLite table used by the other geocoder
and emits a CSV with addresses that could not be resolved (with tried candidates).

This is conservative: it won't overwrite the main script and logs failures for manual review.
"""
from pathlib import Path
import argparse
import sqlite3
from datetime import datetime, timezone
import csv

try:
    from geopy.geocoders import Nominatim
    from geopy.extra.rate_limiter import RateLimiter
except Exception as e:
    print('geopy is required for batch geocoding:', e)
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


def generate_candidates(s: str):
    """Return a list of candidate query strings for geocoding, ordered by preference."""
    if not isinstance(s, str):
        return []
    s0 = s.strip()
    cand = []

    # original
    cand.append(s0)

    # add Montevideo, Uruguay if missing
    if 'montevideo' not in s0.lower():
        cand.append(f"{s0}, Montevideo, Uruguay")

    # if contains ' y ' (corner) also try comma-separated and 'and' variants
    if ' y ' in s0.lower():
        cand.append(s0.replace(' y ', ', '))
        cand.append(s0.replace(' y ', ' and '))
        # with suffix
        if 'montevideo' not in s0.lower():
            cand.append(s0.replace(' y ', ', ') + ', Montevideo, Uruguay')

    # if contains ' and ' try with comma also
    if ' and ' in s0.lower():
        cand.append(s0.replace(' and ', ', '))

    # remove common trailing noise
    for noisy in ['ref', 'aprox', 'aproximadamente', 'cerca de', 'entre']:
        if noisy in s0.lower():
            cleaned = s0.lower().split(noisy)[0].strip()
            if cleaned:
                cand.append(cleaned)
                if 'montevideo' not in cleaned:
                    cand.append(f"{cleaned}, Montevideo, Uruguay")

    # dedupe while preserving order
    seen = set()
    out = []
    for c in cand:
        if not c:
            continue
        if c.lower() not in seen:
            seen.add(c.lower())
            out.append(c)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sources', nargs='*', default=None, help='CSV files to scan; default: CSVs in repo root')
    parser.add_argument('--delay', type=float, default=1.0, help='min delay seconds between geocode calls')
    parser.add_argument('--max-candidates', type=int, default=5, help='max candidates to try per address')
    args = parser.parse_args()

    if args.sources:
        files = [Path(x) for x in args.sources]
    else:
        files = list(Path('.').glob('*.csv'))

    addrs = set()
    import pandas as pd
    for f in files:
        try:
            df = pd.read_csv(f, dtype=str, encoding='utf-8')
        except Exception:
            df = pd.read_csv(f, dtype=str, encoding='latin-1')

        # collect from several possible columns
        for c in ('direccion_norm', 'direccion_limpia', 'direccion', 'ubicacion'):
            if c in df.columns:
                for u in df[c].astype(str).dropna().unique():
                    if u and u.strip() and u.strip().lower() not in ('nan', ''):
                        addrs.add((u.strip(), c))
                break

    print('Found', len(addrs), 'unique addresses (value,source_col) to check')

    dbp = get_db_path()
    print('Using DB:', dbp)
    conn = sqlite3.connect(str(dbp))
    ensure_table(conn)

    geolocator = Nominatim(user_agent='idatos_batch_geocoder_improved', timeout=10)
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=args.delay)

    to_try = []
    for val, col in addrs:
        to_try.append((val, col))

    failed = []
    total = len(to_try)
    for i, (val, col) in enumerate(to_try, 1):
        print(f'[{i}/{total}] address from {col}: {val}')
        candidates = generate_candidates(val)[:args.max_candidates]
        # also try the raw column value with suffix if not included
        if val not in candidates and 'Montevideo' not in val:
            candidates.append(f"{val}, Montevideo, Uruguay")

        found = None
        for cand in candidates:
            # check cache for exact candidate string
            cached = already_cached(conn, cand)
            if cached:
                print('  cached ->', cached)
                found = (cand, cached[0], cached[1])
                break
            try:
                loc = geocode(cand)
            except Exception as e:
                print('  error geocoding candidate', cand, e)
                loc = None
            if loc:
                lat, lon = loc.latitude, loc.longitude
                write_cache(conn, cand, lat, lon)
                print('  found ->', lat, lon, ' (candidate: ', cand, ')')
                found = (cand, lat, lon)
                break
            else:
                print('   no result for candidate:', cand)

        if not found:
            failed.append({'original': val, 'source_col': col, 'tried': ';'.join(candidates)})

    # write failed list for manual inspection
    if failed:
        outp = Path('geocode_failed_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.csv')
        with outp.open('w', newline='', encoding='utf-8') as fh:
            w = csv.DictWriter(fh, fieldnames=['original', 'source_col', 'tried'])
            w.writeheader()
            for r in failed:
                w.writerow(r)
        print('Wrote failed addresses to', outp)
    else:
        print('All addresses resolved or present in cache')

    conn.close()


if __name__ == '__main__':
    main()
