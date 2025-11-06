from pathlib import Path
import json
import unicodedata
import re
from typing import Tuple, Dict, List, Set, Optional


def normalize_for_match(s: str) -> str:
    if not isinstance(s, str):
        return ''
    t = unicodedata.normalize('NFKD', s)
    t = ''.join(c for c in t if not unicodedata.combining(c))
    t = t.lower()
    t = re.sub(r'[^a-z0-9 ]+', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def load_denuncias_aliases(json_path: Path = Path('datos') / 'denuncias_hurtos_por_10000_hab_montevideo.json') -> Tuple[Dict[str, str], List[str], Set[str], Dict[str, str]]:
    alias_map = {}
    label_map = {}
    barrio_tokens = set()
    if not json_path.exists():
        return alias_map, [], barrio_tokens, label_map
    try:
        with open(json_path, 'r', encoding='utf-8') as fh:
            payload = json.load(fh)
        data = payload.get('data', {})
        for key, item in data.items():
            label = item.get('label', '')
            norm_key = normalize_for_match(label).replace(' ', '_') if label else key
            label_map[norm_key] = label
            alias_map[norm_key] = norm_key
            barrio_tokens.add(normalize_for_match(label))
            for a in item.get('aliases', []):
                ak = normalize_for_match(a)
                alias_map[ak] = norm_key
                barrio_tokens.add(ak)
    except Exception:
        return {}, [], set(), {}

    fuzzy_choices = list(alias_map.keys())
    return alias_map, fuzzy_choices, barrio_tokens, label_map


def _fuzzy_match(u_norm: str, fuzzy_choices: List[str], alias_map: Dict[str, str], logger=None, threshold_full: int = 78, threshold_token: int = 85) -> Optional[str]:
    try:
        from rapidfuzz import process as rf_process, fuzz as rf_fuzz
    except Exception:
        if logger:
            logger.debug('rapidfuzz no disponible: skip fuzzy matching')
        return None

    if not fuzzy_choices:
        return None

    queries = [u_norm] + [tok for tok in u_norm.split() if len(tok) >= 3]
    for q in queries:
        best = rf_process.extractOne(q, fuzzy_choices, scorer=rf_fuzz.partial_ratio)
        if not best:
            continue
        score = best[1]
        required = threshold_full if q == u_norm else threshold_token
        if score >= required:
            if logger:
                kind = 'whole' if q == u_norm else 'token'
                logger.info(f"Fuzzy barrio match ({kind}): '{best[0]}' score={score} token='{q}' -> {alias_map.get(best[0])}")
            return alias_map.get(best[0])

    return None


def guess_barrio(ubic: str, alias_map: Dict[str, str], fuzzy_choices: List[str], logger=None, threshold_full: int = 78, threshold_token: int = 85) -> Optional[str]:
    """Try deterministic matches first (parts and substring), then fuzzy match.

    Keeps logic simple to reduce cognitive complexity for linters.
    """
    if not isinstance(ubic, str) or not ubic:
        return None
    u_norm = normalize_for_match(ubic)

    # try components separated by comma or newline (common address parts)
    parts = [p.strip() for p in re.split(r"[,\n]", ubic) if p.strip()]
    # check first few parts and last part
    for i in range(min(3, len(parts))):
        cand = normalize_for_match(parts[i])
        if cand in alias_map:
            return alias_map[cand]
    if parts:
        last = normalize_for_match(parts[-1])
        if last in alias_map:
            return alias_map[last]

    # substring match against alias keys
    for a, v in alias_map.items():
        if a and a in u_norm:
            return v

    # fallback to fuzzy matching
    return _fuzzy_match(u_norm, fuzzy_choices, alias_map, logger=logger, threshold_full=threshold_full, threshold_token=threshold_token)


def limpiar_ubicacion_para_geocodificacion(direccion: str) -> str:
    if not isinstance(direccion, str):
        return ''
    parte_principal = direccion.split(',')[0].strip()
    parte_principal = re.sub(r'\s*/\s*\d+\s*$', '', parte_principal)
    parte_principal = re.sub(r'\s*Esq\.?\s*', ' and ', parte_principal, flags=re.IGNORECASE)
    parte_principal = re.sub(r'\s*esquina\s*', ' and ', parte_principal, flags=re.IGNORECASE)
    parte_principal = re.sub(r'\s{2,}', ' ', parte_principal).strip()
    return parte_principal.strip()


def extraer_dorms(titulo: str) -> Optional[int]:
    if not isinstance(titulo, str):
        return None
    t = titulo.lower()
    if 'monoambiente' in t or 'mono ambiente' in t or 'studio' in t:
        return 1
    m = re.search(r'(\d+)\s*(dorm|hab|amb)', t)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            return None
    m2 = re.search(r'\b(un|uno|una|dos|tres|cuatro)\b', t)
    map_num = {'un':1,'uno':1,'una':1,'dos':2,'tres':3,'cuatro':4}
    if m2:
        return map_num.get(m2.group(1), None)
    return None
