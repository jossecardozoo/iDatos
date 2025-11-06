"""03_clean_gallito_addresses.py
Wrapper: call the canonical repo-root script that performs Gallito address cleaning.
This repository uses `scripts/03_clean_addresses.py` as the implementation — the
wrapper resolves to that file to keep the numeric pipeline in `iDatos/backend/scripts`.
"""
import runpy
from pathlib import Path

repo_root = Path(__file__).resolve().parents[3]
# canonical implementation live in repo-root scripts/03_clean_addresses.py
script = repo_root / 'scripts' / '03_clean_addresses.py'

if __name__ == '__main__':
    runpy.run_path(str(script), run_name='__main__')
