#!/bin/bash
# Actualiza la Brújula P2P en el VPS con un solo comando (siempre desde main):
#   curl -fsSL https://raw.githubusercontent.com/johnray000/bexo-scripts/main/vps/actualizar_brujula.sh | sudo bash
# No guarda nada en la carpeta donde estés: baja el instalador a una carpeta temporal y lo corre con main.
set -e
[ "$(id -u)" = "0" ] || { echo "Correlo con sudo."; exit 1; }
TMP=$(mktemp -d)
curl -fsSL https://raw.githubusercontent.com/johnray000/bexo-scripts/main/vps/dashboard_instalar.sh -o "$TMP/instalar.sh"
bash "$TMP/instalar.sh" main < /dev/tty   # por si el instalador tiene que preguntar algo
rm -rf "$TMP"
