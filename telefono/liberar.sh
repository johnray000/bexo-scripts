#!/data/data/com.termux/files/usr/bin/sh
# Libera memoria con un toque: cierra las apps pesadas que no estás usando y deja dormida a Abitab ID.
#   liberar.sh          cierra las apps de APPS (y las de ~/.liberar_extra, una por línea) y avisa cuánta RAM liberó
#   liberar.sh abitab   despierta Abitab ID y la abre. La próxima vez que toques "Liberar" vuelve a quedar dormida.
# "Dormida" = desactivada (pm disable-user): no aparece, no corre en segundo plano y no gasta nada, pero no se borra
# ni pierde tu sesión. Si alguna vez querés despertarla a mano:  adb -s 127.0.0.1:5555 shell pm enable uy.com.abitab.iddigital.prod
# Ojo: una app cerrada no manda notificaciones hasta que la volvés a abrir.
# Necesita ADB (puerto 5555, ver adb_reconectar.sh).
APPS="com.okinc.okex.gp com.instagram.android org.telegram.messenger"
ABITAB=uy.com.abitab.iddigital.prod

S=127.0.0.1:5555
adb devices 2>/dev/null | grep -q "^$S[[:space:]]*device$" || adb connect "$S" >/dev/null 2>&1
if ! adb devices 2>/dev/null | grep -q "^$S[[:space:]]*device$"; then
  termux-notification --id liberar --title 'Liberar ⚠️' --content 'No hay ADB. Tocá RECONECTAR en la notificación de ADB y probá de nuevo.'
  exit 1
fi
A() { adb -s "$S" shell "$@" 2>/dev/null; }
libre() { A cat /proc/meminfo | awk '/^MemAvailable:/{printf "%d", $2/1024}'; }

if [ "$1" = abitab ]; then
  A pm enable "$ABITAB" >/dev/null
  A monkey -p "$ABITAB" -c android.intent.category.LAUNCHER 1 >/dev/null
  termux-notification --id liberar --title 'Abitab ID despierta' --content 'Cuando termines, tocá "Liberar" y vuelve a dormirse.'
  exit 0
fi

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
# Abitab: si está instalada y despierta, se duerme
if A pm list packages -e "$ABITAB" | grep -q "$ABITAB"; then
  A am force-stop "$ABITAB"
  A pm disable-user --user 0 "$ABITAB" >/dev/null && CERRADAS="$CERRADAS abitab(dormida)"
fi
sleep 3
DESPUES=$(libre)
[ -n "$CERRADAS" ] || CERRADAS=" nada (ya estaban cerradas)"
termux-notification --id liberar --title "Memoria libre: $DESPUES MB (antes $ANTES MB)" --content "Cerré:$CERRADAS"
