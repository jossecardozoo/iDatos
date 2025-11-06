"""00_run_full_pipeline.py
Wrapper to run the existing `run_full_pipeline.py` with a numeric prefix.
"""
import runpy
from pathlib import Path

script = Path(__file__).with_name('run_full_pipeline.py')

if __name__ == '__main__':
    runpy.run_path(str(script), run_name='__main__')
