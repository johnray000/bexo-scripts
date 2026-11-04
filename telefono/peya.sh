#!/data/data/com.termux/files/usr/bin/sh
# Acceso directo "Turnos PeYa" del escritorio (Termux:Widget): lo tocás una vez y refresca los turnos;
# si ya está refrescando, lo para. También se para con el botón PARAR de la notificación o al pasar 1 hora.
P=/data/data/com.termux/files/home
PID="$P/.peya.pid"
if [ "$1" = "parar" ] || { [ -f "$PID" ] && kill -0 "$(cat "$PID")" 2>/dev/null; }; then
  touch "$P/.peya_parar"
  termux-notification --id peya-estado --title 'PeYa Rider' --content 'Parando…'
  exit 0
fi
echo $$ > "$PID"
termux-wake-lock
termux-notification --id peya-estado --ongoing --title 'PeYa Rider' --content 'Refrescando turnos… no toques la pantalla' \
  --button1 'PARAR' --button1-action "sh $P/bexo-scripts/telefono/peya.sh parar"
cd ~/bexo-scripts && git pull -q --ff-only >> ~/peya.log 2>&1
python ~/bexo-scripts/peya_turnos.py >> ~/peya.log 2>&1
termux-notification --id peya-estado --title 'PeYa Rider' --content "$(tail -1 ~/peya.log | cut -c1-200)"
termux-wake-unlock
rm -f "$PID"
