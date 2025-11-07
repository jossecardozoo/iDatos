"""
merge_denuncias.py

Integra el JSON normalizado de denuncias (datos/denuncias_hurtos_por_10000_hab_montevideo.json)
con CSVs de anuncios (MercadoLibre, Gallito, InfoCasas, etc.).

Salida: por cada CSV de entrada se genera un nuevo CSV con sufijo `_with_denuncias.csv`
con la columna `hurtos_por_10k` (valor numérico) y `barrio_normalizado`.

Heurística de emparejamiento:
- Si existe una columna `barrio` la usa.
- Si existe `ubicacion`, intenta extraer el barrio buscando coincidencias con aliases del JSON
  o tomando la segunda/tercera parte separada por comas.
- Si no encuentra coincidencias deja NaN.

Metadatos incluidos en el script.
"""

METADATA = {
    "name": "merge_denuncias",
    "description": "Integra denuncias por barrio (JSON) con CSVs de anuncios y agrega columna de hurtos por 10k habitantes.",
    "author": "iDatos team",
    "date_created": "2025-11-04",
    "version": "1.0",
}

import json
import unicodedata
import re
from pathlib import Path
import pandas as pd

JSON_PATH = Path("datos/denuncias_hurtos_por_10000_hab_montevideo.json")
CSV_CANDIDATES = [
    Path("mercadolibre_alquileres_con_imagen.csv"),
    Path("gallito_alquileres_crudos.csv"),
    Path("infocasas_datos.csv"),
    Path("datos_transformados_final.csv"),
]


def normalize_text(s):
    if not isinstance(s, str):
        return ""
    s = s.lower().strip()
    # Remove accents
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    # Replace non-alphanumeric by underscore
    s = re.sub(r"[^a-z0-9]+", '_', s)
    s = re.sub(r'__+', '_', s)
    return s.strip('_')


def load_denuncias(json_path=JSON_PATH):
    with open(json_path, 'r', encoding='utf-8') as f:
        payload = json.load(f)

    meta = payload.get('metadata', {})
    data = payload.get('data', {})

    # Build mapping: normalized_key -> value, and collect aliases
    value_map = {}
    alias_map = {}  # normalized alias -> normalized_key

    for norm_key, item in data.items():
        value = item.get('value')
        label = item.get('label')
        aliases = item.get('aliases', [])

        value_map[norm_key] = {'value': value, 'label': label}

        # register normalized label as alias
        alias_map[normalize_text(label)] = norm_key

        for a in aliases:
            alias_map[normalize_text(a)] = norm_key

    return meta, value_map, alias_map


def guess_barrio_from_ubicacion(ubicacion, alias_map):
    """Intenta inferir el barrio a partir del campo 'ubicacion' del anuncio."""
    if not isinstance(ubicacion, str) or not ubicacion:
        return None

    # Split by comma and try parts (trim)
    parts = [p.strip() for p in ubicacion.split(',') if p.strip()]

    # Try parts in order (2nd or 3rd part often contains barrio)
    for idx in [1, 2, -1, 0]:
        if len(parts) > idx and idx >= -len(parts):
            cand = parts[idx]
            cand_norm = normalize_text(cand)
            if cand_norm in alias_map:
                return alias_map[cand_norm]

    # fallback: search for any alias substring match
    ubic_norm = normalize_text(ubicacion)
    for alias_norm, key in alias_map.items():
        if alias_norm and alias_norm in ubic_norm:
            return key

    return None


def integrate_csv(path_csv, meta, value_map, alias_map):
    if not path_csv.exists():
        print(f"[SKIP] No existe: {path_csv}")
        return

    print(f"Procesando: {path_csv}")
    df = pd.read_csv(path_csv, dtype=str, encoding='utf-8', errors='ignore')

    # Ensure ubicacion column exists
    if 'barrio' not in df.columns and 'ubicacion' not in df.columns and 'location' not in df.columns:
        print(f"  -> No se encontró columna 'ubicacion' ni 'barrio' en {path_csv.name}. Se intentará inferir de otras columnas.")

    # Create columns
    df['barrio_normalizado'] = None
    df['hurtos_por_10k'] = None

    for idx, row in df.iterrows():
        barrio_key = None

        # 1) If explicit barrio column
        if 'barrio' in df.columns and pd.notna(row.get('barrio')):
            barrio_key = alias_map.get(normalize_text(row.get('barrio')))

        # 2) If ubicacion column 
        if barrio_key is None and 'ubicacion' in df.columns and pd.notna(row.get('ubicacion')):
            barrio_key = guess_barrio_from_ubicacion(row.get('ubicacion'), alias_map)

        # 3) If location column
        if barrio_key is None and 'location' in df.columns and pd.notna(row.get('location')):
            barrio_key = guess_barrio_from_ubicacion(row.get('location'), alias_map)

        if barrio_key:
            df.at[idx, 'barrio_normalizado'] = barrio_key
            df.at[idx, 'hurtos_por_10k'] = value_map.get(barrio_key, {}).get('value')

    out_path = path_csv.with_name(path_csv.stem + '_with_denuncias.csv')
    df.to_csv(out_path, index=False, encoding='utf-8')
    print(f"  -> Guardado con denuncias: {out_path}")


def main():
    meta, value_map, alias_map = load_denuncias()

    # If CSV_CANDIDATES not present in cwd, also scan current dir for '*.csv'
    existing = [p for p in CSV_CANDIDATES if p.exists()]
    if not existing:
        # scan for csvs in current folder
        existing = list(Path('.').glob('*.csv'))

    for p in existing:
        integrate_csv(p, meta, value_map, alias_map)


if __name__ == '__main__':
    main()
