import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time

# METADATA del script
METADATA = {
    "name": "mercadolibre_scraper",
    "description": "Scraper de alquileres desde MercadoLibre Uruguay. Extrae título, ubicación, precio, dorms, baños, superficie, imagen y URL.",
    "author": "iDatos team",
    "date_created": "2025-11-04",
    "version": "1.0",
}

# --- CONFIGURACIÓN ---

# URL base de alquileres en Mercado Libre Uruguay
URL_BASE = "https://listado.mercadolibre.com.uy/inmuebles/alquiler"
ITEMS_PER_PAGE = 48  # ML muestra 48 resultados por página
MAX_PAGES_TO_SCRAPE = 5  # Definimos un máximo de 5 páginas a scrapear

# Simular un navegador (User-Agent)
headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )
}


# --- FUNCIÓN DE EXTRACCIÓN DE DATOS POR PÁGINA ---

def obtener_caracteristica_ml(anuncio_html, texto_clave):
    """
    Busca una característica específica (Dorms, Baños, m²) en la tarjeta de la propiedad.
    """
    # Selector principal para los atributos
    tags_tipologia = anuncio_html.find("ul", class_="poly-attributes_list")

    if not tags_tipologia:
        return "N/A"

    # Iterar sobre los ítems de la lista (li)
    for tag in tags_tipologia.find_all("li", class_="poly-attributes_list__item"):
        texto = tag.text.strip().lower()  # Convertimos a minúsculas

        # Verificamos si la clave está en el texto (ej: 'dormitorio' en '1 dormitorio')
        if texto_clave in texto:
            # Buscamos el primer número en el texto
            match = re.search(r"(\d+)", texto)
            if match:
                return match.group(1)

    return "N/A"


def raspar_pagina_ml(url):
    """Extrae datos clave de UNA página de resultados de Mercado Libre."""
    datos_propiedades = []

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "html.parser")

        # Selector Principal: Contenedor de cada anuncio.
        anuncios = soup.find_all("li", class_="ui-search-layout__item")

        if not anuncios:
            return pd.DataFrame()

        # Extraer la información
        for anuncio in anuncios:

            content_wrapper = anuncio.find("div", class_="poly-card__content")

            # --- EXTRACCIÓN DE TÍTULO Y URL ---
            titulo_tag = content_wrapper.find("a", class_="poly-component__title") if content_wrapper else None

            titulo = titulo_tag.text.strip() if titulo_tag else "N/A"

            url_ml = "N/A"
            if titulo_tag and titulo_tag.get("href"):
                # Tomamos el href y eliminamos el fragmento de seguimiento ('#...')
                url_ml = titulo_tag.get("href").split("#")[0]

            # --- EXTRACCIÓN DE UBICACIÓN Y PRECIO ---
            ubicacion_tag = content_wrapper.find("span", class_="poly-component__location") if content_wrapper else None
            ubicacion = ubicacion_tag.text.strip() if ubicacion_tag else "N/A"

            price_container = content_wrapper.find("div", class_="poly-component__price") if content_wrapper else None
            price_value, currency = "N/A", "N/A"

            if price_container:
                fraction_tag = price_container.find("span", class_="andes-money-amount__fraction")
                price_value = fraction_tag.text.strip() if fraction_tag else ""
                symbol_tag = price_container.find("span", class_="andes-money-amount__currency-symbol")
                currency_symbol = symbol_tag.text.strip() if symbol_tag else ""

                price_value = re.sub(r"[^\d]", "", price_value)
                currency = currency_symbol if currency_symbol else "N/A"

            # --- EXTRACCIÓN DE IMAGEN Y CARACTERÍSTICAS ---
            image_wrapper = anuncio.find("div", class_="poly-card__portada")
            image_tag = image_wrapper.find("img") if image_wrapper else None

            if not image_tag:
                image_tag = anuncio.find("img", class_="ui-search-result-image__element")

            imagen_url = "N/A"
            if image_tag:
                src_url = image_tag.get("src")
                data_src_url = image_tag.get("data-src")

                if src_url and not src_url.startswith("data:image/"):
                    imagen_url = src_url
                elif data_src_url:
                    imagen_url = data_src_url

            dorms = obtener_caracteristica_ml(anuncio, "dormit")
            banos = obtener_caracteristica_ml(anuncio, "baño")
            metros_cuadrados = obtener_caracteristica_ml(anuncio, "m²")

            datos_propiedades.append(
                {
                    "titulo": titulo,
                    "ubicacion": ubicacion,
                    "precio_valor": price_value,
                    "precio_moneda": currency,
                    "dorms": dorms,
                    "banos": banos,
                    # Compatibilidad con pipelines que usan la clave con tilde
                    "baños": banos,
                    "superficie_m2": metros_cuadrados,
                    "imagen_url": imagen_url,
                    "fuente": "MercadoLibre",
                    # NUEVO CAMPO AGREGADO
                    "url": url_ml,
                }
            )

        return pd.DataFrame(datos_propiedades)

    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Error de conexión al portal en {url}: {e}")
        return pd.DataFrame()
    except Exception as e:
        print(f"[ERROR] Ocurrió un error inesperado al raspar la página: {e}")
        return pd.DataFrame()


def raspar_mercadolibre_multipagina(max_pages):
    """Orquesta el raspado de múltiples páginas de Mercado Libre."""
    all_results = []

    for page in range(1, max_pages + 1):
        # Fórmula de paginación de ML: _Desde_X
        start_index = (page - 1) * ITEMS_PER_PAGE + 1

        if page == 1:
            url = URL_BASE
        else:
            # Construcción de la URL: /inmuebles/alquiler/_Desde_49_NoIndex_True, etc.
            url = f"{URL_BASE}/_Desde_{start_index}_NoIndex_True"

        print(f"Scraping página {page} (Índice de inicio: {start_index})...")

        df_page = raspar_pagina_ml(url)

        if df_page.empty:
            print(f"No se encontraron anuncios o error en la página {page}. Terminando la extracción.")
            break

        all_results.append(df_page)

        # Pausa de 3 segundos para evitar ser bloqueado
        time.sleep(3)

    if not all_results:
        return pd.DataFrame()

    return pd.concat(all_results, ignore_index=True)


# --- FUNCIÓN DE IMPUTACIÓN (POST-SCRAPING) ---

def imputar_dormitorios_por_titulo(df):
    """
    Rellena los valores 'N/A' de la columna 'dorms' buscando patrones en el título.
    """

    def extraer_dormitorio_de_texto(titulo, dorms_actual):
        if pd.isna(dorms_actual) or str(dorms_actual).upper() == "N/A":

            titulo_lower = titulo.lower()

            numero_map = {
                "un": "1",
                "uno": "1",
                "una": "1",
                "dos": "2",
                "tres": "3",
                "cuatro": "4",
            }

            if "monoambiente" in titulo_lower or "studio" in titulo_lower or "loft" in titulo_lower:
                return "1"

            match_digit = re.search(r"(\d+)\s*(dorm|hab|amb)", titulo_lower)
            if match_digit:
                return match_digit.group(1)

            match_numero_letra = re.search(r"(un|uno|dos|tres|cuatro)\s+dormitorios?", titulo_lower)
            if match_numero_letra:
                return numero_map.get(match_numero_letra.group(1), dorms_actual)

        return dorms_actual

    df["dorms"] = df.apply(lambda row: extraer_dormitorio_de_texto(row["titulo"], row["dorms"]), axis=1)
    return df


# --- EJECUCIÓN Y GUARDADO DE DATOS ---
if __name__ == "__main__":

    # 1. Extracción (E) - Multi-página
    df_resultados = raspar_mercadolibre_multipagina(MAX_PAGES_TO_SCRAPE)

    if not df_resultados.empty:

        # 2. Transformación (T): Imputación de Dormitorios desde el Título
        print("\n--- Ejecutando imputación de dormitorios desde el título para valores 'N/A'... ---")
        df_resultados = imputar_dormitorios_por_titulo(df_resultados)

        print(f"\n[ÉXITO] Total de anuncios de Mercado Libre obtenidos: {len(df_resultados)}")
        print("\n--- Vista Final de los Datos Raspados (incluyendo URL) ---")
        # Mostrar la nueva columna 'url'
        print(df_resultados[["titulo", "ubicacion", "precio_valor", "url"]].head())

        # 3. Carga (L): Guardar archivos
        output_csv = "mercadolibre_alquileres_con_imagen.csv"
        df_resultados.to_csv(output_csv, index=False, encoding="utf-8")
        print(f"\n[OK] Datos guardados en {output_csv}")

    print("\n--- Fin del Proceso de Extracción ---")