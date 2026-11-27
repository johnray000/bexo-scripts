#!/data/data/com.termux/files/usr/bin/sh
# Actualiza TODO lo del teléfono con un solo comando (siempre desde main):
#   sh ~/bexo-scripts/actualizar.sh
# 1) pasa el repo a main y baja lo último, 2) reinicia el que escucha ntfy para que tome el código nuevo,
# 3) sube el Apps Script (apps-script/subir.sh). Los demás scripts del teléfono ya leen de esta carpeta.
cd ~/bexo-scripts || { echo "❌ No encuentro ~/bexo-scripts"; exit 1; }
git config core.fileMode false

echo "1/3 Pasando a main y bajando lo último…"
git fetch -q origin || { echo "❌ No pude bajar de GitHub. ¿Hay internet?"; exit 1; }
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "❌ Hay archivos cambiados a mano en ~/bexo-scripts:"
  git status --short --untracked-files=no
  echo "   No toqué nada. Mandale esto a Claude."
  exit 1
fi
git checkout -q main && git pull -q --ff-only origin main || { echo "❌ No pude pasar a main. Mandale esto a Claude."; exit 1; }
echo "   Teléfono en main: $(git log -1 --format='%h %s' | cut -c1-70)"

echo "2/3 Reiniciando el que escucha ntfy…"
[ -f ~/.escuchar_ntfy.pid ] && kill "$(cat ~/.escuchar_ntfy.pid)" 2>/dev/null
command -v pkill >/dev/null 2>&1 && pkill -f "telefono/escuchar_ntfy.py" 2>/dev/null
rm -f ~/.escuchar_ntfy.pid
sleep 1
sh ~/bexo-scripts/telefono/escuchar.sh

echo "3/3 Subiendo el Apps Script…"
sh ~/bexo-scripts/apps-script/subir.sh
