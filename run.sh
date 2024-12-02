#!/bin/bash

# Correr el servidor
echo "Iniciando el servidor..."
docker run -it -v "$(pwd)/server/server_files:/app/server_files" -v "$(pwd)/server/db:/app/db" --name server1 --cap-add NET_ADMIN --network servers server

# Correr el cliente
echo "Iniciando el cliente..."
docker run -it -v "$(pwd)/client/client_files:/app/client_files" --name client1 --cap-add NET_ADMIN --network clients client