# Metadatos de Datasets

Este directorio contiene metadatos estructurados sobre los datasets utilizados en el proyecto de integración de datos inmobiliarios.

## Archivos de Metadatos

### Datos Contextuales de Montevideo

#### `proximidadbicircuito_metadata.json`
- **Dataset**: Proximidad a bicicircuitos
- **Formato**: GPKG
- **Fuente**: Intendencia de Montevideo (CKAN)
- **Actualización**: 23 de enero de 2024
- **Descripción**: Distancia entre cada Zona Censal y el bicicircuito más cercano según recorridos del viario urbano (peatonal)
- **Campos principales**:
  - `CODCOMP_A`: Código de zona censal
  - `DISTANCIABICICIRCUITO_MEAN`: Distancia promedio al bicicircuito más cercano (metros)
  - Campos de población con acceso a bicicircuitos a menos de 300m

#### `proximidadparadas_metadata.json`
- **Dataset**: Proximidad a paradas de autobús
- **Formato**: GPKG
- **Fuente**: Intendencia de Montevideo (CKAN)
- **Actualización**: 23 de enero de 2024
- **Descripción**: Distancia de cada zona censal (manzana) a la parada de autobús más cercana según recorridos del viario urbano (peatonal)
- **Campos principales**:
  - `CODCOMP_A`: Código de zona censal
  - `DISTANCIAPARADA_MEAN`: Distancia promedio a la parada más cercana (metros)
  - Campos de población con acceso a paradas a menos de 300m

### Datos de Seguridad

#### `denuncias_hurtos_por_10000_hab_montevideo.json`
- **Dataset**: Denuncias de hurtos por barrio
- **Formato**: JSON
- **Fuente**: Datos públicos de seguridad
- **Descripción**: Estadísticas de denuncias de hurtos normalizadas por población (por 10,000 habitantes) por barrio de Montevideo
- **Uso**: Clasificación de nivel de criminalidad (baja/media/alta) y matching de barrios

## Estructura de Metadatos

Cada archivo de metadatos JSON sigue la siguiente estructura:

```json
{
  "dataset_name": "Nombre del dataset",
  "dataset_id": "identificador_unico",
  "description": "Descripción detallada",
  "source": {
    "name": "Organización",
    "url": "URL de descarga",
    "organization": "Institución"
  },
  "format": "Formato del archivo",
  "license": "Licencia",
  "dates": {
    "created": "Fecha de creación",
    "last_data_update": "Última actualización de datos",
    "last_metadata_update": "Última actualización de metadatos"
  },
  "fields": [
    {
      "name": "nombre_campo",
      "type": "tipo",
      "description": "Descripción del campo"
    }
  ],
  "spatial_coverage": {
    "area": "Área geográfica",
    "granularity": "Nivel de granularidad",
    "coordinate_system": "Sistema de coordenadas"
  },
  "usage_in_project": {
    "purpose": "Propósito en el proyecto",
    "integration_method": "Método de integración",
    "field_mapped": "Campo mapeado en el proyecto",
    "source_field": "Campo origen"
  },
  "data_quality": {
    "completeness": "Nivel de completitud",
    "accuracy": "Precisión",
    "update_frequency": "Frecuencia de actualización"
  }
}
```

## Integración en el Pipeline

Estos datasets se integran en el pipeline ETL mediante:

1. **Join espacial**: Unión de coordenadas de propiedades con zonas censales
2. **Enriquecimiento contextual**: Agregación de distancias a servicios
3. **Normalización**: Mapeo de códigos de zona censal a propiedades

### Archivos GPKG Utilizados

- `proximidadbicircuito.gpkg`: Contiene datos de proximidad a bicicircuitos
- `proximidadparadas.gpkg`: Contiene datos de proximidad a paradas de autobús

### Scripts de Integración

Los datos contextuales se integran mediante:
- `scripts/datos_contextuales.py`: Función `enrich_with_contextual_data()`
- Join espacial usando coordenadas geográficas
- Mapeo por zona censal (CODCOMP_A)

## Referencias

- [Portal de Datos Abiertos de Montevideo](https://ckan-data.montevideo.gub.uy/)
- [Dataset de Proximidad para la Vida Cotidiana](https://ckan-data.montevideo.gub.uy/dataset/8a5a5726-21bb-423e-9726-8b80b17872f5)

## Notas

- Los datasets GPKG requieren la librería `geopandas` para su procesamiento
