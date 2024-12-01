FROM python:3.10-slim

# Instalar herramientas necesarias
RUN apt-get update && apt-get install -y iproute2 iputils-ping && rm -rf /var/lib/apt/lists/*

# Configurar el directorio de trabajo
WORKDIR /app

# Copiar el script principal del cliente
COPY myclient.py /app/myclient.py

# Copiar los archivos del cliente
COPY client_files /app/client_files

# Copiar el script de entrada
COPY client_entrypoint.sh /app/client_entrypoint.sh

# Hacer ejecutable el script de entrada
RUN chmod +x /app/client_entrypoint.sh

# Comando de entrada predeterminado
ENTRYPOINT ["/app/client_entrypoint.sh"]
