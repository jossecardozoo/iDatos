# Scripts para Detección de Duplicados

Este documento describe los scripts disponibles para ejecutar el pipeline ETL completo o solo la detección de duplicados con diferentes métodos.

## Scripts Disponibles

### 1. Pipeline Completo

#### `run_etl.py` - Pipeline con Coordenadas (Método Original)

Ejecuta el pipeline ETL completo usando detección de duplicados por coordenadas exactas.

```bash
# Uso básico
python scripts/run_etl.py

# Con base de datos personalizada
python scripts/run_etl.py --db-path data/custom_database.db
```

**Características**:
- Método: Coordenadas exactas
- Velocidad: Muy rápida (~0.1s para 200 registros)
- Precisión: Solo detecta coordenadas idénticas

---

#### `run_etl_with_dbscan.py` - Pipeline con DBSCAN (Recomendado) ⚡

Ejecuta el pipeline ETL completo usando detección de duplicados con DBSCAN.

```bash
# Uso básico (eps=0.3)
python scripts/run_etl_with_dbscan.py

# Con parámetro eps personalizado
python scripts/run_etl_with_dbscan.py --eps 0.4

# Con base de datos personalizada
python scripts/run_etl_with_dbscan.py --db-path data/custom_database.db --eps 0.3
```

**Características**:
- Método: DBSCAN (Density-Based Clustering)
- Velocidad: Rápida (~2.4s para 200 registros)
- Precisión: Detecta variaciones en títulos, precios, ubicaciones
- **Recomendado para producción**

**Parámetros**:
- `--eps`: Distancia máxima entre puntos en un cluster (default: 0.3)
  - Valores más bajos (0.2): Más estricto, detecta menos duplicados
  - Valores más altos (0.5): Más permisivo, puede agrupar ofertas diferentes

---

#### `run_etl_with_hierarchical.py` - Pipeline con Clustering Jerárquico

Ejecuta el pipeline ETL completo usando detección de duplicados con clustering jerárquico.

```bash
# Uso básico (threshold=75.0)
python scripts/run_etl_with_hierarchical.py

# Con umbral personalizado
python scripts/run_etl_with_hierarchical.py --threshold 80.0

# Con base de datos personalizada
python scripts/run_etl_with_hierarchical.py --db-path data/custom_database.db --threshold 75.0
```

**Características**:
- Método: Clustering Jerárquico Bottom-Up
- Velocidad: **MUY LENTA** (~19 minutos para 200 registros)
- Precisión: Control fino sobre el proceso de agrupación
- **⚠️ ADVERTENCIA**: Solo usar para análisis detallado de muestras pequeñas

**Parámetros**:
- `--threshold`: Umbral de similaridad (default: 75.0)
  - Valores más bajos (70): Más permisivo
  - Valores más altos (80): Más estricto

---

### 2. Solo Detección de Duplicados

#### `detect_duplicates_only.py` - Detección sobre Datos Transformados

Ejecuta **SOLO** la detección de duplicados sobre datos ya transformados (sin ejecutar todo el pipeline).

```bash
# Método por coordenadas (original)
python scripts/detect_duplicates_only.py --method coordinates

# Método DBSCAN (recomendado)
python scripts/detect_duplicates_only.py --method dbscan
python scripts/detect_duplicates_only.py --method dbscan --eps 0.4

# Método jerárquico (lento)
python scripts/detect_duplicates_only.py --method hierarchical
python scripts/detect_duplicates_only.py --method hierarchical --threshold 80.0

# Con base de datos personalizada
python scripts/detect_duplicates_only.py --method dbscan --db-path data/custom_database.db
```

**Características**:
- No ejecuta el pipeline completo
- Carga datos desde `transformed_listings`
- Útil para probar diferentes métodos sin reprocesar todo
- Guarda resultados en `duplicates_detected` y `duplicates_moved`

**Métodos disponibles**:
- `coordinates`: Detección por coordenadas exactas
- `dbscan`: Detección con DBSCAN (recomendado)
- `hierarchical`: Detección con clustering jerárquico

**Parámetros**:
- `--method`: Método de detección (coordinates, dbscan, hierarchical)
- `--db-path`: Ruta a la base de datos (opcional)
- `--eps`: Parámetro eps para DBSCAN (solo con --method dbscan)
- `--threshold`: Umbral para clustering jerárquico (solo con --method hierarchical)

---

## Comparación de Métodos

| Método | Script | Velocidad (200 reg) | Escalabilidad | Uso Recomendado |
|--------|--------|---------------------|---------------|-----------------|
| **Coordenadas** | `run_etl.py` | ~0.1s | Excelente | Producción (coordenadas exactas) |
| **DBSCAN** | `run_etl_with_dbscan.py` | ~2.4s | Excelente | **Producción (recomendado)**  |
| **Jerárquico** | `run_etl_with_hierarchical.py` | ~19 min | Muy mala | Solo análisis detallado |

---

## Flujo de Trabajo Recomendado

### Para Producción

1. **Pipeline completo con DBSCAN**:
   ```bash
   python scripts/run_etl_with_dbscan.py
   ```

2. **Si necesitas ajustar parámetros**:
   ```bash
   # Probar diferentes valores de eps
   python scripts/detect_duplicates_only.py --method dbscan --eps 0.2
   python scripts/detect_duplicates_only.py --method dbscan --eps 0.3
   python scripts/detect_duplicates_only.py --method dbscan --eps 0.4
   ```

### Para Análisis Detallado

1. **Ejecutar pipeline completo**:
   ```bash
   python scripts/run_etl.py  # O con DBSCAN
   ```

2. **Probar clustering jerárquico en muestra pequeña**:
   ```bash
   # Primero limitar datos en la BD o usar muestra
   python scripts/detect_duplicates_only.py --method hierarchical --threshold 75.0
   ```

### Para Desarrollo/Pruebas

1. **Probar diferentes métodos sin reprocesar**:
   ```bash
   # Ya tienes datos transformados
   python scripts/detect_duplicates_only.py --method coordinates
   python scripts/detect_duplicates_only.py --method dbscan --eps 0.3
   ```

---

## Visualización de Resultados

Después de ejecutar cualquier script, puedes visualizar los resultados:

```bash
# Ver duplicados detectados
python scripts/view_duplicates.py

# Exportar duplicados a CSV
python scripts/export_cross_portal_duplicates.py

# Ver todos los datos transformados
python scripts/dump_db_to_txt.py
```



---

## Notas Importantes

1. **DBSCAN es el método recomendado** para producción por su velocidad y escalabilidad
2. **Clustering jerárquico** solo debe usarse para análisis detallado de muestras pequeñas
3. **Método de coordenadas** es útil cuando solo necesitas detectar coordenadas exactamente iguales
4. Todos los métodos guardan resultados en las mismas tablas (`duplicates_detected`, `duplicates_moved`)
5. Los scripts de "solo detección" requieren que exista la tabla `transformed_listings`

---

