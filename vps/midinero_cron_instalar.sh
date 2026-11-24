#!/bin/bash
# Deja el cron de MiDinero en lunes, miércoles y viernes a las 13:00 UTC (10:00 en Uruguay), sin editar a mano.
# Saca cualquier línea vieja de midinero_cron.sh y pone la nueva. Se puede correr las veces que sea.
# Desde el teléfono lo corre telefono/vps_midinero_cron.sh (por SSH).
if [ ! -f ~/bexo-scripts/vps/midinero_cron.sh ]; then
  echo "❌ En este usuario ($(whoami)) no está ~/bexo-scripts: el cron de MiDinero es de otro usuario del VPS"
  exit 1
fi
git -C ~/bexo-scripts pull -q
LINEA='0 13 * * 1,3,5 bash ~/bexo-scripts/vps/midinero_cron.sh >> ~/midinero.log 2>&1'
TMP=$(mktemp)
crontab -l 2>/dev/null | grep -v 'midinero_cron.sh' > "$TMP"
echo "$LINEA" >> "$TMP"
crontab "$TMP"
rm -f "$TMP"
echo "✅ Cron de MiDinero:"
crontab -l | grep midinero_cron.sh
