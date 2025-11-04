import py_compile, sys
files = [
    r'c:\Users\CaroH\Documents\fing\IntegracionDatos\scripts\mercadolibre_scraper.py',
    r'c:\Users\CaroH\Documents\fing\IntegracionDatos\iDatos\backend\scripts\mercadolibre_scraper.py',
    r'c:\Users\CaroH\Documents\fing\IntegracionDatos\scripts\infocasas_alquiler_Gallito.py',
    r'c:\Users\CaroH\Documents\fing\IntegracionDatos\iDatos\backend\scripts\infocasas_alquiler_Gallito.py',
    r'c:\Users\CaroH\Documents\fing\IntegracionDatos\scripts\transformaciones\script_transformaciones.py',
    r'c:\Users\CaroH\Documents\fing\IntegracionDatos\iDatos\backend\scripts\transformaciones\script_transformaciones.py',
    r'c:\Users\CaroH\Documents\fing\IntegracionDatos\scripts\merge_denuncias.py',
    r'c:\Users\CaroH\Documents\fing\IntegracionDatos\scripts\etl_functions_prefect.py'
]
ok = True
for f in files:
    try:
        py_compile.compile(f, doraise=True)
        print('COMPILE_OK:', f)
    except Exception as e:
        print('COMPILE_FAIL:', f)
        print(e)
        ok = False
if not ok:
    sys.exit(1)
