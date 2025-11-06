#!/usr/bin/env python
"""
Script para ejecutar el pipeline ETL completo (incluye scrapers).

Este script ejecuta el flujo ETL completo que:
1. Ejecuta scrapers para obtener datos de portales inmobiliarios
2. Limpia y normaliza direcciones
3. Geocodifica direcciones en batch
4. Carga datos crudos en raw_listings
5. Transforma los datos (normalización, enriquecimiento)
6. Detecta duplicados cross-portal y los mueve a tabla separada
7. Guarda datos transformados en transformed_listings

Uso:
    python scripts/run_full_pipeline.py [--db-path PATH] [--gallito-limit N] [--dry-run]
    
Ejemplos:
    python scripts/run_full_pipeline.py
    python scripts/run_full_pipeline.py --db-path data/custom_database.db
    python scripts/run_full_pipeline.py --gallito-limit 50 --dry-run
"""
import sys
import argparse
from pathlib import Path

# Añadir el directorio backend al path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from scripts.etl_functions_prefect import full_etl_pipeline


def main():
    parser = argparse.ArgumentParser(
        description='Ejecuta el pipeline ETL completo (incluye scrapers)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  %(prog)s
  %(prog)s --db-path data/custom_database.db
  %(prog)s --gallito-limit 50 --dry-run
  %(prog)s --dry-run
        """
    )
    parser.add_argument(
        '--db-path',
        type=str,
        default='',
        help='Ruta a la base de datos SQLite (default: data/etl_datalake.db)'
    )
    parser.add_argument(
        '--gallito-limit',
        type=int,
        default=0,
        help='Límite de registros a scrapear de Gallito (0 = sin límite, default: 0)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Ejecutar en modo dry-run (sin scrapers ni geocodificación)'
    )
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("EJECUTANDO PIPELINE ETL COMPLETO")
    print("=" * 80)
    print()
    
    if args.db_path:
        print(f"Base de datos: {args.db_path}")
    else:
        print("Base de datos: data/etl_datalake.db (default)")
    
    if args.gallito_limit > 0:
        print(f"Límite Gallito: {args.gallito_limit} registros")
    else:
        print("Límite Gallito: Sin límite")
    
    if args.dry_run:
        print("Modo: DRY-RUN (sin scrapers ni geocodificación)")
    else:
        print("Modo: COMPLETO (incluye scrapers y geocodificación)")
    
    print()
    print("Iniciando pipeline completo...")
    print("-" * 80)
    
    try:
        # Ejecutar el pipeline completo
        full_etl_pipeline(
            db_path=args.db_path if args.db_path else None,
            gallito_limit=args.gallito_limit,
            dry_run=args.dry_run
        )
        
        print()
        print("-" * 80)
        print("✓ Pipeline ETL completo finalizado exitosamente")
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

