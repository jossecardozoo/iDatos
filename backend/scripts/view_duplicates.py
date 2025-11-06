"""
Script para visualizar información de duplicados cross-portal.

Muestra estadísticas y detalles de los duplicados detectados entre diferentes portales.
Solo muestra duplicados cross-portal (los duplicados del mismo portal se ignoran).
"""
import sqlite3
import pandas as pd

conn = sqlite3.connect('data/etl_datalake.db')

print("=" * 80)
print("TABLA: duplicates_detected")
print("=" * 80)

# Estructura de la tabla
print("\n=== ESTRUCTURA DE LA TABLA ===")
cursor = conn.cursor()
cursor.execute('PRAGMA table_info(duplicates_detected)')
columns = cursor.fetchall()
for col in columns:
    print(f"  {col[1]}: {col[2]}")

# Total de registros
total = pd.read_sql_query('SELECT COUNT(*) as total FROM duplicates_detected', conn).iloc[0]['total']
print(f"\n=== TOTAL DE REGISTROS: {total} ===")

# Resumen por tipo de duplicado
print("\n=== RESUMEN POR TIPO DE DUPLICADO ===")
df_summary = pd.read_sql_query(
    'SELECT is_cross_portal, COUNT(*) as count FROM duplicates_detected GROUP BY is_cross_portal',
    conn
)
print(df_summary.to_string(index=False))

# Duplicados cross-portal
print("\n=== DUPLICADOS CROSS-PORTAL (15 registros) ===")
df_cross = pd.read_sql_query(
    '''SELECT 
        primary_source, 
        duplicate_source, 
        distance_meters,
        primary_titulo, 
        duplicate_titulo,
        primary_ubicacion,
        duplicate_ubicacion
    FROM duplicates_detected 
    WHERE is_cross_portal = 1 
    LIMIT 15''',
    conn
)
print(df_cross.to_string(index=False))

# Estadísticas por fuente
print("\n=== ESTADÍSTICAS POR FUENTE ===")
df_source = pd.read_sql_query(
    '''SELECT 
        primary_source, 
        duplicate_source,
        COUNT(*) as count
    FROM duplicates_detected 
    GROUP BY primary_source, duplicate_source
    ORDER BY count DESC
    LIMIT 10''',
    conn
)
print(df_source.to_string(index=False))

# Muestra de duplicados del mismo portal
print("\n=== MUESTRA DE DUPLICADOS DEL MISMO PORTAL (5 primeros) ===")
df_same = pd.read_sql_query(
    '''SELECT 
        primary_source, 
        duplicate_source,
        distance_meters,
        primary_titulo,
        duplicate_titulo
    FROM duplicates_detected 
    WHERE is_cross_portal = 0 
    LIMIT 5''',
    conn
)
print(df_same.to_string(index=False))

conn.close()

