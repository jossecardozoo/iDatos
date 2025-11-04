# Dockerfile para ejecutar el ETL con Prefect (flujo local)
FROM python:3.11-slim

WORKDIR /app

# Copiar requirements y instalar
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copiar el resto del proyecto
COPY . /app

ENV PYTHONUNBUFFERED=1

# Crear carpeta data
RUN mkdir -p /app/data

# Punto de entrada: ejecutar el flow ETL
CMD ["python", "-u", "scripts/etl_functions_prefect.py"]
