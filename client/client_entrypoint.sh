#!/bin/bash

# Configurar la ruta predeterminada al router
ip route del default
ip route add default via 10.0.10.254

# Ejecutar la aplicación del cliente
python /app/myclient.py
