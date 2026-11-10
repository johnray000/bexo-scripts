#!/bin/bash
# Lo corre cron en el VPS los martes a las 13:00 UTC (10:00 en Uruguay): lee las entradas de MiDinero de los
# últimos 9 días (por el túnel del teléfono) y las manda a "Movs UY". Si falla, el control de los miércoles
# de 17_MovimientosUY.gs avisa por WhatsApp cuando pasen 8 días sin lectura. Log: ~/midinero.log
git -C ~/bexo-scripts pull -q
echo "== $(date '+%d/%m/%Y %H:%M')"
~/venv-md/bin/python ~/bexo-scripts/facturacion/midinero.py
