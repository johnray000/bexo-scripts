#!/data/data/com.termux/files/usr/bin/sh
# Lo corre Termux cada 4 horas: baja la última versión de los scripts y sube las órdenes P2P (Binance y Bybit).
cd ~/bexo-scripts && git pull -q --ff-only >> ~/subir.log 2>&1
python ~/bexo-scripts/subir_ordenes.py >> ~/subir.log 2>&1
grep -q '^BYBIT_KEY=' ~/.subir-ordenes.env && python ~/bexo-scripts/bybit_ordenes.py >> ~/subir.log 2>&1
