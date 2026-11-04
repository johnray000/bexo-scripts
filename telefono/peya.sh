#!/data/data/com.termux/files/usr/bin/sh
# Lo corre el botón "REFRESCAR TURNOS PEYA": refresca los turnos hasta que toques PARAR (o pase 1 hora).
P=/data/data/com.termux/files/home
if [ "$1" = "parar" ]; then touch "$P/.peya_parar"; exit 0; fi
termux-wake-lock
termux-notification --id peya-estado --ongoing --title 'PeYa Rider' --content 'Refrescando turnos… no toques la pantalla' \
  --button1 'PARAR' --button1-action "sh $P/bexo-scripts/telefono/peya.sh parar"
cd ~/bexo-scripts && git pull -q --ff-only >> ~/peya.log 2>&1
python ~/bexo-scripts/peya_turnos.py >> ~/peya.log 2>&1
termux-notification --id peya-estado --title 'PeYa Rider' --content "$(tail -1 ~/peya.log | cut -c1-200)"
termux-wake-unlock
