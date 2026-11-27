#!/data/data/com.termux/files/usr/bin/sh
# Lee las órdenes de la app de OKX y las manda a la planilla. Lo corre el botón de la notificación (con "ya").
# Sin "ya" (activador automático) lee como mucho 1 vez cada 10 horas.
STAMP=~/.okx_ultima
if [ "$1" != "ya" ] && [ -f "$STAMP" ] && [ $(( $(date +%s) - $(cat "$STAMP") )) -lt 36000 ]; then exit 0; fi
termux-notification --id historial-p2p-estado --title 'Historial P2P' --content 'Leyendo OKX… no toques la pantalla'
cd ~/bexo-scripts && git pull -q --ff-only >> ~/okx.log 2>&1
if python ~/bexo-scripts/okx_ordenes.py >> ~/okx.log 2>&1; then
  date +%s > "$STAMP"
  if tail -1 ~/okx.log | grep -q ' 0 órdenes OKX'; then
    # No es un error, pero tampoco "todo subido": no leyó ninguna orden (o no hubo en esos días, o no pudo leer la app).
    termux-notification --id historial-p2p-estado --title 'Historial P2P: no leí ninguna orden' --content 'Si operaste en OKX esos días, abrí OKX en Órdenes > Completadas y probá de nuevo.'
  else
    termux-notification --id historial-p2p-estado --title 'Historial P2P ✅' --content "$(tail -1 ~/okx.log | cut -c1-200)"
  fi
else
  termux-notification --id historial-p2p-estado --title 'Historial P2P ⚠️' --content "$(tail -1 ~/okx.log | cut -c1-200)"
fi
