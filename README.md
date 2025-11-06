# UniDatos 

Proyecto desarrollado para la materia **Integración de Datos**  
**Facultad de Ingeniería, Universidad de la República (FIng - Udelar)**  
**Integrantes:**  
- Josefina Cardozo — 5.224.009-2  
- Mayte Carro — 5.396.847-1  
- Carolina Martínez — 5.245.351-8  

---

## Descripción

**UniDatos** es una aplicación desarrollada en **Flutter** y **FastAPI** que integra información de distintas fuentes inmobiliarias y datasets públicos para facilitar la búsqueda, comparación y recomendación de viviendas en Montevideo.  
Forma parte de un proyecto ETL que aborda la **integración de datos heterogéneos** (HTML, JSON, CSV) provenientes de portales como **Mercado Libre**, **Gallito Luis**, además de fuentes abiertas de la Intendencia de Montevideo (proximidad a servicios, seguridad, transporte, etc.).

---

## Objetivo

Centralizar y estandarizar la información de alquiler y venta de propiedades, resolviendo heterogeneidades **sintácticas**, **estructurales**, **temporales** y **espaciales** para obtener: 
- Visualización de precios, seguridad y servicios cercanos.  
- Información centralizada sobre las propiedades disponibles.
- Búsqueda y filtrado de las propiedades según preferencias de usuario.

---

##  Tecnologías

- **Frontend:** Flutter  
- **Backend:** FastAPI  
- **Lenguajes:** Dart, Python 
- **Procesos ETL:** Python / Pandas / GeoPandas  
- **Fuentes de datos:**  
  - Portales inmobiliarios (HTML / JSON)  
  - Datasets públicos (INE, GeoServer Montevideo, Observatorio de Seguridad)  

---

##  Ejecución

Clonar el repositorio:
```bash
git clone https://github.com/<usuario>/monteroom.git
cd monteroom
```

Ejecutar el backend exponiendolo al puerto 8001
```bash
python -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8001
```
Ejecutar el backend en el navegador
```bash
flutter run -d chrome 
```