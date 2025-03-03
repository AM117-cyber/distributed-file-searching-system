# # Dockerfile para el cliente
# FROM python:3.9-slim

# # Crear directorio de trabajo
# WORKDIR /app

# # Instalar herramientas de red necesarias
# RUN apt-get update && apt-get install -y --no-install-recommends iproute2 && rm -rf /var/lib/apt/lists/*

# # Copiar los archivos necesarios
# COPY client/front.py ./front.py
# COPY . .
# # COPY client/client.sh /usr/local/bin/client.sh

# # Asegúrate de que el script sea ejecutable
# # RUN chmod +x /usr/local/bin/client.sh

# RUN pip install streamlit

# EXPOSE 8501

# HEALTHCHECK CMD curl --fail http://localhost:8501 || exit 1

# # Ejecutar el script de configuración y luego el cliente
# # ENTRYPOINT ["/bin/bash", "-c", "/usr/local/bin/client.sh"]
# ENTRYPOINT ["streamlit", "run", "front.py", "--server.port=8501", "--server.address=0.0.0.0"]

# # docker run -p 8501:8501 your-image-name

# # Dockerfile para el cliente
# FROM python:3.9-slim

# # Crear directorio de trabajo
# WORKDIR /app

# # Instalar herramientas de red necesarias
# RUN apt-get update && apt-get install -y --no-install-recommends iproute2 && rm -rf /var/lib/apt/lists/*

# # Copiar los archivos necesarios
# COPY  client.py /app
# COPY  client.sh app

# # Asegúrate de que el script sea ejecutable
# RUN chmod +x /app/client.sh

# # Ejecutar el script de configuración y luego el cliente
# ENTRYPOINT ["/bin/bash", "-c", "/app/client.sh && python /app/client.py"]


# FROM python:3.9-slim

# WORKDIR /app

# COPY ./requirements.txt .

# RUN pip install --no-cache-dir -r requirements.txt

# RUN apt-get update && apt-get install -y --no-install-recommends iproute2 && rm -rf /var/lib/apt/lists/*



# COPY . .

# EXPOSE 8501

# # Asegúrate de que el script sea ejecutable
# RUN chmod +x /app/client.sh

# # Ejecutar el script de configuración y luego el cliente
# ENTRYPOINT ["/bin/bash", "-c", "/app/client.sh"]

# CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]



FROM python:3.9-slim

# Crear directorio de trabajo
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends iproute2 && rm -rf /var/lib/apt/lists/*

# Copiar los archivos necesarios
COPY client/client.py ./client.py
COPY client/client.sh /usr/local/bin/client.sh

RUN chmod +x /usr/local/bin/client.sh

ENTRYPOINT ["/bin/bash", "-c", "/usr/local/bin/client.sh && python /app/client.py"]
