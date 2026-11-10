#!/data/data/com.termux/files/usr/bin/sh
# Lo llama alerta.sh cada 15 min. Los martes (o cualquier día si ya pasaron más de 8 días sin leer) pone una
# notificación fija con el botón para leer los movimientos de las apps uruguayas. Se va sola cuando se leyeron.
ULT=$(cat ~/.movs_uy_ultima 2>/dev/null || echo 0)
DIAS=$(( ($(date +%s) - ULT) / 86400 ))
if [ "$DIAS" -lt 6 ]; then exit 0; fi
if [ "$(date +%u)" != "2" ] && [ "$DIAS" -le 8 ]; then exit 0; fi
if [ "$(date +%H)" -lt 10 ]; then exit 0; fi
termux-notification --id movs-uy --ongoing --priority high \
  --title 'Movimientos UY de la semana' --content "Hace $DIAS días que no se leen. Tocá el botón y poné tu huella." \
  --button1 'LEER MOVIMIENTOS UY' \
  --button1-action 'sh /data/data/com.termux/files/home/bexo-scripts/telefono/movs_uy.sh'
