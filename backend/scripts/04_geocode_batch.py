"""04_geocode_batch.py
Wrapper to execute the legacy `geocode_batch.py` from the same folder.
"""
import runpy
from pathlib import Path

repo_root = Path(__file__).resolve().parents[3]
script = repo_root / 'scripts' / Path(__file__).name

if __name__ == '__main__':
    runpy.run_path(str(script), run_name='__main__')
