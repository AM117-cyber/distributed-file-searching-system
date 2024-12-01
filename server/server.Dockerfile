# Dockerfile para el servidor
FROM python:3.9-slim

# Crear directorio de trabajo
WORKDIR /app

# Instalar herramientas de red necesarias
RUN apt-get update && apt-get install -y --no-install-recommends iproute2 && rm -rf /var/lib/apt/lists/*


# Copiar los archivos necesarios
COPY server/server.py ./server.py
COPY server/server.sh /usr/local/bin/server.sh
# Asegúrate de que el script sea ejecutable
RUN chmod +x /usr/local/bin/server.sh
# Crear la carpeta server_files
RUN mkdir -p /app/server_files && chmod -R 777 /app/server_files

# Copiar el script del servidor
COPY myserver.py /app/myserver.py



# Ejecutar el script de configuración y luego iniciar el servidor
ENTRYPOINT ["/bin/bash", "-c", "/usr/local/bin/server.sh && python /app/server.py"]



# # Exponer el puerto del servidor
# EXPOSE 9999

# # Ejecutar el servidor
# CMD ["python", "/app/myserver.py"]