#!/data/data/com.termux/files/usr/bin/sh
# Acceso directo "CazarPeYa" del escritorio (Termux:Widget) y botones de la notificación de PeYa.
#   peya.sh            → pregunta el día (hoy, mañana, jueves…) y caza
#   peya.sh mañana     → caza ese día sin preguntar
#   peya.sh parar      → para la caza
# Si ya está cazando, tocar el acceso directo la para.
P=/data/data/com.termux/files/home
PID="$P/.peya.pid"
if [ "$1" = "parar" ] || { [ -f "$PID" ] && kill -0 "$(cat "$PID")" 2>/dev/null; }; then
  touch "$P/.peya_parar"
  termux-notification --id peya-estado --title '⏹ PeYa: parando…' --content 'Un momento'
  exit 0
fi
DIA="$1"
if [ -z "$DIA" ]; then
  DIA=$(termux-dialog radio -t 'Cazar turnos para…' -v 'hoy,mañana,lunes,martes,miércoles,jueves,viernes,sábado,domingo' \
    | python -c 'import json,sys; d=json.load(sys.stdin); print(d.get("text","") if d.get("code")==-1 else "")')
  [ -z "$DIA" ] && exit 0
fi
echo $$ > "$PID"
termux-wake-lock
termux-notification --id peya-estado --ongoing --title "🟢 PeYa: arrancando ($DIA)" --content 'Abriendo la app…' \
  --button1 'PARAR DEL TODO' --button1-action "sh $P/bexo-scripts/telefono/peya.sh parar"
cd ~/bexo-scripts && git pull -q --ff-only >> ~/peya.log 2>&1
if ! python ~/bexo-scripts/peya_turnos.py --dia "$DIA" >> ~/peya.log 2>&1; then
  # el script se cortó con un error: queda parado y lo dice
  termux-notification --id peya-estado --title "⏹ PeYa: PARADO ($DIA)" \
    --content "Error: $(tail -1 ~/peya.log | cut -c1-150)" \
    --button1 'CAZAR DE NUEVO' --button1-action "sh $P/bexo-scripts/telefono/peya.sh $DIA"
fi
termux-wake-unlock
rm -f "$PID"
