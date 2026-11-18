#!/bin/bash
# Instala (o actualiza) el vigía de ventas P2P en el VPS. Uso: sudo bash vigia_instalar.sh [rama]
# - Baja vigia_ventas.py de GitHub a /opt/vigia-ventas (de main, o de la rama que le pases para probar)
# - Usa la key de SOLO LECTURA que ya tiene el relay (/etc/relay-binance.env): no pide claves de Binance
# - La primera vez pide el token del bot de Telegram y el tema de ntfy (los dos opcionales, al menos uno).
#   Quedan en /etc/vigia-ventas.env (no está en GitHub).
# - Lo deja como servicio "vigia-ventas" (máximo 40 MB de RAM) y manda un mensaje de prueba.
# Volver a correrlo actualiza el código y no toca la configuración.
set -e
RAMA=${1:-main}
BASE=https://raw.githubusercontent.com/johnray000/bexo-scripts/$RAMA/vps
DIR=/opt/vigia-ventas
ENV=/etc/vigia-ventas.env

[ "$(id -u)" = "0" ] || { echo "Correlo con sudo: sudo bash vigia_instalar.sh"; exit 1; }
[ -f /etc/relay-binance.env ] || { echo "No encuentro /etc/relay-binance.env (la key del relay). Avisale a Claude."; exit 1; }

mkdir -p "$DIR"
curl -fsSL "$BASE/vigia_ventas.py" -o "$DIR/vigia_ventas.py.nuevo"
python3 -m py_compile "$DIR/vigia_ventas.py.nuevo"
mv "$DIR/vigia_ventas.py.nuevo" "$DIR/vigia_ventas.py"

if [ ! -f "$ENV" ]; then
  echo ""
  echo "TELEGRAM. Pegá el token que te dio @BotFather (algo como 123456:ABC...) y Enter."
  echo "Si no querés Telegram, Enter vacío."
  read -r TOKEN
  CHAT=""
  if [ -n "$TOKEN" ]; then
    echo ""
    echo "Ahora abrí tu bot en Telegram, mandale cualquier mensaje (por ejemplo: hola) y después tocá Enter acá."
    read -r _
    CHAT=$(curl -fsS "https://api.telegram.org/bot$TOKEN/getUpdates" | python3 -c '
import json, sys
r = json.load(sys.stdin).get("result") or []
ids = [u["message"]["chat"]["id"] for u in r if "message" in u]
print(ids[-1] if ids else "")') || CHAT=""
    if [ -z "$CHAT" ]; then
      echo "No vi tu mensaje al bot (o el token está mal). No instalé nada; probá de nuevo."
      exit 1
    fi
    echo "Listo, tu chat es $CHAT."
  fi
  echo ""
  echo "NTFY. Pegá el tema de ntfy (en el teléfono: cat ~/.bexo-ntfy, empieza con bexo-) y Enter."
  echo "Si no querés ntfy, Enter vacío."
  read -r TEMA
  if [ -z "$TOKEN" ] && [ -z "$TEMA" ]; then
    echo "Sin Telegram ni ntfy no hay a dónde avisar. No instalé nada."
    exit 1
  fi
  umask 077
  cat > "$ENV" <<FIN
TELEGRAM_TOKEN=$TOKEN
TELEGRAM_CHAT=$CHAT
NTFY_TOPIC=$TEMA
FIN
fi

cat > /etc/systemd/system/vigia-ventas.service <<'FIN'
[Unit]
Description=Vigía de ventas P2P (Binance → Telegram/ntfy)
After=network-online.target

[Service]
EnvironmentFile=/etc/relay-binance.env
EnvironmentFile=/etc/vigia-ventas.env
ExecStart=/usr/bin/python3 /opt/vigia-ventas/vigia_ventas.py
User=nobody
Group=nogroup
Restart=always
RestartSec=10
MemoryMax=40M

[Install]
WantedBy=multi-user.target
FIN
systemctl daemon-reload
systemctl enable -q vigia-ventas
systemctl restart vigia-ventas

echo ""
python3 "$DIR/vigia_ventas.py" --probar && echo "LISTO: el vigía está corriendo. Te tuvo que llegar un mensaje de PRUEBA." \
  || echo "El vigía quedó instalado pero el mensaje de prueba no llegó. Mandale a Claude lo de arriba."
echo "Para ver qué hace: journalctl -u vigia-ventas -n 20"
