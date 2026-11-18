#!/bin/bash
# Instala (o actualiza) el vigía de la alarma del teléfono en el VPS. Uso: sudo bash vigia_instalar.sh [rama]
# - Baja vigia_ventas.py de GitHub a /opt/vigia-ventas (de main, o de la rama que le pases para probar)
# - Actualiza el relay (/opt/relay-binance) para que reciba el latido del teléfono (/latido) y lo reinicia
# - La primera vez pide el tema de ntfy (el de ~/.bexo-ntfy del teléfono). Queda en /etc/vigia-ventas.env.
# - Lo deja como servicio "vigia-ventas" (máximo 40 MB de RAM) y manda un aviso de prueba a ntfy.
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

# Relay con /latido (guarda el anterior en relay_binance.py.antes por si hay que volver)
cd /opt/relay-binance
cp -n relay_binance.py relay_binance.py.antes
curl -fsSL "$BASE/relay_binance.py" -o relay_binance.py.nuevo
python3 -m py_compile relay_binance.py.nuevo
mv relay_binance.py.nuevo relay_binance.py
systemctl restart relay-binance
sleep 2
codigo=$(curl -s -m 10 -o /dev/null -w '%{http_code}' http://localhost:8082/anuncios)
if [ "$codigo" != "403" ]; then
  echo "El relay nuevo no responde (código $codigo). Vuelvo al anterior y no sigo."
  cp relay_binance.py.antes relay_binance.py
  systemctl restart relay-binance
  exit 1
fi
cd - > /dev/null

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
Description=Vigía de la alarma del teléfono (latido → ntfy)
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
python3 "$DIR/vigia_ventas.py" --probar && echo "LISTO: el vigía está corriendo. Te tuvo que llegar un aviso de PRUEBA en ntfy." \
  || echo "Algo falló con el aviso de prueba. Mandale a Claude lo de arriba."
echo ""
echo "Para el teléfono, este es el RELAY_TOKEN (no lo mandes por chat: copialo y pegalo vos en Termux):"
grep '^RELAY_TOKEN=' /etc/relay-binance.env
echo "Para ver qué hace: journalctl -u vigia-ventas -n 20"
