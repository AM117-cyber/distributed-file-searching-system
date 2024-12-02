#!/bin/bash

# Crear las redes
echo "Creando redes..."
docker network create clients --subnet 10.0.10.0/24
docker network create servers --subnet 10.0.11.0/24

# Construir la imagen del router
echo "Construyendo la imagen del router..."
docker build -t router -f router/router.Dockerfile .

# Crear y configurar el contenedor del router
echo "Creando y configurando el router..."
docker run -itd --rm --name router router
docker network connect --ip 10.0.10.254 clients router
docker network connect --ip 10.0.11.254 servers router

# Construir las imágenes de cliente y servidor
echo "Construyendo las imágenes de cliente y servidor..."
docker build -t client -f client/client.Dockerfile .
docker build -t server -f server/server.Dockerfile .

echo "Startup completado."