#!/data/data/com.termux/files/usr/bin/sh
# Lee las entradas de UNA app uruguaya (prex, itau u ocablue) y las manda a la hoja "Movs UY". Lo corre el botón de esa app
# (movs_uy_boton.sh). Lee 9 días: la semana más margen; lo repetido no se duplica. Al terminar muestra el botón
# de la app siguiente que esté pendiente, si hay alguna.
APP="$1"
termux-notification-remove movs-uy
cd ~/bexo-scripts && git pull -q --ff-only >> ~/movs_uy.log 2>&1
date "+--- %d/%m %H:%M $APP" >> ~/movs_uy.log
if ! python ~/bexo-scripts/facturacion/"$APP".py --dias 9 >> ~/movs_uy.log 2>&1; then
  termux-notification --id "$APP" --title "$APP ⚠️" --content "$(tail -1 ~/movs_uy.log | cut -c1-200)"
fi
sh ~/bexo-scripts/telefono/movs_uy_boton.sh
