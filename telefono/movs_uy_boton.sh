#!/data/data/com.termux/files/usr/bin/sh
# Lo llama alerta.sh cada 15 min. Muestra el botón de UNA app por vez (en este orden), la primera que esté pendiente:
# lunes, miércoles y viernes desde las 10 si hace más de un día y medio que no se lee, o cualquier día si pasaron
# más de 3 días (por si un día de lectura se pasó).
# Cuando esa app se lee, aparece el botón de la siguiente. Cada botón corre solo su app.
APPS="prex itau ocablue mercadopago"
if [ "$(date +%H)" -lt 10 ]; then exit 0; fi
for APP in $APPS; do
  ULT=$(cat ~/.movs_uy_ultima_"$APP" 2>/dev/null || echo 0)
  [ "$APP" = prex ] && [ "$ULT" = 0 ] && ULT=$(cat ~/.movs_uy_ultima 2>/dev/null || echo 0)
  HORAS=$(( ($(date +%s) - ULT) / 3600 ))
  DIAS=$(( HORAS / 24 ))
  if [ "$HORAS" -lt 36 ]; then continue; fi
  case "$(date +%u)" in 1|3|5) ;; *) [ "$HORAS" -le 72 ] && continue ;; esac
  CUANDO="Hace $DIAS días que no se lee"
  [ "$ULT" = 0 ] && CUANDO="Todavía no se leyó"
  case "$APP" in prex) NOMBRE=Prex ;; itau) NOMBRE=Itaú ;; ocablue) NOMBRE="OCA Blue" ;; mercadopago) NOMBRE="Mercado Pago" ;; *) NOMBRE=$APP ;; esac
  termux-notification --id movs-uy --ongoing --priority high \
    --title "Movimientos UY: $NOMBRE" --content "$CUANDO $NOMBRE. Tocá el botón y poné tu huella." \
    --button1 "LEER $NOMBRE" \
    --button1-action "sh /data/data/com.termux/files/home/bexo-scripts/telefono/movs_uy.sh $APP"
  exit 0
done
termux-notification-remove movs-uy
