#!/data/data/com.termux/files/usr/bin/sh
# Lo corre Termux cada 15 minutos: si la alarma de compras y ventas no está corriendo, la arranca.
# También deja escuchando ntfy (botón "Armar en Binance", telefono/escuchar.sh).
# Así sigue andando aunque Android la cierre o reinicies el teléfono.
sh ~/bexo-scripts/telefono/boton.sh
sh ~/bexo-scripts/telefono/liberar.sh boton
sh ~/bexo-scripts/telefono/adb_reconectar.sh vigilar
sh ~/bexo-scripts/telefono/movs_uy_boton.sh
sh ~/bexo-scripts/telefono/tunel_vps.sh
sh ~/bexo-scripts/telefono/diagnostico.sh boton
sh ~/bexo-scripts/telefono/diagnostico.sh vigilar &
sh ~/bexo-scripts/telefono/escuchar.sh vigilar
PID=~/.alerta_compras.pid
if [ -f "$PID" ] && kill -0 "$(cat "$PID")" 2>/dev/null; then exit 0; fi
cd ~/bexo-scripts && git pull -q --ff-only >> ~/alerta.log 2>&1
termux-wake-lock
nohup python ~/bexo-scripts/alerta_compras.py >> ~/alerta.log 2>&1 &
echo $! > "$PID"
