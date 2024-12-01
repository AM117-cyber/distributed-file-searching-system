# Dockerfile para el cliente
FROM python:3.9-slim

# Crear directorio de trabajo
WORKDIR /app

# Instalar herramientas de red necesarias
RUN apt-get update && apt-get install -y --no-install-recommends iproute2 && rm -rf /var/lib/apt/lists/*

# Copiar los archivos necesarios
COPY client/client.py ./client.py
COPY client/client.sh /usr/local/bin/client.sh

# Copiar los archivos del cliente
COPY client/client_files /app/client_files

# Asegúrate de que el script sea ejecutable
RUN chmod +x /usr/local/bin/client.sh

# Ejecutar el script de configuración y luego el cliente
ENTRYPOINT ["/bin/bash", "-c", "/usr/local/bin/client.sh && python /app/client.py"]