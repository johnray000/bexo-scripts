#!/data/data/com.termux/files/usr/bin/sh
# Notificación fija con los botones "Actualizar historial P2P" y "Refrescar turnos PeYa". La vuelve a poner alerta.sh cada 15 min si la borraste.
termux-notification --id historial-p2p --ongoing --priority low \
  --title 'Historial P2P' --content 'Tocá el botón para leer tus órdenes de OKX y mandarlas a la planilla' \
  --button1 'ACTUALIZAR HISTORIAL P2P' \
  --button1-action 'sh /data/data/com.termux/files/home/bexo-scripts/telefono/okx.sh ya' \
  --button2 'REFRESCAR TURNOS PEYA' \
  --button2-action 'sh /data/data/com.termux/files/home/bexo-scripts/telefono/peya.sh'
