#!/data/data/com.termux/files/usr/bin/sh
# Libera memoria con un toque: cierra las apps pesadas que no estás usando y avisa cuánta RAM liberó.
# Cierra las de APPS y las de ~/.liberar_extra (un nombre de paquete por línea).
# Abitab ID queda además sin permiso para correr en segundo plano: su ícono sigue, la abrís a mano cuando
# la necesites, y al cerrarla no vuelve a arrancar sola.
# Ojo: una app cerrada no manda notificaciones hasta que la volvés a abrir.
# Necesita ADB (puerto 5555, ver adb_reconectar.sh).
APPS="com.okinc.okex.gp com.instagram.android org.telegram.messenger uy.com.abitab.iddigital.prod"
ABITAB=uy.com.abitab.iddigital.prod

S=127.0.0.1:5555
adb devices 2>/dev/null | grep -q "^$S[[:space:]]*device$" || adb connect "$S" >/dev/null 2>&1
if ! adb devices 2>/dev/null | grep -q "^$S[[:space:]]*device$"; then
  termux-notification --id liberar --title 'Liberar ⚠️' --content 'No hay ADB. Tocá RECONECTAR en la notificación de ADB y probá de nuevo.'
  exit 1
fi
A() { adb -s "$S" shell "$@" 2>/dev/null; }
libre() { A cat /proc/meminfo | awk '/^MemAvailable:/{printf "%d", $2/1024}'; }

ANTES=$(libre)
termux-notification --id liberar --title 'Liberando memoria…' --content 'Cerrando apps'
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
termux-notification --id liberar --title "Memoria libre: $DESPUES MB (antes $ANTES MB)" --content "Cerré:$CERRADAS"
