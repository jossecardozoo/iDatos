#!/usr/bin/env python
"""
Script para ejecutar el pipeline ETL completo con detección de duplicados usando DBSCAN.

Este script ejecuta el flujo ETL que:
1. Descubre y carga CSVs de la carpeta data/raw/
2. Guarda datos crudos en raw_listings
3. Transforma los datos (geocodificación, normalización, enriquecimiento)
4. Detecta duplicados cross-portal usando DBSCAN (método rápido)
5. Guarda datos transformados en transformed_listings

Uso:
    python scripts/run_etl_with_dbscan.py [--db-path PATH] [--eps EPS]
    
Ejemplos:
    python scripts/run_etl_with_dbscan.py
    python scripts/run_etl_with_dbscan.py --db-path data/custom_database.db
    python scripts/run_etl_with_dbscan.py --eps 0.4
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
        description='Ejecuta el pipeline ETL con detección de duplicados usando DBSCAN (método rápido)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  %(prog)s
  %(prog)s --db-path data/custom_database.db
  %(prog)s --eps 0.4
        """
    )
    parser.add_argument(
        '--db-path',
        type=str,
        default=None,
        help='Ruta personalizada a la base de datos SQLite (default: data/etl_datalake.db)'
    )
    parser.add_argument(
        '--eps',
        type=float,
        default=0.3,
        help='Parámetro eps para DBSCAN (default: 0.3)'
    )
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("EJECUTANDO PIPELINE ETL CON DBSCAN (MÉTODO RÁPIDO)")
    print("=" * 80)
    print()
    
    if args.db_path:
        print(f"Base de datos: {args.db_path}")
    else:
        print("Base de datos: data/etl_datalake.db (default)")
    
    print(f"Método de detección: DBSCAN (eps={args.eps})")
    print()
    print("Iniciando pipeline...")
    print("-" * 80)
    
    try:
        # Ejecutar el pipeline con DBSCAN
        etl_flow(sqlite_path=args.db_path, duplicate_method='dbscan')
        
        print()
        print("-" * 80)
        print("✓ Pipeline ETL completado exitosamente con DBSCAN")
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

