"""01_mercadolibre_scraper.py
Wrapper to execute the legacy `mercadolibre_scraper.py` from the same folder.
"""
import runpy
from pathlib import Path

# Run the canonical script from the repository root 'scripts' folder.
# This ensures numeric wrappers under `iDatos/backend/scripts` call the actual implementation
# located at repo_root/scripts/01_mercadolibre_scraper.py
repo_root = Path(__file__).resolve().parents[3]
script = repo_root / 'scripts' / Path(__file__).name

if __name__ == '__main__':
    runpy.run_path(str(script), run_name='__main__')
