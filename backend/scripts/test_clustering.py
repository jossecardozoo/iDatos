"""
Script de prueba para el sistema de clustering jerárquico.

Ejecuta el clustering sobre los datos transformados y genera reportes.
"""
import pandas as pd
import sys
from pathlib import Path

# Agregar el directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.etl.clustering import (
    detect_duplicates_by_clustering,
    lexical_similarity,
    calculate_article_score,
    hierarchical_clustering_bottom_up,
    calculate_combined_similarity,
    compare_location,
    compare_price,
    compare_physical_features
)
from scripts.etl.config import SQLITE_PATH
from sqlalchemy import create_engine


def load_transformed_data(db_path: str = None):
    """Carga los datos transformados desde la base de datos."""
    if db_path is None:
        db_path = str(SQLITE_PATH)
    
    engine = create_engine(f'sqlite:///{db_path}')
    
    try:
        df = pd.read_sql('SELECT * FROM transformed_listings', engine)
        print(f"Cargados {len(df)} registros desde transformed_listings")
        return df
    except Exception as e:
        print(f"Error cargando datos: {e}")
        # Intentar cargar desde CSV como fallback
        csv_path = Path("data/processed/datos_transformados_final.csv")
        if csv_path.exists():
            print(f"Intentando cargar desde {csv_path}")
            df = pd.read_csv(csv_path)
            print(f"Cargados {len(df)} registros desde CSV")
            return df
        raise


def test_lexical_similarity():
    """Prueba la función de similaridad lexicográfica."""
    print("\n=== Prueba de Similaridad Lexicográfica ===")
    
    test_cases = [
        ("Apartamento 2 dormitorios Pocitos", "Apto 2 dorms Pocitos"),
        ("Casa 3 habitaciones Centro", "Casa 3 hab Centro"),
        ("Departamento en Malvín", "Depto Malvín"),
        ("Alquiler completamente diferente", "Casa en otro barrio"),
    ]
    
    for title1, title2 in test_cases:
        similarity = lexical_similarity(title1, title2)
        print(f"'{title1}' vs '{title2}': {similarity:.2f}% similar")


def test_scoring():
    """Prueba el sistema de scoring."""
    print("\n=== Prueba de Sistema de Scoring ===")
    
    from scripts.etl.clustering import calculate_article_score
    
    # Crear datos de prueba
    test_data = {
        'titulo': ['Apartamento en Pocitos', 'Casa en Centro'],
        'precio_base_uyu': [25000, 30000],
        'dorms': [2, 3],
        'banos': [1, 2],
        'superficie_m2': [60, 80],
        'latitud': [-34.9, -34.9],
        'longitud': [-56.15, -56.15],
        'ubicacion': ['Pocitos, Montevideo', 'Centro, Montevideo'],
    }
    df_test = pd.DataFrame(test_data)
    
    for idx, row in df_test.iterrows():
        score = calculate_article_score(row, cluster_rows=None)
        print(f"Alquiler {idx} ('{row['titulo']}'): Score = {score:.2f}")


def run_clustering_experiment(df: pd.DataFrame, similarity_threshold: float = 75.0):
    """Ejecuta el experimento de clustering."""
    print(f"\n=== Experimento de Clustering (umbral={similarity_threshold}) ===")
    
    # Buscar columna de fuente
    source_col = None
    for col in df.columns:
        if 'source' in str(col).lower() or col == '__source_file':
            source_col = col
            break
    
    print(f"Usando columna de fuente: {source_col}")
    print(f"Total de ofertas: {len(df)}")
    
    # Ejecutar clustering
    df_final, df_clusters_info, df_duplicates_records = detect_duplicates_by_clustering(
        df,
        similarity_threshold=similarity_threshold,
        title_col='titulo',
        source_col=source_col,
        logger=None
    )
    
    # Mostrar resultados
    print(f"\nResultados:")
    print(f"- Registros totales: {len(df_final)}")
    print(f"- Clusters detectados: {len(df_clusters_info)}")
    print(f"- Duplicados identificados: {len(df_duplicates_records)}")
    
    if not df_clusters_info.empty:
        print(f"\nTop 10 clusters por similaridad:")
        top_clusters = df_clusters_info.nlargest(10, 'similarity_score')
        for idx, row in top_clusters.iterrows():
            print(f"\n  Cluster {row['cluster_id']}:")
            print(f"    Similaridad: {row['similarity_score']:.2f}%")
            print(f"    Tamaño: {row['cluster_size']} ofertas")
            print(f"    Cross-portal: {row['is_cross_portal']}")
            print(f"    Primario: '{row['primary_titulo'][:50]}...'")
            print(f"    Duplicado: '{row['duplicate_titulo'][:50]}...'")
            print(f"    Score primario: {row['primary_score']:.2f}")
            print(f"    Score duplicado: {row['duplicate_score']:.2f}")
    
    return df_final, df_clusters_info, df_duplicates_records


def compare_with_coordinates_method(df: pd.DataFrame):
    """Compara resultados con el método de coordenadas."""
    print("\n=== Comparación con Método de Coordenadas ===")
    
    from scripts.etl.deduplication import detect_duplicates_by_coordinates
    
    # Ejecutar método de coordenadas
    df_coords, df_duplicates_coords, df_records_coords = detect_duplicates_by_coordinates(
        df,
        logger=None
    )
    
    print(f"Método de coordenadas:")
    print(f"- Duplicados detectados: {len(df_records_coords)}")
    print(f"- Pares de duplicados: {len(df_duplicates_coords)}")
    
    return df_duplicates_coords, df_records_coords


def main():
    """Función principal."""
    print("=" * 80)
    print("SISTEMA DE CLUSTERING JERÁRQUICO PARA DETECCIÓN DE DUPLICADOS")
    print("=" * 80)
    
    # Cargar datos
    try:
        df = load_transformed_data()
    except Exception as e:
        print(f"Error cargando datos: {e}")
        return
    
    # Verificar que tenemos datos
    if df.empty:
        print("No hay datos para procesar")
        return
    
    # Verificar columnas necesarias
    if 'titulo' not in df.columns:
        print("Error: No se encuentra la columna 'titulo'")
        print(f"Columnas disponibles: {list(df.columns)}")
        return
    
    # Pruebas unitarias
    test_lexical_similarity()
    test_scoring()
    
    # Experimento principal
    print("\n" + "=" * 80)
    print("EXPERIMENTO PRINCIPAL")
    print("=" * 80)
    
    # Probar con diferentes umbrales
    thresholds = [70.0, 75.0, 80.0]
    
    results = {}
    for threshold in thresholds:
        print(f"\n{'='*80}")
        df_final, df_clusters, df_duplicates = run_clustering_experiment(df, threshold)
        results[threshold] = {
            'clusters': len(df_clusters),
            'duplicates': len(df_duplicates),
            'df_clusters': df_clusters,
            'df_duplicates': df_duplicates
        }
    
    # Comparar con método de coordenadas
    print("\n" + "=" * 80)
    compare_with_coordinates_method(df)
    
    # Resumen
    print("\n" + "=" * 80)
    print("RESUMEN DE RESULTADOS")
    print("=" * 80)
    print(f"{'Umbral':<10} {'Clusters':<15} {'Duplicados':<15}")
    print("-" * 40)
    for threshold, result in results.items():
        print(f"{threshold:<10.1f} {result['clusters']:<15} {result['duplicates']:<15}")
    
    # Guardar resultados
    output_dir = Path("data/intermediate")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    for threshold, result in results.items():
        if not result['df_clusters'].empty:
            output_file = output_dir / f"clusters_threshold_{threshold:.0f}.csv"
            result['df_clusters'].to_csv(output_file, index=False, encoding='utf-8')
            print(f"\nResultados guardados en: {output_file}")
    
    print("\n" + "=" * 80)
    print("EXPERIMENTO COMPLETADO")
    print("=" * 80)


if __name__ == "__main__":
    main()

