FROM base

WORKDIR /app

COPY server/routing.sh /app
COPY server/server.py /app

RUN chmod +x /app/routing.sh

ENTRYPOINT [ "/app/routing.sh" ]