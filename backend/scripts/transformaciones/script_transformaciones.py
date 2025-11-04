import pandas as pd
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import re  # Necesario para la limpieza con expresiones regulares
import time
from pathlib import Path

# METADATA del pipeline de transformaciones
METADATA = {
    "name": "script_transformaciones",
    "description": "ETL de transformaciones: unificación de monedas, geocodificación y limpieza de ubicaciones.",
    "author": "iDatos team",
    "date_created": "2025-11-04",
    "version": "1.0",
}

# --- CONFIGURACIÓN ETL ---

# Moneda base para la unificación: Peso Uruguayo (UYU)
MONEDA_BASE = 'UYU'

# Tasas de cambio (A la fecha de la consulta. AJUSTAR según sea necesario)
TASAS_DE_CAMBIO = {
    'UYU': 1.0,                           # UYU a UYU
    'USD': 39.93,                         # USD a UYU 
    'U$S': 39.93,                         # Símbolo común para Dólar a UYU
    '$': 1.0,                             # Si el símbolo es '$' y está en Uruguay, se asume UYU
    'ARS': 0.0278,                        # ARS a UYU 
    'N/A': 1.0                            # Valor por defecto
}

# Configuración de GeoPy
GEOLOCATOR = Nominatim(user_agent="universidad_proyecto_integracion_datos_2025", timeout=10)
# Limitar la tasa (1 consulta por segundo) para evitar bloqueos
geocode_rate_limit = RateLimiter(GEOLOCATOR.geocode, min_delay_seconds=1.5)


# --- NUEVA FUNCIÓN DE LIMPIEZA DE DIRECCIÓN ---

def limpiar_ubicacion_para_geocodificacion(direccion):
    """
    Limpia la cadena de dirección para mejorar la tasa de éxito de GeoPy.
    Se queda solo con la calle y número/intersección.
    """
    if not isinstance(direccion, str):
        return ''
    
    # 1. Tomar solo la primera parte (antes de la primera coma), que suele ser la calle y número.
    parte_principal = direccion.split(',')[0].strip()
    
    # 2. Limpiar ruidos comunes y estandarizar
    
    # Eliminar números de apartamento/piso (ej: 2336/201)
    # Busca un '/' seguido de números al final del texto o precedido por un espacio
    parte_principal = re.sub(r'\s*/\s*\d+\s*$', '', parte_principal)
    
    # Normalizar intersecciones: reemplazar 'Esq', 'esquina' o 'y' por ' and ' (funciona bien en Nominatim)
    parte_principal = re.sub(r'\s*Esq\.?\s*', ' and ', parte_principal, flags=re.IGNORECASE)
    parte_principal = re.sub(r'\s*esquina\s*', ' and ', parte_principal, flags=re.IGNORECASE)

    # Reemplazar doble espacio por uno simple
    parte_principal = re.sub(r'\s{2,}', ' ', parte_principal).strip()
    
    return parte_principal.strip()


# --- FUNCIONES DE TRANSFORMACIÓN ---

def unificar_monedas(df):
    """
    Convierte la columna 'precio_valor' a la MONEDA_BASE (UYU).
    """
    print("Iniciando unificación de monedas...")
    
    df['precio_valor'] = pd.to_numeric(
        df['precio_valor'], errors='coerce'
    ).fillna(0)
    
    def convertir_a_base(row):
        moneda = str(row['precio_moneda']).upper().strip().replace('$', 'UYU') 
        valor = row['precio_valor']
        tasa = TASAS_DE_CAMBIO.get(moneda, 1.0) 
        return valor * tasa

    df['precio_base_UYU'] = df.apply(convertir_a_base, axis=1)
    
    print(f"[OK] Precios unificados a {MONEDA_BASE}.")
    return df

def geocodificar_direcciones(df):
    """
    Limpia la dirección, luego la convierte en coordenadas (latitud y longitud).
    """
    print("\nIniciando geocodificación de direcciones...")
    
    # PASO 1: APLICAR LA LIMPIEZA
    df['ubicacion_limpia'] = df['ubicacion'].apply(limpiar_ubicacion_para_geocodificacion)
    
    # PASO 2: CONCATENAR CON EL CONTEXTO GEOGRÁFICO
    df['ubicacion_geocodificar'] = df['ubicacion_limpia'] + ', Montevideo, Uruguay'
    
    # PASO 3: Aplicar la geocodificación con RateLimiter
    df['geoloc'] = df['ubicacion_geocodificar'].apply(geocode_rate_limit)
    
    # PASO 4: Extraer latitud y longitud
    df['latitud'] = df['geoloc'].apply(
        lambda loc: loc.latitude if loc else 'N/A'
    )
    df['longitud'] = df['geoloc'].apply(
        lambda loc: loc.longitude if loc else 'N/A'
    )
    
    geocoded_count = len(df[df['geoloc'].notna() & (df['latitud'] != 'N/A')])
    print(f"[OK] {geocoded_count} direcciones geocodificadas con éxito.")
    
    # PASO 5: Limpieza final: eliminar columnas auxiliares
    df = df.drop(columns=['ubicacion_geocodificar', 'geoloc', 'ubicacion_limpia'], errors='ignore')
    
    return df

# --- EJECUCIÓN DEL PROCESO ETL ---
if __name__ == "__main__":
    
    # 1. CARGA: Cargar el DataFrame del script anterior
    try:
        df_crudo = pd.read_csv('mercadolibre_alquileres_con_imagen.csv')
        print(f"Datos crudos cargados. Total de filas: {len(df_crudo)}")
    except FileNotFoundError:
        print("ERROR: No se encontró 'mercadolibre_alquileres_con_imagen.csv'.")
        
        # DataFrame de Prueba con ejemplos problemáticos
        df_crudo = pd.DataFrame({
            'titulo': ['Apartamento con ruido', 'Casa Intersección', 'Loft con código postal'],
            'ubicacion': [
                'Cristóbal Echevarriarza 3471, Pocitos Nuevo, 21 De Setiembre',
                'Eduardo Victor Haedo Esq. Acevedo Diaz, Tres Cruces', 
                'Acosta Y Lara 2336/201 Esq Juan Guzmán, La Blanqueada'
            ],
            'precio_valor': [35000, 1000, 15000],
            'precio_moneda': ['UYU', 'U$S', 'UYU'],
            'imagen_url': ['url1', 'url2', 'url3']
        })
        print("Usando datos de prueba.")
    
    print("\n--- INICIO PROCESO DE TRANSFORMACIÓN (ETL) ---")
    
    # 2. TRANSFORMACIÓN (T)
    df_unificado = unificar_monedas(df_crudo.copy())
    
    # La geocodificación ahora usa la función de limpieza
    df_geocodificado = geocodificar_direcciones(df_unificado)
    
    # 3. EXPOSICIÓN (L): Guardar los datos transformados
    
    nombre_archivo_final_csv = 'datos_transformados_final.csv'
    nombre_archivo_final_txt = 'datos_transformados_final.txt'
    
    # Guardar en CSV
    df_geocodificado.to_csv(nombre_archivo_final_csv, index=False, encoding='utf-8')
    print(f"\n[OK] Resultados guardados en {nombre_archivo_final_csv}")

    # Guardar en TXT
    with open(nombre_archivo_final_txt, 'w', encoding='utf-8') as f:
         f.write("Resultados del Proceso ETL (Moneda y GeoPy)\n\n")
         f.write(df_geocodificado.to_string())
    print(f"[OK] Resultados guardados en {nombre_archivo_final_txt}")

    print("\n--- PROCESO FINALIZADO ---")
    
    # Muestra de los datos transformados
    print("\n--- Muestra de los datos transformados (Precios en UYU y Coordenadas):")
    print(df_geocodificado[['ubicacion', 'precio_moneda', 'precio_valor', 'precio_base_UYU', 'latitud', 'longitud']].head())