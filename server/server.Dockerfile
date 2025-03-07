FROM base

WORKDIR /app
# Copia los archivos necesarios
COPY server/routing.sh /app
COPY server/server.py /app
COPY server/cert.pem /app/cert.pem
COPY server/key.pem /app/key.pem

# Asigna permisos de ejecución al script de routing
RUN chmod +x /app/routing.sh

# Define el punto de entrada
ENTRYPOINT [ "/app/routing.sh" ]
