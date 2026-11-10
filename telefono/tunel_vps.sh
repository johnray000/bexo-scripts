#!/data/data/com.termux/files/usr/bin/sh
# Túnel para que el VPS salga a internet por la conexión del teléfono (IP de Uruguay).
# MiDinero bloquea al VPS por estar en EE.UU.; con esto el VPS ve un proxy en su 127.0.0.1:1080
# (solo accesible desde el propio VPS) y midinero.py lo usa. Lo llama alerta.sh cada 15 min:
# si el túnel no está, lo levanta. Necesita VPS_SSH=usuario@ip en ~/.subir-ordenes.env y la clave
# ~/.ssh/id_ed25519 autorizada en el VPS.
pgrep -f "ssh -N -R 1080" >/dev/null && exit 0
VPS=$(grep '^VPS_SSH=' ~/.subir-ordenes.env 2>/dev/null | cut -d= -f2)
[ -n "$VPS" ] || exit 0
termux-wake-lock
nohup ssh -N -R 1080 -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes \
  -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$VPS" >> ~/tunel.log 2>&1 &
