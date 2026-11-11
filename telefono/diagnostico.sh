#!/data/data/com.termux/files/usr/bin/sh
# Diagnóstico del bot desde el teléfono. Entra al VPS por SSH y corre vps/diagnostico.py (lo manda por la
# conexión, así el VPS no necesita git pull). Usa VPS_SSH y la clave del túnel (ver tunel_vps.sh).
#   diagnostico.sh boton      pone la notificación fija con DIAGNÓSTICO y RASTREAR (lo llama alerta.sh)
#   diagnostico.sh ya         corre todas las etapas y muestra el resultado en una notificación
#   diagnostico.sh rastrear   pide nombre o número y muestra lo último que WAHA recibió de ese cliente
#   diagnostico.sh vigilar    chequeo callado: solo avisa si algo falla (lo llama alerta.sh cada 15 min)
DIR=/data/data/com.termux/files/home/bexo-scripts
PY="$DIR/vps/diagnostico.py"
VPS=$(grep '^VPS_SSH=' ~/.subir-ordenes.env 2>/dev/null | cut -d= -f2)
LOG=~/diagnostico.log

correr() {   # $@ = argumentos para diagnostico.py
  [ -n "$VPS" ] || { echo "❌ Falta VPS_SSH en ~/.subir-ordenes.env"; return 2; }
  OUT=$(ssh -o BatchMode=yes -o ConnectTimeout=20 -o StrictHostKeyChecking=accept-new "$VPS" python3 - "$@" < "$PY" 2>&1)
  r=$?
  # 255 = no pudo entrar por SSH
  [ $r -eq 255 ] && echo "❌ Etapa 1: no pude entrar al VPS por SSH (¿VPS apagado o sin internet?)"
  echo "$OUT"
  return $r
}

mostrar() {   # $1 = id, $2 = título, $3 = texto (al expandir la notificación se ve completo)
  termux-notification --id "$1" --priority high --title "$2" --content "$3" \
    --button1 'REPETIR' --button1-action "sh $DIR/telefono/diagnostico.sh ya"
}

case "${1:-ya}" in
  boton)
    termux-notification --id diag-boton --ongoing --priority low \
      --title 'Bot WhatsApp' --content '¿No llegó una pre-orden? Revisá dónde se cortó.' \
      --button1 'DIAGNÓSTICO' --button1-action "sh $DIR/telefono/diagnostico.sh ya" \
      --button2 'RASTREAR CLIENTE' --button2-action "sh $DIR/telefono/diagnostico.sh rastrear"
    ;;
  ya)
    termux-notification --id diag-resultado --title 'Diagnóstico' --content 'Revisando… (unos 30 s)'
    SAL=$(correr)
    echo "$SAL" > ~/diagnostico_ultimo.txt
    { date '+%d/%m %H:%M ya'; echo "$SAL"; } >> "$LOG"
    mostrar diag-resultado 'Diagnóstico del bot' "$SAL"
    ;;
  rastrear)
    Q=$(termux-dialog text -t 'Rastrear cliente' -i 'Nombre o número' | python -c 'import json,re,sys; print(re.sub(r"[^\w ]", "", json.load(sys.stdin).get("text", "")).strip())')
    [ -n "$Q" ] || exit 0
    termux-notification --id diag-resultado --title "Rastreando $Q" --content 'Buscando en WAHA…'
    SAL=$(correr rastrear "$Q")
    echo "$SAL" > ~/diagnostico_ultimo.txt
    mostrar diag-resultado "Rastreo: $Q" "$SAL"
    ;;
  vigilar)
    SAL=$(correr vigilar)
    r=$?
    # Sin SSH: si el teléfono no tiene internet no es culpa del VPS, no avisar
    if [ $r -eq 255 ] && ! curl -s -m 8 -o /dev/null https://www.google.com; then exit 0; fi
    if [ -z "$SAL" ]; then rm -f ~/.diag_aviso; exit 0; fi
    { date '+%d/%m %H:%M vigilar'; echo "$SAL"; } >> "$LOG"
    PRIMERA=$(echo "$SAL" | head -1)
    # No repetir el mismo aviso cada 15 min: solo si cambió
    [ "$PRIMERA" = "$(cat ~/.diag_aviso 2>/dev/null)" ] && exit 0
    echo "$PRIMERA" > ~/.diag_aviso
    echo "$SAL" > ~/diagnostico_ultimo.txt
    mostrar diag-resultado '⚠️ Bot: algo falla' "$SAL"
    ;;
esac
