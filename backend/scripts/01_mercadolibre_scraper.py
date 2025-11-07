"""01_mercadolibre_scraper.py
Wrapper to execute the mercadolibre_scraper from the etl module.
"""
import runpy
from pathlib import Path

# El scraper está en backend/scripts/etl/mercadolibre_scraper.py
script = Path(__file__).resolve().parent / 'etl' / 'mercadolibre_scraper.py'

if __name__ == '__main__':
    runpy.run_path(str(script), run_name='__main__')
