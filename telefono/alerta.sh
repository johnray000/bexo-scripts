#!/data/data/com.termux/files/usr/bin/sh
# Lo corre Termux cada 15 minutos: si la alarma de compras no está corriendo, la arranca.
# Así sigue andando aunque Android la cierre o reinicies el teléfono.
PID=~/.alerta_compras.pid
if [ -f "$PID" ] && kill -0 "$(cat "$PID")" 2>/dev/null; then exit 0; fi
cd ~/bexo-scripts && git pull -q --ff-only >> ~/alerta.log 2>&1
termux-wake-lock
nohup python ~/bexo-scripts/alerta_compras.py >> ~/alerta.log 2>&1 &
echo $! > "$PID"
