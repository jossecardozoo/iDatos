#!/usr/bin/env python
"""
Script para ejecutar SOLO la detección de duplicados sobre datos ya transformados.

Este script carga los datos de transformed_listings y aplica detección de duplicados
sin ejecutar todo el pipeline ETL.

Métodos disponibles:
- coordinates: Detección por coordenadas exactas (rápido, método original)
- dbscan: Detección con DBSCAN (rápido, recomendado)
- hierarchical: Detección con clustering jerárquico (lento, preciso)

Uso:
    python scripts/detect_duplicates_only.py [--method METHOD] [--db-path PATH] [--options]
    
Ejemplos:
    # Método por coordenadas (original)
    python scripts/detect_duplicates_only.py --method coordinates
    
    # Método DBSCAN (recomendado)
    python scripts/detect_duplicates_only.py --method dbscan
    python scripts/detect_duplicates_only.py --method dbscan --eps 0.4
    
    # Método jerárquico (lento)
    python scripts/detect_duplicates_only.py --method hierarchical
    python scripts/detect_duplicates_only.py --method hierarchical --threshold 80.0
"""
import sys
import argparse
from pathlib import Path
import pandas as pd
from sqlalchemy import create_engine

# Añadir el directorio backend al path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from scripts.etl.config import SQLITE_PATH
from scripts.etl.deduplication import (
    detect_duplicates_by_coordinates,
    save_duplicates_to_table,
    save_duplicate_records_to_table
)
from scripts.etl.clustering_fast import detect_duplicates_by_dbscan
from scripts.etl.clustering import detect_duplicates_by_clustering


def load_transformed_data(db_path: str):
    """Carga datos transformados desde la base de datos."""
    engine = create_engine(f'sqlite:///{db_path}')
    df = pd.read_sql('SELECT * FROM transformed_listings', engine)
    return df, engine


def main():
    parser = argparse.ArgumentParser(
        description='Ejecuta SOLO la detección de duplicados sobre datos transformados',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Métodos disponibles:
  coordinates  - Detección por coordenadas exactas (rápido, método original)
  dbscan       - Detección con DBSCAN (rápido, recomendado) ⭐
  hierarchical - Detección con clustering jerárquico (lento, preciso)

Ejemplos:
  %(prog)s --method coordinates
  %(prog)s --method dbscan --eps 0.4
  %(prog)s --method hierarchical --threshold 80.0
        """
    )
    
    parser.add_argument(
        '--method',
        type=str,
        choices=['coordinates', 'dbscan', 'hierarchical'],
        default='coordinates',
        help='Método de detección de duplicados (default: coordinates)'
    )
    
    parser.add_argument(
        '--db-path',
        type=str,
        default=None,
        help='Ruta a la base de datos SQLite (default: data/etl_datalake.db)'
    )
    
    # Opciones específicas para DBSCAN
    parser.add_argument(
        '--eps',
        type=float,
        default=0.3,
        help='Parámetro eps para DBSCAN (default: 0.3, solo para --method dbscan)'
    )
    
    # Opciones específicas para clustering jerárquico
    parser.add_argument(
        '--threshold',
        type=float,
        default=75.0,
        help='Umbral de similaridad para clustering jerárquico (default: 75.0, solo para --method hierarchical)'
    )
    
    args = parser.parse_args()
    
    # Determinar ruta de base de datos
    db_path = args.db_path if args.db_path else str(SQLITE_PATH)
    
    print("=" * 80)
    print("DETECCIÓN DE DUPLICADOS (SOLO)")
    print("=" * 80)
    print()
    print(f"Base de datos: {db_path}")
    print(f"Método: {args.method}")
    
    if args.method == 'dbscan':
        print(f"Parámetro eps: {args.eps}")
    elif args.method == 'hierarchical':
        print(f"Umbral de similaridad: {args.threshold}")
        print()
        print("⚠️  ADVERTENCIA: Este método es MUY LENTO")
        respuesta = input("¿Desea continuar? (s/n): ")
        if respuesta.lower() != 's':
            print("Operación cancelada.")
            return
    
    print()
    print("Cargando datos transformados...")
    print("-" * 80)
    
    try:
        # Cargar datos
        df, engine = load_transformed_data(db_path)
        engine_url = f'sqlite:///{db_path}'
        
        print(f"✓ Cargados {len(df)} registros desde transformed_listings")
        print()
        print("Iniciando detección de duplicados...")
        print("-" * 80)
        
        # Ejecutar detección según método
        if args.method == 'coordinates':
            print("Método: Coordenadas exactas")
            df_final, df_duplicates_info, df_duplicates_records = detect_duplicates_by_coordinates(
                df,
                logger=None
            )
        elif args.method == 'dbscan':
            print("Método: DBSCAN (rápido)")
            df_final, df_duplicates_info, df_duplicates_records = detect_duplicates_by_dbscan(
                df,
                eps=args.eps,
                min_samples=2,
                title_col='titulo',
                source_col=None,
                logger=None
            )
        else:  # hierarchical
            print("Método: Clustering Jerárquico (lento)")
            df_final, df_duplicates_info, df_duplicates_records = detect_duplicates_by_clustering(
                df,
                similarity_threshold=args.threshold,
                title_col='titulo',
                source_col=None,
                logger=None
            )
        
        # Guardar resultados
        print()
        print("Guardando resultados...")
        print("-" * 80)
        
        if not df_duplicates_info.empty:
            save_duplicates_to_table(df_duplicates_info, engine_url, table_name='duplicates_detected', logger=None)
            print(f"✓ Metadatos de duplicados guardados: {len(df_duplicates_info)} registros")
        
        if not df_duplicates_records.empty:
            save_duplicate_records_to_table(df_duplicates_records, engine_url, table_name='duplicates_moved', logger=None)
            print(f"✓ Registros duplicados movidos: {len(df_duplicates_records)} registros")
        
        print()
        print("-" * 80)
        print("✓ Detección de duplicados completada")
        print()
        print(f"Resumen:")
        print(f"  - Total de registros: {len(df_final)}")
        print(f"  - Pares de duplicados detectados: {len(df_duplicates_info)}")
        print(f"  - Registros marcados como duplicados: {len(df_duplicates_records)}")
        print()
        print("Para visualizar los resultados:")
        print("  - python scripts/view_duplicates.py")
        print("  - python scripts/export_cross_portal_duplicates.py")
        print()
        
    except Exception as e:
        print()
        print("-" * 80)
        print(f"✗ Error durante la detección de duplicados: {e}")
        print()
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

