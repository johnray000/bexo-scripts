#!/bin/bash
# Instala y prueba la lectura de MiDinero en el VPS. Se puede correr las veces que haga falta.
#   bash <(curl -s https://raw.githubusercontent.com/johnray000/bexo-scripts/main/vps/midinero_instalar.sh)
set -e
REPO=~/bexo-scripts
VENV=~/venv-md
# Si /home no deja ejecutar programas (noexec), el entorno va en /opt
if findmnt -no OPTIONS -T "$HOME" | grep -q noexec; then
  VENV=/opt/venv-md
  sudo mkdir -p "$VENV"
  sudo chown "$USER" "$VENV"
fi
ENVF=~/.subir-ordenes.env

echo "== 1/5 Paquetes del sistema"
sudo apt-get update -qq
sudo apt-get install -y -qq python3-venv git >/dev/null

echo "== 2/5 Scripts"
if [ -d "$REPO/.git" ]; then git -C "$REPO" pull -q; else git clone -q https://github.com/johnray000/bexo-scripts.git "$REPO"; fi

echo "== 3/5 Playwright y Chromium (la primera vez tarda unos minutos)"
[ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade playwright
# El node que trae Playwright a veces queda sin permiso de ejecución
NODE=$(ls "$VENV"/lib/python3*/site-packages/playwright/driver/node)
chmod +x "$NODE" || true
if ! "$NODE" --version >/dev/null 2>&1; then
  echo "El programa de Playwright no arranca. Pasale esto a Claude:"
  ls -l "$NODE"
  findmnt -T "$NODE"
  file "$NODE" 2>/dev/null || true
  uname -m
  exit 1
fi
# Con --with-deps Playwright mismo usa sudo para los paquetes del sistema
"$VENV/bin/playwright" install --with-deps chromium

echo "== 4/5 Email y contraseña de MiDinero"
touch "$ENVF"
chmod 600 "$ENVF"
if ! grep -q '^MIDINERO_EMAIL=' "$ENVF"; then
  read -r -p "Email de MiDinero: " MD_EMAIL
  echo "MIDINERO_EMAIL=$MD_EMAIL" >> "$ENVF"
fi
if ! grep -q '^MIDINERO_CLAVE=' "$ENVF"; then
  read -r -s -p "Contraseña de MiDinero (no se ve al escribir): " MD_CLAVE
  echo
  echo "MIDINERO_CLAVE=$MD_CLAVE" >> "$ENVF"
fi
echo "Guardado en $ENVF (solo lo puede leer tu usuario)"

echo "== 5/5 Entrando a MiDinero"
"$VENV/bin/python" "$REPO/facturacion/midinero.py" --explorar

echo
echo "Listo."
