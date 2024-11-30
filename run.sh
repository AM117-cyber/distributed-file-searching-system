#!/bin/bash

# Habilita la salida de comandos y errores
set -e

echo "Iniciando servidor..."

# Ejecutar el contenedor del servidor con IP estática
docker run -d --name server1 \
    --network servers \
    --ip 10.0.11.10 \
    -v "$(pwd)/server_files:/app/server_files" \
    server

echo "Servidor iniciado con IP 10.0.11.10."

echo "Iniciando cliente..."

# Ejecutar el contenedor del cliente en modo interactivo
docker run -it --name client1 --network clients --cap-add=NET_ADMIN client

# Configurar la ruta predeterminada del cliente para que apunte al router
docker exec client1 sh -c "
    ip route del default
    ip route add default via 10.0.10.254
"

echo "Cliente configurado y en ejecución."


echo "Ejecución completa. Verificando conectividad..."

# Verificar conectividad desde el cliente al servidor
docker exec client1 ping -c 4 10.0.11.10 || echo "Ping fallido. Verifica la configuración de red."

echo "Conectividad verificada. Cliente enviará comandos al servidor."

# Ejecutar la aplicación del cliente
# docker exec -it client1 python /app/myclient.py

echo "Proceso finalizado."
