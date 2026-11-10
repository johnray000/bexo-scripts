#!/data/data/com.termux/files/usr/bin/sh
# Lo llama alerta.sh cada 15 min. Muestra el botón de UNA app por vez (en este orden), la primera que esté pendiente:
# los martes desde las 10 si hace 6 días o más que no se lee, o cualquier día si pasaron más de 8.
# Cuando esa app se lee, aparece el botón de la siguiente. Cada botón corre solo su app.
APPS="prex itau"
if [ "$(date +%H)" -lt 10 ]; then exit 0; fi
for APP in $APPS; do
  ULT=$(cat ~/.movs_uy_ultima_"$APP" 2>/dev/null || echo 0)
  [ "$APP" = prex ] && [ "$ULT" = 0 ] && ULT=$(cat ~/.movs_uy_ultima 2>/dev/null || echo 0)
  DIAS=$(( ($(date +%s) - ULT) / 86400 ))
  if [ "$DIAS" -lt 6 ]; then continue; fi
  if [ "$(date +%u)" != "2" ] && [ "$DIAS" -le 8 ]; then continue; fi
  CUANDO="Hace $DIAS días que no se lee"
  [ "$ULT" = 0 ] && CUANDO="Todavía no se leyó"
  case "$APP" in prex) NOMBRE=Prex ;; itau) NOMBRE=Itaú ;; *) NOMBRE=$APP ;; esac
  termux-notification --id movs-uy --ongoing --priority high \
    --title "Movimientos UY: $NOMBRE" --content "$CUANDO $NOMBRE. Tocá el botón y poné tu huella." \
    --button1 "LEER $NOMBRE" \
    --button1-action "sh /data/data/com.termux/files/home/bexo-scripts/telefono/movs_uy.sh $APP"
  exit 0
done
termux-notification-remove movs-uy
