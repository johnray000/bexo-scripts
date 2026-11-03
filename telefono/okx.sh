#!/data/data/com.termux/files/usr/bin/sh
# Lo corre Termux cada 2 horas. Lee OKX como mucho 1 vez cada 10 horas: si el teléfono estaba bloqueado
# o sin wifi, prueba de nuevo en la próxima vuelta.
STAMP=~/.okx_ultima
if [ -f "$STAMP" ] && [ $(( $(date +%s) - $(cat "$STAMP") )) -lt 36000 ]; then exit 0; fi
cd ~/bexo-scripts && git pull -q --ff-only >> ~/okx.log 2>&1
python ~/bexo-scripts/okx_ordenes.py >> ~/okx.log 2>&1 && date +%s > "$STAMP"
