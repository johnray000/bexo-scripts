#!/data/data/com.termux/files/usr/bin/sh
# Lee las entradas de las apps uruguayas (por ahora Prex) y las manda a la hoja "Movs UY". Lo corre el botón
# de la notificación de los martes (movs_uy_boton.sh). Lee 9 días: la semana más margen; lo repetido no se duplica.
termux-notification-remove movs-uy
cd ~/bexo-scripts && git pull -q --ff-only >> ~/movs_uy.log 2>&1
date '+--- %d/%m %H:%M' >> ~/movs_uy.log
if ! python ~/bexo-scripts/facturacion/prex.py --dias 9 >> ~/movs_uy.log 2>&1; then
  termux-notification --id prex --title 'Prex ⚠️' --content "$(tail -1 ~/movs_uy.log | cut -c1-200)"
fi
