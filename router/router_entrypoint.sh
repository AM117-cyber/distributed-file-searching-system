#!/bin/bash

# Aplicar configuraciones de sysctl
sysctl -p

# Configurar reglas de iptables para permitir el tráfico entre las redes
iptables -A FORWARD -i eth1 -o eth2 -j ACCEPT
iptables -A FORWARD -i eth2 -o eth1 -j ACCEPT

# Configurar NAT para el tráfico de clientes a servidores
iptables -t nat -A POSTROUTING -s 10.0.10.0/24 -o eth2 -j MASQUERADE

# Mantener el contenedor en ejecución
tail -f /dev/null
