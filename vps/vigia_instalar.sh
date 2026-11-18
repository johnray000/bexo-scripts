#!/bin/bash
# Instala (o actualiza) el vigía de ventas P2P en el VPS. Uso: sudo bash vigia_instalar.sh [rama]
# - Baja vigia_ventas.py de GitHub a /opt/vigia-ventas (de main, o de la rama que le pases para probar)
# - Usa la key de SOLO LECTURA que ya tiene el relay (/etc/relay-binance.env): no pide claves de Binance
# - La primera vez pide el tema de ntfy (el de ~/.bexo-ntfy del teléfono). Queda en /etc/vigia-ventas.env.
# - Lo deja como servicio "vigia-ventas" (máximo 40 MB de RAM) y le pide al teléfono un sonido de prueba.
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
  echo "Pegá el tema de ntfy (en el teléfono: cat ~/.bexo-ntfy, empieza con bexo-) y Enter:"
  read -r TEMA
  case "$TEMA" in
    bexo-*) ;;
    *) echo "Ese tema no empieza con bexo-. No instalé nada."; exit 1 ;;
  esac
  umask 077
  echo "NTFY_TOPIC=$TEMA" > "$ENV"
fi

cat > /etc/systemd/system/vigia-ventas.service <<'FIN'
[Unit]
Description=Vigía de órdenes P2P (Binance → teléfono por ntfy)
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
python3 "$DIR/vigia_ventas.py" --probar && echo "LISTO: el vigía está corriendo y el teléfono sonó la venta de PRUEBA." \
  || echo "El vigía quedó instalado, pero el teléfono no contestó: te tuvo que llegar una notificación de ntfy. Mandale a Claude lo de arriba."
echo "Para ver qué hace: journalctl -u vigia-ventas -n 20"
