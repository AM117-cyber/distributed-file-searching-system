FROM base

WORKDIR /app

COPY server/routing.sh /app
COPY server/server.py /app

COPY server/cert.pem /app/cert.pem
COPY server/key.pem /app/key.pem

RUN chmod +x /app/routing.sh

ENTRYPOINT [ "/app/routing.sh" ]