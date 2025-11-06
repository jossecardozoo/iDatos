import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time

# METADATA del script
METADATA = {
    "name": "infocasas_alquiler_Gallito",
    "description": "Scraper/parseador para InfoCasas y Gallito (anuncios de alquiler). Extrae título, ubicación, precio, imagen y URL.",
    "author": "iDatos team",
    "date_created": "2025-11-04",
    "version": "1.0",
}

def extract_listing_data(listing_soup):
    """Extrae los datos de un único elemento BeautifulSoup de un anuncio."""
    data = {}
    
    # 1. URL y Título
    # Buscamos el enlace principal que contiene el título (<h2>)
    link_tag = listing_soup.select_one('.content-area .mas-info a')
    if not link_tag:
        return None # Descartamos si no hay enlace principal

    data['url'] = link_tag.get('href')
    # Limpiamos los saltos de línea y espacios extra
    data['titulo'] = link_tag.select_one('h2').text.strip() if link_tag.select_one('h2') else 'N/A'
    
    # 2. Ubicación/Barrio
    # Está en el párrafo dentro del contenedor de información
    location_tag = listing_soup.select_one('.contenedor-info p')
    data['ubicacion'] = location_tag.text.strip() if location_tag else 'N/A'

    # 3. Precio (Moneda y Valor)
    price_tag = listing_soup.select_one('.contenedor-info strong')
    data['precio_moneda'] = 'N/A'
    data['precio_valor'] = 'N/A'

    if price_tag:
        full_price_text = price_tag.text.strip()
        
        # Intentamos separar la moneda del valor usando una expresión regular
        match = re.search(r'([^\d\s\.\,]+)\s*([\d\.\,]+)', full_price_text)
        
        if match:
            # Moneda: $U, U$S, USD, etc. (Limpiamos el carácter unicode \u2022 si existe)
            data['precio_moneda'] = match.group(1).replace('\u2022', '').strip() 
            # Valor: Quitamos puntos o comas de miles para tener un número limpio
            valor_limpio = match.group(2).replace('.', '').replace(',', '').strip() 
            data['precio_valor'] = re.sub(r'[^0-9]', '', valor_limpio)
        else:
            # Caso de solo valor, asumimos que la moneda está implícita o no está clara
            data['precio_valor'] = re.sub(r'[^0-9]', '', full_price_text).strip()
    
    # 4. Imagen URL
    # Buscamos la imagen de la vista previa 
    img_tag = listing_soup.select_one('.img-seva') 

    data['imagen_url'] = img_tag.get('src') if img_tag and img_tag.get('src') else 'N/A'
    
    # 5. Fuente
    data['fuente'] = 'Gallito'

    return data

def scrape_gallito_alquileres(max_pages=3):
    """
    Realiza el scraping de los alquileres en Gallito.com.uy.
    """
    base_url = 'https://www.gallito.com.uy/inmuebles/alquiler/montevideo'
    all_listings = []
    
    # Simulación de un navegador (User-Agent) para evitar bloqueo
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    print("Iniciando scraping en Gallito.com.uy...")
    
    for page in range(1, max_pages + 1):
        # La paginación usa el parámetro ?p=
        url = f"{base_url}?p={page}" if page > 1 else base_url
        print(f"Scraping página {page}: {url}")

        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status() # Lanza un error para códigos de estado 4xx/5xx
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Selector basado en el contenedor de cada anuncio (<article> dentro de un div de columna)
            listing_containers = soup.select('.col-xs-12.col-sm-4.col-md-4.col-lg-3 article')
            
            if not listing_containers:
                print(f"No se encontraron más listings en la página {page}. Terminando.")
                break
                
            for container in listing_containers:
                listing_data = extract_listing_data(container)
                if listing_data:
                    all_listings.append(listing_data)
                    
            print(f"Página {page} scrapeada. Total de anuncios hasta ahora: {len(all_listings)}")

            time.sleep(2) 

        except requests.exceptions.RequestException as e:
            print(f"Error al solicitar la página {page}: {e}")
            break

    return all_listings

# --- EJECUCIÓN DEL SCRAPER ---
if __name__ == "__main__":
    
    # Cambia este valor para scrapear más o menos páginas.
    NUM_PAGES_TO_SCRAPE = 16
    
    data = scrape_gallito_alquileres(max_pages=NUM_PAGES_TO_SCRAPE)

    if data:
        df = pd.DataFrame(data)
        output_filename = 'gallito_alquileres_crudos.csv'
        
        # Guardar en CSV
        df.to_csv(output_filename, index=False, encoding='utf-8')
        
        print("\n--- PROCESO DE SCRAPING FINALIZADO ---")
        print(f"Datos de Gallito guardados en {output_filename}")
        print(f"Total de anuncios obtenidos: {len(df)}")
        
        print("\n--- Muestra de los primeros 5 anuncios:")
        print(df.head())
    else:
        print("\nNo se pudo obtener ningún dato.")