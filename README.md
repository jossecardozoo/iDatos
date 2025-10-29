# Monteroom 🏙️

Proyecto desarrollado para la materia **Integración de Datos**  
**Facultad de Ingeniería, Universidad de la República (FIng - Udelar)**  
**Integrantes:**  
- Josefina Cardozo — 5.224.009-2  
- Mayte Carro — 5.396.847-1  
- Carolina Martínez — 5.245.351-8  

---

## 📘 Descripción

**Monteroom** es una aplicación desarrollada en **Flutter** que integra información de distintas fuentes inmobiliarias y datasets públicos para facilitar la búsqueda, comparación y recomendación de viviendas en Montevideo.  
Forma parte de un proyecto ETL que aborda la **integración de datos heterogéneos** (HTML, JSON, CSV, GPKG) provenientes de portales como **Mercado Libre**, **Gallito Luis** e **InfoCasas**, además de fuentes abiertas de la Intendencia de Montevideo (proximidad a servicios, seguridad, transporte, etc.).

---

## 🎯 Objetivo

Centralizar y estandarizar la información de alquiler y venta de propiedades, resolviendo heterogeneidades **sintácticas**, **estructurales**, **temporales** y **espaciales** para brindar:
- Comparación entre anuncios duplicados.  
- Visualización de precios, seguridad y servicios cercanos.  
- Recomendaciones personalizadas según preferencias del usuario.

---

## 🧩 Tecnologías

- **Frontend:** Flutter  
- **Lenguaje:** Dart  
- **Procesos ETL:** Python / Pandas / GeoPandas  
- **Fuentes de datos:**  
  - Portales inmobiliarios (HTML / JSON)  
  - Datasets públicos (INE, GeoServer Montevideo, Observatorio de Seguridad)  

---

## 🚀 Ejecución

Clonar el repositorio:
```bash
git clone https://github.com/<usuario>/monteroom.git
cd monteroom
