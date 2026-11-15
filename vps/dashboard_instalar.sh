#!/bin/bash
# Instala (o actualiza) el tablero P2P en el VPS. Uso: sudo bash dashboard_instalar.sh
# - Baja dashboard_p2p.py y la página de GitHub a /opt/dashboard-p2p
# - La primera vez pide la dirección del Apps Script (la escribe configurarTableroP2P en el registro)
#   y crea usuario y clave para entrar. Quedan en /etc/dashboard-p2p.env (no está en GitHub).
# - Lo deja como servicio "dashboard-p2p" (máximo 60 MB de RAM) en el primer puerto libre desde 8090.
# Volver a correrlo actualiza el código y no toca la clave.
set -e
BASE=https://raw.githubusercontent.com/johnray000/bexo-scripts/main/vps
DIR=/opt/dashboard-p2p
ENV=/etc/dashboard-p2p.env

[ "$(id -u)" = "0" ] || { echo "Correlo con sudo: sudo bash dashboard_instalar.sh"; exit 1; }

mkdir -p "$DIR"
curl -fsSL "$BASE/dashboard_p2p.py" -o "$DIR/dashboard_p2p.py.nuevo"
curl -fsSL "$BASE/dashboard_index.html" -o "$DIR/index.html.nuevo"
python3 -m py_compile "$DIR/dashboard_p2p.py.nuevo"
mv "$DIR/dashboard_p2p.py.nuevo" "$DIR/dashboard_p2p.py"
mv "$DIR/index.html.nuevo" "$DIR/index.html"
chown -R nobody:nogroup "$DIR"

if [ ! -f "$ENV" ]; then
  # Busca el primer puerto libre entre 8090 y 8099
  PUERTO=""
  for p in 8090 8091 8092 8093 8094 8095 8096 8097 8098 8099; do
    if ! ss -ltn | grep -q ":$p "; then PUERTO=$p; break; fi
  done
  [ -n "$PUERTO" ] || { echo "Los puertos 8090 a 8099 están todos ocupados. Avisale a Claude."; exit 1; }
  echo "Uso el puerto $PUERTO."
  echo ""
  echo "Pegá la dirección que escribió configurarTableroP2P en el registro del Apps Script"
  echo "(empieza con https://script.google.com y termina con ?dash=1&k=...) y Enter:"
  read -r URL
  case "$URL" in
    https://script.google.com/*dash=1*k=*) ;;
    *) echo "Esa dirección no parece la correcta. No instalé nada."; exit 1 ;;
  esac
  CLAVE=$(python3 -c "import secrets; print(secrets.token_urlsafe(12))")
  umask 077
  cat > "$ENV" <<EOF
DASH_URL="$URL"
DASH_USUARIO=john
DASH_CLAVE=$CLAVE
DASH_PUERTO=$PUERTO
EOF
  NUEVA=1
fi

cat > /etc/systemd/system/dashboard-p2p.service <<'EOF'
[Unit]
Description=Tablero P2P
After=network-online.target

[Service]
EnvironmentFile=/etc/dashboard-p2p.env
ExecStart=/usr/bin/python3 /opt/dashboard-p2p/dashboard_p2p.py
User=nobody
Group=nogroup
Restart=always
RestartSec=10
MemoryMax=60M
NoNewPrivileges=yes
ProtectSystem=strict
ReadWritePaths=/opt/dashboard-p2p
ProtectHome=yes
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable -q dashboard-p2p
systemctl restart dashboard-p2p

# El primer pedido al Apps Script tarda unos segundos
. "$ENV"
for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
  sleep 5
  RESP=$(curl -s -m 10 -u "$DASH_USUARIO:$DASH_CLAVE" "http://localhost:$DASH_PUERTO/data.json" || true)
  echo "$RESP" | grep -q '"servidor"' && break
done
if echo "$RESP" | grep -q '"ok": true'; then
  echo ""
  echo "LISTO: el tablero está andando y ya trajo los números de la planilla."
elif echo "$RESP" | grep -q '"servidor"'; then
  echo ""
  echo "El tablero anda pero NO pudo leer la planilla:"
  echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['servidor'].get('error',''))"
  echo "Revisá que hayas subido el Apps Script (subir.sh) y la dirección pegada. Log: journalctl -u dashboard-p2p -n 20"
else
  echo "ALGO FALLÓ: el tablero no responde. Log: journalctl -u dashboard-p2p -n 20"
  exit 1
fi
IP=$(curl -s -m 5 -H 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip || echo "IP-DEL-VPS")
echo ""
echo "Dirección:  http://$IP:$DASH_PUERTO"
echo "Usuario:    $DASH_USUARIO"
if [ -n "$NUEVA" ]; then
  echo ""
  echo "IMPORTANTE: en el firewall de Google Cloud abrí el puerto TCP $DASH_PUERTO."
fi
if [ -n "$NUEVA" ]; then
  echo "Clave:      $DASH_CLAVE   (guardala; para verla de nuevo: sudo cat $ENV)"
fi
echo "Memoria:    $(systemctl show dashboard-p2p -p MemoryCurrent --value | awk '{printf "%.0f MB", $1/1048576}')"
