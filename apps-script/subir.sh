#!/bin/sh
# Sube el Apps Script desde GitHub a Google con un solo comando:
#   sh ~/bexo-scripts/apps-script/subir.sh
# 1) baja lo último del repo, 2) se fija que nadie haya cambiado el código a mano en el editor,
# 3) lo sube (clasp push) y 4) actualiza la implementación web para que doPost tome el cambio.
# Sin claves en el repo: el login de clasp vive en ~/.clasprc.json y el id de la implementación en ~/.bexo-implementacion.

CARPETA="$(cd "$(dirname "$0")" && pwd)"
COPIA="$HOME/.bexo-appscript-ultimo"     # copia de lo último que subimos, para detectar cambios hechos a mano
IMPL="$HOME/.bexo-implementacion"        # id de la implementación web (la URL que usan WAHA/GOWS, Termux, etc.)
TMP="${TMPDIR:-/tmp}/bexo-appscript-$$"

parar() { echo ""; echo "❌ $1"; rm -rf "$TMP"; exit 1; }

command -v clasp >/dev/null 2>&1 || parar "No encuentro clasp. Mirá apps-script/LEEME.md (paso de instalación)."
[ -f "$HOME/.clasprc.json" ] || parar "Falta loguearse a Google una vez: clasp login --no-localhost"

echo "1/4 Bajando lo último de GitHub…"
cd "$CARPETA/.." || parar "No encuentro la carpeta del repo."
git pull -q --ff-only || parar "No pude bajar de GitHub (git pull). No subí nada."
cd "$CARPETA" || exit 1

echo "2/4 Revisando que nadie haya cambiado el código en el editor de Google…"
mkdir -p "$TMP" || parar "No pude crear una carpeta temporal."
cp .clasp.json .claspignore "$TMP/"
( cd "$TMP" && clasp pull >/dev/null 2>&1 ) || parar "No pude leer el proyecto de Google (clasp pull). ¿Activaste la Apps Script API?"
rm -f "$TMP/.clasp.json" "$TMP/.claspignore"
if [ -d "$COPIA" ]; then
  REFERENCIA="$COPIA"
else
  # Primera vez: todavía no hay copia de la última subida, así que comparo contra el repo.
  REFERENCIA="$CARPETA"
fi
CAMBIOS=""
for f in "$TMP"/*; do
  n=$(basename "$f")
  cmp -s "$f" "$REFERENCIA/$n" || CAMBIOS="$CAMBIOS $n"
done
if [ -n "$CAMBIOS" ] && [ "$1" != "--pisar" ]; then
  if [ -d "$COPIA" ]; then
    echo ""
    echo "⚠️  Estos archivos se cambiaron a mano en el editor de Google desde la última subida:"
    echo "   $CAMBIOS"
    echo "   Si subo, esos cambios se pierden. Avisale a Claude para pasarlos al repo primero."
    echo "   (Si querés pisarlos igual: sh $CARPETA/subir.sh --pisar)"
    rm -rf "$TMP"; exit 1
  fi
  echo "   Primera vez: Google tiene diferencias con el repo en:$CAMBIOS"
  echo "   Es normal si ya había cambios esperando en GitHub. Si no estás seguro, cortá con Ctrl+C."
  echo "   Sigo en 10 segundos…"
  sleep 10
fi
rm -rf "$TMP"

# El repo es público: nunca subir IPs ni claves escritas en el código (van en Propiedades del script, ver 0_Config.gs).
SECRETOS=$(grep -nE "[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}|X-Api-Key\"?'?: *['\"][A-Za-z0-9_-]{12,}" *.gs 2>/dev/null)
if [ -n "$SECRETOS" ]; then
  echo "$SECRETOS"
  parar "Encontré datos privados escritos en el código (arriba). No subí nada: hay que pasarlos a Propiedades del script."
fi

echo "3/4 Subiendo el código a Google…"
clasp push --force || parar "Falló la subida (clasp push). El código en Google quedó como estaba."
rm -rf "$COPIA"; mkdir -p "$COPIA"
for f in *.gs *.html appsscript.json; do [ -f "$f" ] && cp "$f" "$COPIA/"; done

echo "4/4 Actualizando la implementación web…"
if [ ! -s "$IMPL" ]; then
  # Primera vez: busco la implementación que no es @HEAD. Si hay una sola, la guardo sola.
  IDS=$(clasp list-deployments 2>/dev/null | grep -v '@HEAD' | grep -oE 'AKfy[A-Za-z0-9_-]+' | sort -u)
  CANT=$(printf '%s\n' "$IDS" | grep -c . )
  if [ "$CANT" = "1" ]; then
    printf '%s\n' "$IDS" > "$IMPL"
  else
    echo "   Hay $CANT implementaciones y no sé cuál es la buena:"
    clasp list-deployments
    printf "   Pegá el id de la implementación web (el que empieza con AKfy…) y Enter: "
    read -r ID
    [ -n "$ID" ] || parar "Código subido, pero no actualicé la implementación (no pegaste el id)."
    printf '%s\n' "$ID" > "$IMPL"
  fi
fi
ID=$(cat "$IMPL")
VERSION_GIT=$(git -C "$CARPETA" log -1 --format='%h %s' | cut -c1-90)
clasp deploy -i "$ID" -d "$VERSION_GIT" || parar "Código subido, pero falló la nueva versión de la implementación."

echo ""
echo "✅ Listo. Código subido y nueva versión publicada ($VERSION_GIT)."
