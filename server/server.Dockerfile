# Usar la imagen oficial de Python
FROM python:3.10-slim

# Instalar iproute2 y iputils-ping (si aún no lo has hecho)
RUN apt-get update && apt-get install -y iproute2 iputils-ping && rm -rf /var/lib/apt/lists/*

# Establecer el directorio de trabajo
WORKDIR /app

# Crear la carpeta server_files
RUN mkdir /app/server_files

# Copiar el script del servidor
COPY myserver.py /app/myserver.py

# Exponer el puerto del servidor
EXPOSE 9999

# Ejecutar el servidor
CMD ["python", "/app/myserver.py"]