import pandas as pd
from fuzzywuzzy import fuzz
import re
import time
# Se requiere 'fuzzywuzzy' y 'python-levenshtein' (para acelerar)

# --- CONFIGURACIÓN DE ARCHIVOS Y UMBRAL ---

ML_FILE = 'mercadolibre_alquileres_con_imagen.csv'
GALLITO_FILE = 'gallito_alquileres_crudos.csv'
OUTPUT_FILE = 'coincidencias_ml_gallito.csv'

# Umbral de similaridad (0-100). Usamos 85.
SIMILARITY_THRESHOLD = 85 

# --- FUNCIÓN DE PREPROCESAMIENTO ---

def normalize_text(text):
    """Limpia y normaliza el texto para mejorar la precisión del matching."""
    if pd.isna(text):
        return ""
    text = str(text).lower()
    
    # 1. Eliminar caracteres especiales y puntuación
    text = re.sub(r'[^a-z0-9\s]', '', text)
    
    # 2. Eliminar palabras comunes o "ruido" que no ayudan a la identificación (opcional pero útil)
    # Se añade 'alquiler' y 'apartamento' a la lista de ruido para mejorar el matching entre títulos
    words_to_remove = r'\b(en|alquiler|de|para|con|y|o|el|la|los|las|un|una|unos|unas|apartamento|casa|dormitorio|baño|baños|dormitorios)\b'
    text = re.sub(words_to_remove, '', text).strip()
    
    # 3. Eliminar espacios duplicados
    return ' '.join(text.split())

# --- FUNCIÓN DE DETECCIÓN DE DUPLICADOS CORREGIDA ---

def detect_duplicates(df_ml, df_gallito):
    """
    Compara títulos entre los dos DataFrames usando 'fuzzywuzzy', 
    eliminando duplicados internos y guardando solo el mejor match por anuncio de ML.
    """
    
    # --- 1. Deduplicación de Inputs (CRUCIAL PARA ELIMINAR REPETICIÓN) ---
    # ML: No tiene URL de listing, usamos Título + Ubicación
    df_ml_unique = df_ml.drop_duplicates(subset=['titulo', 'ubicacion'], keep='first').reset_index(drop=True)
    
    # Gallito: Usa la URL para una deduplicación más precisa, ya que el script de Gallito la captura.
    # Usamos 'titulo' y 'ubicacion' si 'url' no existe.
    dedup_subset_gallito = ['url'] if 'url' in df_gallito.columns else ['titulo', 'ubicacion']
    df_gallito_unique = df_gallito.drop_duplicates(subset=dedup_subset_gallito, keep='first').reset_index(drop=True)
        
    print(f"Listings de ML únicos a procesar: {len(df_ml_unique)} (Original: {len(df_ml)})")
    print(f"Listings de Gallito únicos a procesar: {len(df_gallito_unique)} (Original: {len(df_gallito)})")


    # --- 2. Normalización ---
    df_ml_unique['titulo_norm'] = df_ml_unique['titulo'].apply(normalize_text)
    df_gallito_unique['titulo_norm'] = df_gallito_unique['titulo'].apply(normalize_text)
    
    coincidences = []
    
    print(f"Comparando {len(df_ml_unique)} listings de ML con {len(df_gallito_unique)} de Gallito (Umbral: {SIMILARITY_THRESHOLD})...")
    start_time = time.time()
    
    # Iterar sobre cada anuncio ÚNICO de Mercado Libre
    for index_ml, row_ml in df_ml_unique.iterrows():
        
        best_score = 0
        best_match_gallito = None
        
        # 3. Comparar con todos los anuncios ÚNICOS de Gallito y encontrar el MEJOR
        for index_gallito, row_gallito in df_gallito_unique.iterrows():
            
            # Utilizamos fuzz.token_sort_ratio (más robusto a la inversión de palabras)
            score = fuzz.token_sort_ratio(row_ml['titulo_norm'], row_gallito['titulo_norm'])
            
            if score > best_score:
                best_score = score
                best_match_gallito = row_gallito

        # --- 4. Registro del Mejor Match ---
        if best_score >= SIMILARITY_THRESHOLD:
            # Si el mejor score supera el umbral, registra solo ESA coincidencia
            coincidences.append({
                'score_similaridad': best_score,
                
                'titulo_ml': row_ml['titulo'],
                'ubicacion_ml': row_ml['ubicacion'],
                # La URL de ML sigue siendo N/A si el scraper no la capturó
                'url_ml': row_ml.get('url', 'N/A'), 
                'precio_ml': f"{row_ml['precio_moneda']} {row_ml['precio_valor']}",

                'titulo_gallito': best_match_gallito['titulo'],
                'ubicacion_gallito': best_match_gallito['ubicacion'],
                'url_gallito': best_match_gallito['url'],
                'precio_gallito': f"{best_match_gallito['precio_moneda']} {best_match_gallito['precio_valor']}",
            })

    end_time = time.time()
    print(f"Comparación completada en {end_time - start_time:.2f} segundos.")
    
    return pd.DataFrame(coincidences)


# --- EJECUCIÓN PRINCIPAL ---
if __name__ == "__main__":
    
    try:
        # 1. Cargar Datos
        df_ml = pd.read_csv(ML_FILE)
        df_gallito = pd.read_csv(GALLITO_FILE)
        
        # 2. Detección de Coincidencias
        df_coincidences = detect_duplicates(df_ml, df_gallito)
        
        # 3. Guardar Resultados
        if not df_coincidences.empty:
            # Ordenar por el score de similaridad descendente
            df_coincidences = df_coincidences.sort_values(by='score_similaridad', ascending=False)
            
            df_coincidences.to_csv(OUTPUT_FILE, index=False, encoding='utf-8')
            
            print("\n--- RESULTADOS ---")
            print(f"Se encontraron {len(df_coincidences)} posibles coincidencias ÚNICAS.")
            print(f"Coincidencias guardadas en {OUTPUT_FILE}")
            
            print("\n--- Muestra de las 5 mejores coincidencias ---")
            print(df_coincidences[['score_similaridad', 'titulo_ml', 'titulo_gallito', 'precio_ml', 'precio_gallito']].head())
            
        else:
            print(f"\nNo se encontraron coincidencias por encima del umbral de similaridad ({SIMILARITY_THRESHOLD}).")
            
    except FileNotFoundError as e:
        print(f"ERROR: No se encontró uno de los archivos CSV requeridos. Asegúrate de que '{ML_FILE}' y '{GALLITO_FILE}' existan.")
    except Exception as e:
        print(f"Ocurrió un error inesperado durante el procesamiento: {e}")