#!/usr/bin/env python
"""
Script para ejecutar el pipeline ETL completo con detección de duplicados usando clustering jerárquico.

Este script ejecuta el flujo ETL que:
1. Descubre y carga CSVs de la carpeta data/raw/
2. Guarda datos crudos en raw_listings
3. Transforma los datos (geocodificación, normalización, enriquecimiento)
4. Detecta duplicados cross-portal usando clustering jerárquico (método preciso pero lento)
5. Guarda datos transformados en transformed_listings

⚠️ ADVERTENCIA: Este método es MUY LENTO (puede tardar horas con muchos datos).
   Se recomienda usar DBSCAN para producción.

Uso:
    python scripts/run_etl_with_hierarchical.py [--db-path PATH] [--threshold THRESHOLD]
    
Ejemplos:
    python scripts/run_etl_with_hierarchical.py
    python scripts/run_etl_with_hierarchical.py --db-path data/custom_database.db
    python scripts/run_etl_with_hierarchical.py --threshold 80.0
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
        description='Ejecuta el pipeline ETL con detección de duplicados usando clustering jerárquico (lento)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  %(prog)s
  %(prog)s --db-path data/custom_database.db
  %(prog)s --threshold 80.0
  
⚠️  ADVERTENCIA: Este método es MUY LENTO. Use DBSCAN para producción.
        """
    )
    parser.add_argument(
        '--db-path',
        type=str,
        default=None,
        help='Ruta personalizada a la base de datos SQLite (default: data/etl_datalake.db)'
    )
    parser.add_argument(
        '--threshold',
        type=float,
        default=75.0,
        help='Umbral de similaridad para clustering jerárquico (default: 75.0)'
    )
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("EJECUTANDO PIPELINE ETL CON CLUSTERING JERÁRQUICO")
    print("=" * 80)
    print()
    print("⚠️  ADVERTENCIA: Este método es MUY LENTO (puede tardar horas)")
    print("   Se recomienda usar DBSCAN para producción.")
    print()
    
    if args.db_path:
        print(f"Base de datos: {args.db_path}")
    else:
        print("Base de datos: data/etl_datalake.db (default)")
    
    print(f"Método de detección: Clustering Jerárquico (threshold={args.threshold})")
    print()
    
    respuesta = input("¿Desea continuar? (s/n): ")
    if respuesta.lower() != 's':
        print("Operación cancelada.")
        return
    
    print()
    print("Iniciando pipeline...")
    print("-" * 80)
    
    try:
        # Ejecutar el pipeline con clustering jerárquico
        etl_flow(sqlite_path=args.db_path, duplicate_method='hierarchical')
        
        print()
        print("-" * 80)
        print("✓ Pipeline ETL completado exitosamente con clustering jerárquico")
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

