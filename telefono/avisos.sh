#!/data/data/com.termux/files/usr/bin/sh
# Lo corre Termux cada 15 minutos: si el lector de avisos de las apps (facturacion/notifs_apps.py)
# no está corriendo, lo arranca. Así sigue aunque Android lo cierre o reinicies el teléfono.
PID=~/.notifs_apps.pid
if [ -f "$PID" ] && kill -0 "$(cat "$PID")" 2>/dev/null; then exit 0; fi
cd ~/bexo-scripts && git pull -q --ff-only >> ~/avisos.log 2>&1
termux-wake-lock
nohup python ~/bexo-scripts/facturacion/notifs_apps.py >> ~/avisos.log 2>&1 &
echo $! > "$PID"
