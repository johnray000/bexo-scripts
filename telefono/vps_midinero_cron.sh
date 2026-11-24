#!/data/data/com.termux/files/usr/bin/sh
# Cambia el día del cron de MiDinero en el VPS desde el teléfono (sin abrir la consola web): manda por SSH
# vps/midinero_cron_instalar.sh y muestra el resultado. Usa VPS_SSH de ~/.subir-ordenes.env.
DIR=/data/data/com.termux/files/home/bexo-scripts
VPS=$(grep '^VPS_SSH=' ~/.subir-ordenes.env 2>/dev/null | cut -d= -f2)
[ -n "$VPS" ] || { echo "❌ Falta VPS_SSH en ~/.subir-ordenes.env"; exit 2; }
ssh -o BatchMode=yes -o ConnectTimeout=20 -o StrictHostKeyChecking=accept-new -o LogLevel=ERROR \
  "$VPS" 'bash -s' < "$DIR/vps/midinero_cron_instalar.sh"
