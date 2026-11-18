#!/data/data/com.termux/files/usr/bin/sh
# Libera memoria con un toque: cierra las apps pesadas que no estás usando y avisa cuánta RAM liberó.
# Cierra las de APPS y las de ~/.liberar_extra (un nombre de paquete por línea).
# Abitab ID queda además sin permiso para correr en segundo plano: su ícono sigue, la abrís a mano cuando
# la necesites, y al cerrarla no vuelve a arrancar sola.
# Ojo: una app cerrada no manda notificaciones hasta que la volvés a abrir.
# Necesita ADB (puerto 5555, ver adb_reconectar.sh).
#   liberar.sh boton   pone la notificación fija con el botón LIBERAR (lo llama alerta.sh cada 15 min,
#                      así vuelve si la borraste o reiniciaste). Sin "boton": cierra las apps.
APPS="com.okinc.okex.gp com.instagram.android org.telegram.messenger uy.com.abitab.iddigital.prod"
ABITAB=uy.com.abitab.iddigital.prod

S=127.0.0.1:5555
aviso() {   # $1 = título, $2 = texto. Siempre en la misma notificación fija, con el botón.
  termux-notification --id liberar --ongoing --priority low --title "$1" --content "$2" \
    --button1 'LIBERAR' --button1-action 'sh /data/data/com.termux/files/home/bexo-scripts/telefono/liberar.sh'
}
if [ "$1" = boton ]; then
  # si ya está (con el último resultado), no la pisa
  termux-notification-list 2>/dev/null | grep -q '"liberar"' || aviso 'Liberar memoria' 'Tocá LIBERAR para cerrar OKX, Instagram, Telegram y Abitab'
  exit 0
fi
adb devices 2>/dev/null | grep -q "^$S[[:space:]]*device$" || adb connect "$S" >/dev/null 2>&1
if ! adb devices 2>/dev/null | grep -q "^$S[[:space:]]*device$"; then
  aviso 'Liberar ⚠️' 'No hay ADB. Tocá RECONECTAR en la notificación de ADB y probá de nuevo.'
  exit 1
fi
A() { adb -s "$S" shell "$@" 2>/dev/null; }
libre() { A cat /proc/meminfo | awk '/^MemAvailable:/{printf "%d", $2/1024}'; }

ANTES=$(libre)
aviso 'Liberando memoria…' 'Cerrando apps'
CERRADAS=""
for P in $APPS $(cat ~/.liberar_extra 2>/dev/null); do
  # solo las que están instaladas y abiertas
  if A pidof "$P" >/dev/null; then
    A am force-stop "$P"
    CERRADAS="$CERRADAS $(echo "$P" | awk -F. '{print $(NF>2?NF-1:NF)}')"
  fi
done
# Abitab: nunca en segundo plano. Si quedó desactivada por la versión anterior, la vuelve a activar (vuelve el ícono).
A pm enable "$ABITAB" >/dev/null
A cmd appops set "$ABITAB" RUN_ANY_IN_BACKGROUND ignore
sleep 3
DESPUES=$(libre)
[ -n "$CERRADAS" ] || CERRADAS=" nada (ya estaban cerradas)"
aviso "Memoria libre: $DESPUES MB (antes $ANTES MB)" "$(date +%H:%M) cerré:$CERRADAS"
