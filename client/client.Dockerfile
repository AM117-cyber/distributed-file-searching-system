# Dockerfile para el cliente
FROM base

# Crear directorio de trabajo
WORKDIR /app

# Copiar los archivos necesarios
COPY client/client.py ./client.py
COPY client/client.sh /usr/local/bin/client.sh

# Asegúrate de que el script sea ejecutable
RUN chmod +x /usr/local/bin/client.sh

# Ejecutar el script de configuración y luego el cliente
ENTRYPOINT ["/bin/bash", "-c", "/usr/local/bin/client.sh && python /app/new_client.py"]