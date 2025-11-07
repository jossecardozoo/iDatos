"""
Script de prueba para el sistema de clustering rápido con DBSCAN.

Compara rendimiento con clustering jerárquico.
"""
import pandas as pd
import sys
import time
from pathlib import Path

# Agregar el directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.etl.clustering_fast import detect_duplicates_by_dbscan
from scripts.etl.clustering import detect_duplicates_by_clustering
from scripts.etl.config import SQLITE_PATH
from sqlalchemy import create_engine


def load_transformed_data(db_path: str = None, sample_size: int = 200):
    """
    Carga una muestra pequeña de datos transformados desde la base de datos.
    
    Args:
        db_path: Ruta a la base de datos
        sample_size: Número de registros a cargar (default: 200 para pruebas rápidas)
    """
    if db_path is None:
        db_path = str(SQLITE_PATH)
    
    engine = create_engine(f'sqlite:///{db_path}')
    
    try:
        # Cargar solo una muestra pequeña para pruebas rápidas
        query = f'SELECT * FROM transformed_listings LIMIT {sample_size}'
        df = pd.read_sql(query, engine)
        print(f"Cargados {len(df)} registros (muestra de {sample_size}) desde transformed_listings")
        return df
    except Exception as e:
        print(f"Error cargando datos: {e}")
        csv_path = Path("data/processed/datos_transformados_final.csv")
        if csv_path.exists():
            print(f"Intentando cargar desde {csv_path}")
            df = pd.read_csv(csv_path)
            # Tomar muestra
            if len(df) > sample_size:
                df = df.sample(n=sample_size, random_state=42)
            print(f"Cargados {len(df)} registros (muestra) desde CSV")
            return df
        raise


def test_dbscan(df: pd.DataFrame, eps: float = 0.3):
    """Prueba DBSCAN con diferentes parámetros."""
    print(f"\n=== Prueba DBSCAN (eps={eps}, {len(df)} registros) ===")
    
    # Buscar columna de fuente
    source_col = None
    for col in df.columns:
        if 'source' in str(col).lower() or col == '__source_file':
            source_col = col
            break
    
    start_time = time.time()
    
    try:
        df_final, df_clusters_info, df_duplicates_records = detect_duplicates_by_dbscan(
            df,
            eps=eps,
            min_samples=2,
            title_col='titulo',
            source_col=source_col,
            logger=None
        )
        
        elapsed = time.time() - start_time
        
        print(f"[OK] Tiempo de ejecucion: {elapsed:.2f} segundos")
        print(f"[OK] Clusters detectados: {len(df_clusters_info)}")
        print(f"[OK] Duplicados identificados: {len(df_duplicates_records)}")
        
        if not df_clusters_info.empty:
            print(f"\nTop 5 clusters por similaridad:")
            top_clusters = df_clusters_info.nlargest(5, 'similarity_score')
            for idx, row in top_clusters.iterrows():
                print(f"\n  Cluster {row['cluster_id']}:")
                print(f"    Similaridad: {row['similarity_score']:.2f}%")
                print(f"    Tamaño: {row['cluster_size']} ofertas")
                print(f"    Primario: '{row['primary_titulo'][:60]}...'")
                print(f"    Duplicado: '{row['duplicate_titulo'][:60]}...'")
        
        return df_final, df_clusters_info, df_duplicates_records, elapsed
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"[ERROR] Error: {e}")
        print(f"[INFO] Tiempo transcurrido: {elapsed:.2f} segundos")
        return df, pd.DataFrame(), pd.DataFrame(), elapsed


def compare_methods(df: pd.DataFrame, max_rows: int = 100):
    """
    Compara DBSCAN vs Clustering Jerárquico usando una muestra pequeña.
    
    Args:
        df: DataFrame completo
        max_rows: Número máximo de filas a usar para comparación (default: 100)
    """
    print("\n" + "=" * 80)
    print("COMPARACIÓN DE MÉTODOS")
    print(f"(Usando muestra de {min(len(df), max_rows)} registros para comparación rápida)")
    print("=" * 80)
    
    # Usar solo una muestra pequeña para comparación
    df_sample = df.head(max_rows).copy() if len(df) > max_rows else df.copy()
    
    # Probar DBSCAN
    print("\n--- DBSCAN (Método Rápido) ---")
    try:
        _, df_clusters_dbscan, df_dups_dbscan, time_dbscan = test_dbscan(df_sample, eps=0.3)
    except Exception as e:
        print(f"Error con DBSCAN: {e}")
        time_dbscan = float('inf')
        df_clusters_dbscan = pd.DataFrame()
        df_dups_dbscan = pd.DataFrame()
    
    # Probar Clustering Jerárquico (solo muestra pequeña)
    print("\n--- Clustering Jerárquico (Método Lento) ---")
    print(f"(Usando {len(df_sample)} registros para comparación justa...)")
    
    try:
        start_time = time.time()
        _, df_clusters_hier, df_dups_hier = detect_duplicates_by_clustering(
            df_sample,
            similarity_threshold=75.0,
            title_col='titulo',
            source_col=None,
            logger=None
        )
        time_hier = time.time() - start_time
        print(f"Tiempo de ejecución: {time_hier:.2f} segundos")
        print(f"Clusters detectados: {len(df_clusters_hier)}")
        print(f"Duplicados identificados: {len(df_dups_hier)}")
    except Exception as e:
        print(f"Error con Clustering Jerárquico: {e}")
        time_hier = float('inf')
        df_clusters_hier = pd.DataFrame()
        df_dups_hier = pd.DataFrame()
    
    # Resumen comparativo
    print("\n" + "=" * 80)
    print("RESUMEN COMPARATIVO")
    print("=" * 80)
    print(f"{'Método':<30} {'Tiempo (s)':<15} {'Clusters':<15} {'Duplicados':<15}")
    print("-" * 75)
    print(f"{'DBSCAN (rápido)':<30} {time_dbscan:<15.2f} {len(df_clusters_dbscan):<15} {len(df_dups_dbscan):<15}")
    if time_hier != float('inf'):
        print(f"{'Jerárquico':<30} {time_hier:<15.2f} {len(df_clusters_hier):<15} {len(df_dups_hier):<15}")
        if time_dbscan > 0 and time_dbscan != float('inf'):
            speedup = time_hier / time_dbscan
            print(f"\nDBSCAN es aproximadamente {speedup:.1f}x más rápido")
    
    return {
        'dbscan': {'time': time_dbscan, 'clusters': len(df_clusters_dbscan), 'dups': len(df_dups_dbscan)},
        'hierarchical': {'time': time_hier, 'clusters': len(df_clusters_hier), 'dups': len(df_dups_hier)}
    }


def main():
    """Función principal."""
    print("=" * 80)
    print("SISTEMA DE CLUSTERING RÁPIDO (DBSCAN) PARA DETECCIÓN DE DUPLICADOS")
    print("=" * 80)
    
    # Configuración: usar muestra pequeña para pruebas rápidas
    SAMPLE_SIZE = 500  # Cambiar aquí para ajustar tamaño de muestra
    COMPARISON_SIZE = 200  # Tamaño para comparación entre métodos
    
    print(f"\n[INFO] Usando muestra de {SAMPLE_SIZE} registros para pruebas rapidas")
    print(f"       (Para comparacion: {COMPARISON_SIZE} registros)\n")
    
    # Cargar datos (muestra pequeña)
    try:
        df = load_transformed_data(sample_size=SAMPLE_SIZE)
    except Exception as e:
        print(f"Error cargando datos: {e}")
        return
    
    if df.empty:
        print("No hay datos para procesar")
        return
    
    if 'titulo' not in df.columns:
        print("Error: No se encuentra la columna 'titulo'")
        return
    
    # Probar diferentes valores de eps (solo con muestra)
    print("\n" + "=" * 80)
    print("PRUEBAS CON DIFERENTES PARÁMETROS (DBSCAN)")
    print("=" * 80)
    
    eps_values = [0.2, 0.3, 0.4, 0.5]
    results = {}
    
    for eps in eps_values:
        print(f"\n{'='*80}")
        try:
            _, df_clusters, df_dups, elapsed = test_dbscan(df, eps=eps)
            results[eps] = {
                'time': elapsed,
                'clusters': len(df_clusters),
                'duplicates': len(df_dups)
            }
        except Exception as e:
            print(f"Error con eps={eps}: {e}")
            results[eps] = {'time': 0, 'clusters': 0, 'duplicates': 0}
    
    # Resumen de parámetros
    print("\n" + "=" * 80)
    print("RESUMEN POR PARÁMETROS")
    print("=" * 80)
    print(f"{'EPS':<10} {'Tiempo (s)':<15} {'Clusters':<15} {'Duplicados':<15}")
    print("-" * 55)
    for eps, result in results.items():
        print(f"{eps:<10.1f} {result['time']:<15.2f} {result['clusters']:<15} {result['duplicates']:<15}")
    
    # Comparar con método jerárquico (solo muestra pequeña)
    print("\n" + "=" * 80)
    compare_methods(df, max_rows=COMPARISON_SIZE)
    
    print("\n" + "=" * 80)
    print("EXPERIMENTO COMPLETADO")
    print("=" * 80)
    print(f"\n[TIP] Para procesar todos los datos, usa detect_duplicates_by_dbscan() directamente")
    print(f"      con el DataFrame completo. DBSCAN es mucho mas rapido que el metodo jerarquico.")


if __name__ == "__main__":
    main()

