#!/bin/bash
# =====================================================================
# prueba_carga.sh — ¿aguanta instance-1 con todo prendido a la vez?
# =====================================================================
# Mide RAM, swap, memoria de WAHA y carga cada 5 s mientras:
#   1) base (nada extra)            30 s
#   2) WAHA: lecturas de chats       ~1 min
#   3) Relay Binance: 10 consultas   ~1 min
#   4) MiDinero (--probar, no carga nada) + WAHA + Binance juntos  hasta 5 min
#   5) enfriamiento                  30 s
# Al final te dice si aguanta, el pico de memoria y si WAHA siguió WORKING.
#
# NO manda mensajes a nadie. NO cambia nada de WAHA ni del relay.
#
# Uso:
#   bash ~/prueba_carga.sh              (todo junto, con MiDinero)
#   bash ~/prueba_carga.sh sin-midinero (solo WAHA y Binance)
# =====================================================================
set -u
MIDI="$HOME/venv-md/bin/python $HOME/bexo-scripts/facturacion/midinero.py --probar --desde $(date -d '7 days ago' +%d/%m/%Y)"
[ "${1:-}" = "sin-midinero" ] && MIDI=""
LOG=~/prueba_carga_$(date +%Y%m%d_%H%M).log
FASE=/tmp/prueba_carga_fase
INICIO=$(date '+%Y-%m-%d %H:%M:%S')
CLAVE=$(grep -E 'API_KEY=' ~/waha.env | head -1 | cut -d= -f2)
RTOKEN=$(sudo grep -E '^RELAY_TOKEN=' /etc/relay-binance.env | cut -d= -f2-)
WAHA=http://localhost:8080
RELAY=http://localhost:8082
ERR_WAHA=0; ERR_RELAY=0

fase() { echo "$1" > "$FASE"; echo; echo "▶ $1"; }

# --- Monitor: una línea cada 5 s ---
monitor() {
  while [ -f "$FASE" ]; do
    mem=$(free -m | awk '/^Mem:/{u=$3;a=$7} /^Swap:/{s=$3} END{printf "%s %s %s",u,a,s}')
    wm=$(sudo docker stats --no-stream --format '{{.MemUsage}}' waha 2>/dev/null | awk '{print $1}')
    ld=$(cut -d' ' -f1 /proc/loadavg)
    set -- $mem
    echo "$(date +%H:%M:%S) usada=${1}M disponible=${2}M swap=${3}M waha=${wm:-?} carga=${ld} fase=$(cat "$FASE" 2>/dev/null)" >> "$LOG"
    sleep 5
  done
}

estado_waha() {
  curl -s -m 10 -H "X-Api-Key: $CLAVE" "$WAHA/api/sessions/default" | grep -oE '"status":"[A-Z_]+"' | head -1 | cut -d'"' -f4
}

carga_waha() {   # $1 = vueltas
  for i in $(seq 1 "$1"); do
    curl -s -m 20 -o /dev/null -w '%{http_code}' -H "X-Api-Key: $CLAVE" "$WAHA/api/default/chats?limit=100" | grep -q 200 || ERR_WAHA=$((ERR_WAHA+1))
    sleep 2
  done
}

carga_relay() {  # $1 = vueltas
  for i in $(seq 1 "$1"); do
    curl -s -m 20 -o /dev/null -w '%{http_code}' "$RELAY/anuncios?token=$RTOKEN&fiat=VES&tipo=SELL&filas=10" | grep -q 200 || ERR_RELAY=$((ERR_RELAY+1))
    sleep 4
  done
}

echo "Prueba de carga · log en $LOG"
echo "WAHA al empezar: $(estado_waha)"
fase "1-base"; monitor & MON=$!
sleep 30

fase "2-waha"; carga_waha 25
fase "3-binance"; carga_relay 12

if [ -n "$MIDI" ]; then
  fase "4-todo-junto"
  echo "  Midinero: $MIDI (máximo 5 min)"
  ( timeout 300 bash -c "$MIDI" > ~/prueba_carga_midinero.log 2>&1; echo "  Midinero terminó (código $?)" ) &
  MIDPID=$!
  while kill -0 "$MIDPID" 2>/dev/null; do carga_waha 3; carga_relay 2; done
  pkill -f chrome 2>/dev/null; pkill -f chromium 2>/dev/null   # que no quede Chrome colgado
else
  echo; echo "▶ 4-todo-junto: salteado (pediste sin-midinero)"
fi

fase "5-enfriamiento"; sleep 30
rm -f "$FASE"; wait "$MON" 2>/dev/null

# --- Resumen ---
FIN_WAHA=$(estado_waha)
read -r PICO MINDISP PICOSWAP SWAP0 <<<"$(awk '{for(i=2;i<=4;i++){split($i,a,"=");gsub("M","",a[2]);v[i]=a[2]+0}
  if(v[2]>p)p=v[2]; if(m==""||v[3]<m)m=v[3]; if(v[4]>s)s=v[4]; if(NR==1)s0=v[4]} END{print p,m,s,s0}' "$LOG")"
PICOWAHA=$(awk '{split($5,a,"=");print a[2]}' "$LOG" | sort -h | tail -1)
OOM=$(sudo journalctl -k --since "$INICIO" 2>/dev/null | grep -ciE 'out of memory|killed process')

echo
echo "================ RESULTADO ================"
echo "RAM usada, pico:          ${PICO} MB de $(free -m | awk '/^Mem:/{print $2}') MB"
echo "RAM disponible, mínimo:   ${MINDISP} MB"
echo "Swap: empezó en ${SWAP0} MB, pico ${PICOSWAP} MB"
echo "WAHA, pico de memoria:    ${PICOWAHA}"
echo "WAHA al final:            ${FIN_WAHA}   (errores en lecturas: ${ERR_WAHA})"
echo "Relay Binance, errores:   ${ERR_RELAY}"
echo "Procesos matados por memoria: ${OOM}"
if [ "${OOM:-0}" -gt 0 ] || [ "${MINDISP:-0}" -lt 100 ] || [ "$FIN_WAHA" != "WORKING" ]; then
  echo "VEREDICTO: NO AGUANTA. Midinero/Chrome no pueden correr en este servidor."
elif [ "${MINDISP:-0}" -lt 250 ] || [ $((PICOSWAP - SWAP0)) -gt 150 ]; then
  echo "VEREDICTO: JUSTO. Anda, pero sin margen: cualquier cosa más y WAHA sufre."
else
  echo "VEREDICTO: AGUANTA con margen."
fi
echo "==========================================="
echo "Ahora mandá un \"prueba\" desde otro número y fijate que llegue a Buffer."
echo "Detalle cada 5 s: $LOG"
