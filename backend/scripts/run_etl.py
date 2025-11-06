#!/usr/bin/env python
"""
Script para ejecutar el pipeline ETL básico.

Este script ejecuta el flujo ETL que:
1. Descubre y carga CSVs de la carpeta data/raw/
2. Guarda datos crudos en raw_listings
3. Transforma los datos (geocodificación, normalización, enriquecimiento)
4. Detecta duplicados cross-portal y los mueve a tabla separada
5. Guarda datos transformados en transformed_listings

Uso:
    python scripts/run_etl.py [--db-path PATH]
    
Ejemplos:
    python scripts/run_etl.py
    python scripts/run_etl.py --db-path data/custom_database.db
"""
import sys
import argparse
from pathlib import Path

# Añadir el directorio backend al path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from scripts.etl_functions_prefect import etl_flow


def main():
    parser = argparse.ArgumentParser(
        description='Ejecuta el pipeline ETL básico',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  %(prog)s
  %(prog)s --db-path data/custom_database.db
        """
    )
    parser.add_argument(
        '--db-path',
        type=str,
        default=None,
        help='Ruta personalizada a la base de datos SQLite (default: data/etl_datalake.db)'
    )
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("EJECUTANDO PIPELINE ETL BÁSICO")
    print("=" * 80)
    print()
    
    if args.db_path:
        print(f"Base de datos: {args.db_path}")
    else:
        print("Base de datos: data/etl_datalake.db (default)")
    
    print()
    print("Iniciando pipeline...")
    print("-" * 80)
    
    try:
        # Ejecutar el pipeline
        etl_flow(sqlite_path=args.db_path)
        
        print()
        print("-" * 80)
        print("✓ Pipeline ETL completado exitosamente")
        print()
        print("Para visualizar los resultados:")
        print("  - python scripts/dump_db_to_txt.py")
        print("  - python scripts/export_cross_portal_duplicates.py")
        print("  - python scripts/view_duplicates.py")
        print()
        
    except Exception as e:
        print()
        print("-" * 80)
        print(f"✗ Error durante la ejecución del pipeline: {e}")
        print()
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

