#!/data/data/com.termux/files/usr/bin/sh
# Túnel para que el VPS salga a internet por la conexión del teléfono (IP de Uruguay).
# MiDinero bloquea al VPS por estar en EE.UU.; con esto el VPS ve un proxy en su 127.0.0.1:1080
# (solo accesible desde el propio VPS) y midinero.py lo usa. Lo llama alerta.sh cada 15 min:
# si el vigilante no está corriendo, lo arranca. El vigilante reconecta a los 10 s si la conexión se corta
# (cambio de red, Android que duerme a Termux). Necesita VPS_SSH=usuario@ip en ~/.subir-ordenes.env y la
# clave ~/.ssh/id_ed25519 autorizada en el VPS.
PID=~/.tunel_vps.pid
if [ -f "$PID" ] && kill -0 "$(cat "$PID")" 2>/dev/null; then exit 0; fi
VPS=$(grep '^VPS_SSH=' ~/.subir-ordenes.env 2>/dev/null | cut -d= -f2)
[ -n "$VPS" ] || exit 0
termux-wake-lock
pkill -f "ssh -N -R 1080" 2>/dev/null
nohup sh -c "while true; do
  ssh -N -R 1080 -o ServerAliveInterval=15 -o ServerAliveCountMax=2 -o ExitOnForwardFailure=yes \
    -o ConnectTimeout=20 -o BatchMode=yes -o StrictHostKeyChecking=accept-new '$VPS'
  echo \"\$(date '+%d/%m %H:%M') se cortó, reconecto en 10 s\"
  sleep 10
done" >> ~/tunel.log 2>&1 &
echo $! > "$PID"
