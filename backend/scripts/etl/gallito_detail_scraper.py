#!/usr/bin/env python
"""
gallito_detail_scraper.py

Scraper de detalles de Gallito que visita cada URL individual para extraer
la dirección completa y otros datos detallados del inmueble.

Lee: gallito_alquileres_crudos.csv
Genera: gallito_alquileres_crudos.with_addr.csv

Uso:
    python -m scripts.etl.gallito_detail_scraper --input gallito_alquileres_crudos.csv --output gallito_alquileres_crudos.with_addr.csv [--limit N]
"""
import argparse
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
from pathlib import Path
import sys


def get_inmueble_data(html_content: str) -> dict:
    """
    Extrae la dirección, cantidad de dormitorios y precio del inmueble
    usando el contenido HTML proporcionado.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    data = {
        'direccion': None,
        'dormitorios': None,
        'precio_detalle': None
    }

    # 1. Extraer Dirección (h2.direccion)
    address_element = soup.select_one('h2.direccion')
    if address_element:
        data['direccion'] = address_element.get_text(strip=True)

    # 2. Extraer Precio detallado (Busca el strong dentro de contenedor-info)
    price_element = soup.select_one('.contenedor-info strong')
    if price_element:
        data['precio_detalle'] = price_element.get_text(strip=True)
    
    # 3. Extraer Dormitorios
    dormitorios_element = soup.select_one('.mas-info a span')
    
    if dormitorios_element:
        dormitorios_text = dormitorios_element.get_text(strip=True)
        
        # Usamos regex para encontrar el primer número en el texto
        match = re.search(r'(\d+)', dormitorios_text)
        
        if match:
            data['dormitorios'] = int(match.group(1))
        # Manejar caso de "Monoambiente" o "Studio"
        elif 'monoambiente' in dormitorios_text.lower() or 'studio' in dormitorios_text.lower() or 'mono' in dormitorios_text.lower():
            data['dormitorios'] = 0
        
    return data


def scrape_gallito_details(input_csv: str, output_csv: str, limit: int = None, delay: float = 2.0):
    """
    Lee el CSV de entrada, visita cada URL y extrae detalles adicionales.
    
    Args:
        input_csv: Ruta al CSV con las URLs
        output_csv: Ruta donde guardar el CSV con direcciones completas
        limit: Límite opcional de registros a procesar (None = todos)
        delay: Tiempo de espera entre requests (segundos)
    """
    # Leer CSV de entrada
    print(f"Leyendo archivo: {input_csv}")
    df = pd.read_csv(input_csv)
    
    if 'url' not in df.columns:
        raise ValueError("El CSV debe tener una columna 'url'")
    
    total_rows = len(df)
    if limit:
        df = df.head(limit)
        print(f"Procesando {len(df)} de {total_rows} registros (límite: {limit})")
    else:
        print(f"Procesando {len(df)} registros")
    
    # Headers para simular navegador
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    # Listas para almacenar resultados
    direcciones = []
    dormitorios_list = []
    precios_detalle = []
    errores = []
    
    # Procesar cada URL
    for idx, row in df.iterrows():
        url = row['url']
        print(f"[{idx + 1}/{len(df)}] Procesando: {url}")
        
        try:
            # Hacer request a la URL
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            # Extraer datos del HTML
            inmueble_data = get_inmueble_data(response.text)
            
            direcciones.append(inmueble_data.get('direccion'))
            dormitorios_list.append(inmueble_data.get('dormitorios'))
            precios_detalle.append(inmueble_data.get('precio_detalle'))
            errores.append(None)
            
            # Esperar entre requests para no sobrecargar el servidor
            if idx < len(df) - 1:  # No esperar después del último
                time.sleep(delay)
                
        except requests.exceptions.RequestException as e:
            print(f"  ⚠ Error HTTP: {e}")
            direcciones.append(None)
            dormitorios_list.append(None)
            precios_detalle.append(None)
            errores.append(str(e))
        except Exception as e:
            print(f"  ⚠ Error procesando: {e}")
            direcciones.append(None)
            dormitorios_list.append(None)
            precios_detalle.append(None)
            errores.append(str(e))
    
    # Agregar columnas nuevas al DataFrame
    df['direccion_completa'] = direcciones
    df['dormitorios_detalle'] = dormitorios_list
    df['precio_detalle'] = precios_detalle
    if any(errores):
        df['error_scraping'] = errores
    
    # Guardar CSV de salida
    output_path = Path(output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, encoding='utf-8')
    
    # Estadísticas
    exitosos = sum(1 for d in direcciones if d is not None)
    print(f"\n{'='*60}")
    print(f"Proceso completado:")
    print(f"  Total procesados: {len(df)}")
    print(f"  Direcciones extraídas: {exitosos}")
    print(f"  Errores: {len(df) - exitosos}")
    print(f"  Archivo guardado: {output_path}")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(
        description='Scraper de detalles de Gallito que extrae direcciones completas de URLs individuales',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        '--input',
        type=str,
        required=True,
        help='Archivo CSV de entrada con URLs (gallito_alquileres_crudos.csv)'
    )
    parser.add_argument(
        '--output',
        type=str,
        required=True,
        help='Archivo CSV de salida con direcciones completas (.with_addr.csv)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Límite de registros a procesar (útil para pruebas)'
    )
    parser.add_argument(
        '--delay',
        type=float,
        default=2.0,
        help='Tiempo de espera entre requests en segundos (default: 2.0)'
    )
    
    args = parser.parse_args()
    
    # Verificar que el archivo de entrada existe
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: El archivo de entrada no existe: {args.input}")
        sys.exit(1)
    
    print("="*60)
    print("SCRAPER DE DETALLES DE GALLITO")
    print("="*60)
    print(f"Input:  {args.input}")
    print(f"Output: {args.output}")
    if args.limit:
        print(f"Límite: {args.limit} registros")
    print(f"Delay:  {args.delay} segundos entre requests")
    print("="*60)
    print()
    
    try:
        scrape_gallito_details(
            input_csv=args.input,
            output_csv=args.output,
            limit=args.limit,
            delay=args.delay
        )
    except KeyboardInterrupt:
        print("\n\n⚠ Proceso interrumpido por el usuario")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

