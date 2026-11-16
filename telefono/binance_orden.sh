#!/data/data/com.termux/files/usr/bin/sh
# Arma en la app de Binance la orden de la pre-orden y se frena antes de colocarla (ver binance_orden.py).
# Lo llama termux-url-opener cuando compartís el link "Abrir en Binance" con Termux. Uso: binance_orden.sh LINK
termux-notification --id binance-orden --title 'Binance' --content 'Armando la orden… no toques la pantalla'
date "+--- %d/%m %H:%M" >> ~/binance_orden.log
python ~/bexo-scripts/binance_orden.py "$1" >> ~/binance_orden.log 2>&1
