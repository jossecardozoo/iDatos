"""09_archive_null_coords.py
Wrapper: execute the canonical repo-root archive script. The implementation in this
repo is named `10_archive_null_coords.py`, so use that path.
"""
import runpy
from pathlib import Path

repo_root = Path(__file__).resolve().parents[3]
# canonical implementation is scripts/10_archive_null_coords.py
script = repo_root / 'scripts' / '10_archive_null_coords.py'

if __name__ == '__main__':
    runpy.run_path(str(script), run_name='__main__')
