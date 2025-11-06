"""
Script para exportar duplicados cross-portal a un archivo de texto.

Genera un archivo legible con información sobre los duplicados detectados
entre diferentes portales inmobiliarios.
"""
from pathlib import Path
import sqlite3
import pandas as pd
from datetime import datetime

BASE = Path(__file__).resolve().parents[1]
DB_PATH = BASE / 'data' / 'etl_datalake.db'
OUT_DIR = BASE / 'data'
OUT_FILE = OUT_DIR / 'duplicados_cross_portal.txt'

if not DB_PATH.exists():
    print(f"Error: Base de datos no encontrada en {DB_PATH}")
    raise SystemExit(1)

OUT_DIR.mkdir(parents=True, exist_ok=True)

print(f"Conectando a base de datos: {DB_PATH}")
conn = sqlite3.connect(str(DB_PATH))

# Consultar duplicados cross-portal desde duplicates_moved
print("Consultando duplicados cross-portal...")
df_duplicates = pd.read_sql_query(
    '''SELECT 
        titulo,
        ubicacion,
        precio_base_uyu,
        fuente,
        source_file,
        latitud,
        longitud,
        moved_at,
        reason
    FROM duplicates_moved
    ORDER BY source_file, titulo''',
    conn
)

# También obtener información de duplicates_detected para ver los pares
df_pairs = pd.read_sql_query(
    '''SELECT 
        primary_source,
        duplicate_source,
        primary_titulo,
        duplicate_titulo,
        primary_ubicacion,
        duplicate_ubicacion,
        distance_meters,
        primary_lat,
        primary_lon,
        detected_at
    FROM duplicates_detected
    WHERE is_cross_portal = 1
    ORDER BY primary_source, duplicate_source, primary_titulo''',
    conn
)

conn.close()

# Escribir archivo de texto
with open(OUT_FILE, 'w', encoding='utf-8') as f:
    f.write("=" * 100 + "\n")
    f.write("DUPLICADOS CROSS-PORTAL DETECTADOS\n")
    f.write("=" * 100 + "\n")
    f.write(f"\nFecha de generación: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write(f"Total de registros duplicados movidos: {len(df_duplicates)}\n")
    f.write(f"Total de pares de duplicados detectados: {len(df_pairs)}\n")
    
    f.write("\n" + "=" * 100 + "\n")
    f.write("RESUMEN EJECUTIVO\n")
    f.write("=" * 100 + "\n\n")
    
    # Estadísticas por fuente
    if not df_pairs.empty:
        f.write("Distribución de duplicados cross-portal por fuente:\n")
        f.write("-" * 100 + "\n")
        source_counts = df_pairs.groupby(['primary_source', 'duplicate_source']).size().reset_index(name='count')
        for _, row in source_counts.iterrows():
            f.write(f"  {row['primary_source']} <-> {row['duplicate_source']}: {row['count']} pares\n")
        f.write("\n")
    
    f.write("\n" + "=" * 100 + "\n")
    f.write("REGISTROS MOVIDOS A TABLA duplicates_moved\n")
    f.write("=" * 100 + "\n\n")
    
    if df_duplicates.empty:
        f.write("No hay registros duplicados cross-portal movidos.\n")
    else:
        for idx, row in df_duplicates.iterrows():
            f.write(f"\n{'='*100}\n")
            f.write(f"Registro #{idx + 1}\n")
            f.write(f"{'='*100}\n")
            f.write(f"Título: {row.get('titulo', 'N/A')}\n")
            f.write(f"Ubicación: {row.get('ubicacion', 'N/A')}\n")
            f.write(f"Precio (UYU): {row.get('precio_base_uyu', 'N/A')}\n")
            f.write(f"Fuente: {row.get('fuente', 'N/A')}\n")
            f.write(f"Archivo origen: {row.get('source_file', 'N/A')}\n")
            f.write(f"Coordenadas: Lat {row.get('latitud', 'N/A')}, Lon {row.get('longitud', 'N/A')}\n")
            f.write(f"Fecha de movimiento: {row.get('moved_at', 'N/A')}\n")
            f.write(f"Razón: {row.get('reason', 'N/A')}\n")
    
    f.write("\n\n" + "=" * 100 + "\n")
    f.write("PARES DE DUPLICADOS DETECTADOS\n")
    f.write("=" * 100 + "\n\n")
    
    if df_pairs.empty:
        f.write("No se detectaron pares de duplicados cross-portal.\n")
    else:
        for idx, row in df_pairs.iterrows():
            f.write(f"\n{'='*100}\n")
            f.write(f"Par #{idx + 1}\n")
            f.write(f"{'='*100}\n")
            f.write(f"Fuente primaria: {row.get('primary_source', 'N/A')}\n")
            f.write(f"  - Título: {row.get('primary_titulo', 'N/A')}\n")
            f.write(f"  - Ubicación: {row.get('primary_ubicacion', 'N/A')}\n")
            f.write(f"  - Coordenadas: Lat {row.get('primary_lat', 'N/A')}, Lon {row.get('primary_lon', 'N/A')}\n")
            f.write(f"\nFuente duplicada: {row.get('duplicate_source', 'N/A')}\n")
            f.write(f"  - Título: {row.get('duplicate_titulo', 'N/A')}\n")
            f.write(f"  - Ubicación: {row.get('duplicate_ubicacion', 'N/A')}\n")
            f.write(f"  - Distancia: {row.get('distance_meters', 'N/A')} metros\n")
            f.write(f"\nFecha de detección: {row.get('detected_at', 'N/A')}\n")
    
    f.write("\n\n" + "=" * 100 + "\n")
    f.write("NOTAS\n")
    f.write("=" * 100 + "\n")
    f.write("""
- Estos duplicados fueron detectados usando coordenadas exactamente iguales (latitud y longitud idénticas)
- Solo se consideran duplicados cross-portal (entre diferentes portales)
- Los registros duplicados cross-portal se movieron a la tabla 'duplicates_moved'
- Los registros permanecen en 'transformed_listings' para análisis
- Los duplicados dentro del mismo portal no se procesan

Para más información, consultar:
- Tabla 'duplicates_detected': Metadatos de todos los duplicados detectados
- Tabla 'duplicates_moved': Registros completos de duplicados cross-portal movidos
- Tabla 'transformed_listings': Todos los registros transformados
""")

print(f"\nArchivo generado exitosamente: {OUT_FILE}")
print(f"Total de registros exportados: {len(df_duplicates)}")
print(f"Total de pares de duplicados: {len(df_pairs)}")

