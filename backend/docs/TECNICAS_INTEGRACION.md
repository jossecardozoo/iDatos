# Técnicas de Integración de Datos

Este documento describe las técnicas y metodologías utilizadas en el pipeline de integración de datos inmobiliarios.

## Principios FAIR

El proyecto sigue los principios FAIR (Findable, Accessible, Interoperable, Reusable) para garantizar la calidad y reutilización de los datos:

### Findable (Localizables)
- Cada dataset tiene metadatos descriptivos (fuente, fecha, formato, nivel de procesamiento)
- Identificadores únicos para cada registro
- Metadata almacenada en archivos JSON estructurados

### Accessible (Accesibles)
- Datos almacenados en capas diferenciadas (crudo, procesado, analítico)
- Políticas de acceso claras
- Fuentes originales preservadas en Data Lake

### Interoperable (Interoperables)
- Formatos estándar (CSV, JSON, SQLite)
- Normalización de nombres de atributos y unidades
- Schemas canónicos para intercambio

### Reusable (Reutilizables)
- Metadatos completos sobre origen y transformaciones
- Versionado de pipelines
- Documentación de procesos

## Data Provenance (Trazabilidad)

### Implementación

El sistema implementa trazabilidad completa mediante el módulo `provenance.py`:

1. **Tracking de Runs**: Cada ejecución del pipeline genera un run_id único
2. **Logging de Tasks**: Todas las tareas registran entrada, salida y tiempo de ejecución
3. **Tracking de Transformaciones**: Cada transformación registra:
   - Operación realizada
   - Filas antes/después
   - Columnas agregadas/eliminadas
   - Filtros aplicados
4. **Metadata Persistente**: Toda la información se guarda en JSON para auditoría

### Estructura de Metadata

```json
{
  "run_id": "etl_flow_prefect_abc123",
  "flow_name": "etl_flow_prefect",
  "started_at": "2025-01-15T10:00:00Z",
  "tasks": [
    {
      "task_name": "load_csv",
      "input_data": {...},
      "output_data": {...},
      "execution_time_seconds": 2.5
    }
  ],
  "transformations": [...],
  "duplicate_detections": [...],
  "statistics": {...}
}
```

## Técnicas de Extracción

### Web Scraping

**Portales procesados**:
- MercadoLibre: Scraping de listados de alquiler
- Gallito Luis: Extracción de detalles de propiedades
- InfoCasas: (Pendiente de implementación)

**Herramientas**:
- BeautifulSoup para parsing HTML
- Expresiones regulares para limpieza
- Rate limiting para respetar términos de uso

### APIs Públicas

- **Geocodificación**: Nominatim (OpenStreetMap)
- **Geocodificación alternativa**: geocode.xyz API
- **Datos contextuales**: Intendencia de Montevideo (GPKG)

## Técnicas de Transformación

### 1. Limpieza de Datos

**Normalización sintáctica**:
- Eliminación de caracteres especiales
- Unificación de encoding (UTF-8)
- Normalización de espacios y puntuación

**Validación**:
- Tipado correcto de columnas (números, fechas, cadenas)
- Eliminación de registros inconsistentes
- Manejo de valores nulos

### 2. Normalización Semántica

**Unificación de monedas**:
- Conversión a UYU (peso uruguayo) usando tasas oficiales
- Detección automática de moneda desde texto
- Manejo de símbolos ($, U$S, etc.)

**Normalización de ubicaciones**:
- Limpieza de prefijos comunes ("Casas en", "Apartamentos en")
- Eliminación de referencias redundantes ("Montevideo")
- Estandarización de formatos de dirección

### 3. Geocodificación

**Proceso**:
1. Limpieza de dirección (eliminar piso/apartamento, normalizar intersecciones)
2. Agregación de contexto ("Montevideo, Uruguay")
3. Consulta a Nominatim con rate limiting (1 req/seg)
4. Cache en SQLite para evitar consultas repetidas
5. Fallback a geocode.xyz para direcciones no resueltas

**Optimizaciones**:
- Cache persistente de coordenadas
- Batch processing con delays
- Reintentos automáticos para fallos

### 4. Enriquecimiento Contextual

**Datos agregados**:
- Distancia a parada de ómnibus más cercana
- Distancia a bicicircuito más cercano
- Zona censal
- Barrio oficial

**Método**:
- Join espacial con capas GeoPackage de la Intendencia
- Cálculo de distancias usando geometrías

### 5. Imputación de Datos

**Dormitorios**:
- Extracción desde título usando expresiones regulares
- Patrones: "3 dorm", "dos habitaciones", "monoambiente"
- Mapeo de palabras a números

**Barrios**:
- Matching exacto con diccionario de aliases
- Fuzzy matching con rapidfuzz (umbral 78-85%)
- Validación cruzada con ubicación

**Nivel de criminalidad**:
- Clasificación basada en datos de denuncias
- Umbrales: baja (≤70), media (≤140), alta (>140)
- Por barrio según estadísticas oficiales


## Detección de Duplicados

El pipeline detecta y procesa **únicamente duplicados cross-portal** (entre diferentes portales inmobiliarios):

- **Criterio**: Coordenadas exactamente iguales (latitud y longitud idénticas)
- **Movimiento a tabla separada**: Los duplicados cross-portal se mueven a `duplicates_moved`



### Algoritmo

```python
Para cada portal:
  1. Deduplicación exacta por campos clave
  2. Normalización de títulos
  3. Para cada registro:
     - Calcular similaridad con todos los demás
     - Si similaridad >= umbral Y ubicación similar:
       - Marcar como duplicado
       - Conservar el primero
  4. Registrar duplicados detectados
```

## Calidad de Datos

### Atributos de Calidad Implementados

| Atributo | Estrategia |
|----------|-----------|
| **Exactitud** | Validación cruzada entre fuentes, normalización de direcciones y precios |
| **Consistencia** | Homogeneización de nombres de barrios, monedas y formatos |
| **Trazabilidad** | Registro de transformaciones y metadatos detallados |
| **Fiabilidad** | Selección de fuentes oficiales y documentación de procesos |
| **Completitud** | Imputación de campos faltantes (dormitorios, barrios) |

### Validaciones Aplicadas

- Filtrar solo propiedades en Montevideo
- Validar coordenadas geográficas (lat/lon válidos)

## Arquitectura de Almacenamiento

### Data Lake (Capa Raw)
- **Formato**: SQLite, tabla `raw_listings`
- **Contenido**: Datos crudos sin transformar
- **Metadata**: Fuente, fecha de carga, encoding

### Data Warehouse (Capa Transformed)
- **Formato**: SQLite, tabla `transformed_listings`
- **Contenido**: Datos limpios, normalizados y enriquecidos
- **Características**: 
  - Precios en UYU
  - Coordenadas geográficas
  - Barrios normalizados
  - Datos contextuales agregados

### Organización de Archivos

```
data/
├── raw/              # Datos crudos de scraping
├── processed/        # Datos transformados
├── intermediate/     # Archivos intermedios
├── archive/          # Archivos antiguos
└── provenance/       # Metadata de trazabilidad
```

## Orquestación con Prefect

### Ventajas

1. **Retries automáticos**: Reintentos ante fallos transitorios
2. **Logging estructurado**: Logs con contexto completo
3. **Paralelización**: Tasks independientes pueden ejecutarse en paralelo
4. **Monitoreo**: UI de Prefect para visualizar ejecuciones
5. **Trazabilidad**: Cada task registra entrada/salida automáticamente

### Configuración

- **Retries**: 2-3 intentos por defecto
- **Timeouts**: 1 hora para tasks largos
- **Tags**: Categorización de tasks (extract, transform, load, etc.)


## Referencias

- [Principios FAIR](https://www.go-fair.org/fair-principles/)
- [Data Provenance Best Practices](https://www.w3.org/TR/prov-overview/)
- [Prefect Documentation](https://docs.prefect.io/)
- [OpenStreetMap Nominatim](https://nominatim.org/)

