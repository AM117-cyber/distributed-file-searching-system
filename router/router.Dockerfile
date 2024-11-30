# Usar una imagen ligera
FROM alpine:latest

# Instalar herramientas necesarias
RUN apk add --no-cache iproute2 iptables bash

# Habilitar IP forwarding
RUN echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf

# Copiar el script de inicio del router
COPY router_entrypoint.sh /app/router_entrypoint.sh
RUN chmod +x /app/router_entrypoint.sh

# Establecer el script de entrada
ENTRYPOINT ["/app/router_entrypoint.sh"]
