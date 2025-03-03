# Dockerfile.base
FROM python:3.9-slim

# Definir el directorio de trabajo
WORKDIR /app

# Instalar dependencias del sistema necesarias
RUN apt-get update && apt-get install -y --no-install-recommends iproute2 && rm -rf /var/lib/apt/lists/*

# Copiar el archivo de requerimientos (asegúrate de tener uno con tus dependencias, por ejemplo: streamlit, etc.)
COPY requirements.txt /app/requirements.txt

# Instalar dependencias de Python (esto se cachea en capas, así no se reinstala cada vez)
RUN pip install --no-cache-dir -r requirements.txt

# Exponer el puerto de Streamlit (opcional, pero útil para documentar el puerto)
EXPOSE 8501
