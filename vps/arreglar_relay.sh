#!/bin/bash
# Instala el relay de Binance que no se cuelga y su vigilancia. Uso: sudo bash arreglar_relay.sh
# 1) guarda el relay actual en /opt/relay-binance/relay_binance.py.antes
# 2) pone la versión nueva (atiende varios pedidos a la vez y corta conexiones mudas a los 30 s)
# 3) agrega un control cada 5 min que lo reinicia solo si deja de responder
set -e
BASE=https://raw.githubusercontent.com/johnray000/bexo-scripts/relay-binance-no-se-cuelga/vps
cd /opt/relay-binance
cp -n relay_binance.py relay_binance.py.antes
curl -fsSL "$BASE/relay_binance.py" -o relay_binance.py.nuevo
python3 -m py_compile relay_binance.py.nuevo
mv relay_binance.py.nuevo relay_binance.py
curl -fsSL "$BASE/vigilar_relay.sh" -o /usr/local/bin/vigilar_relay.sh
chmod +x /usr/local/bin/vigilar_relay.sh
echo '*/5 * * * * root /usr/local/bin/vigilar_relay.sh' > /etc/cron.d/relay-binance
systemctl restart relay-binance
sleep 2
codigo=$(curl -s -m 10 -o /dev/null -w '%{http_code}' http://localhost:8082/anuncios)
if [ "$codigo" = "403" ]; then
  echo "LISTO: relay nuevo andando y vigilado cada 5 minutos."
else
  echo "ALGO FALLÓ (código $codigo). Vuelvo al relay anterior."
  cp relay_binance.py.antes relay_binance.py
  systemctl restart relay-binance
fi
