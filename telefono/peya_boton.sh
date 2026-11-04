#!/data/data/com.termux/files/usr/bin/sh
# Notificación fija para arrancar la caza de PeYa con un toque: HOY, MAÑANA u OTRO DÍA (pregunta cuál).
S=/data/data/com.termux/files/home/bexo-scripts/telefono/peya.sh
termux-notification --id peya-lanzador --ongoing --priority low --title 'Cazar turnos PeYa' \
  --content 'Elegí el día. Para parar: bajar volumen x2 o PARAR' \
  --button1 'HOY' --button1-action "sh $S hoy" \
  --button2 'MAÑANA' --button2-action "sh $S mañana" \
  --button3 'OTRO DÍA' --button3-action "sh $S"
