#!/data/data/com.termux/files/usr/bin/sh
# ADB al propio teléfono, después de reiniciar (Android apaga la Depuración inalámbrica y el puerto 5555).
#   adb_reconectar.sh vigilar   chequeo rápido (lo llama alerta.sh cada 15 min): si no hay ADB, pone una
#                               notificación fija con el botón RECONECTAR. Si hay, la saca.
#   adb_reconectar.sh           lo que hace el botón: abre la pantalla de Depuración inalámbrica, espera a que
#                               la prendas, se conecta, deja fijo el puerto 5555 y avisa con ✅.
# La única parte manual es prender la Depuración inalámbrica: Android no deja que un programa la prenda solo.
DIR=/data/data/com.termux/files/home/bexo-scripts
LOG=~/adb_reconectar.log

hay_adb() {
  adb devices 2>/dev/null | grep -q "device$" && return 0
  adb connect 127.0.0.1:5555 >/dev/null 2>&1
  adb devices 2>/dev/null | grep -q "device$"
}

if [ "$1" = vigilar ]; then
  if hay_adb; then
    termux-notification-remove adb-caido
  else
    termux-notification --id adb-caido --ongoing --priority high \
      --title 'ADB desconectado' --content 'Pasa después de reiniciar. Tocá RECONECTAR y prendé la Depuración inalámbrica.' \
      --button1 'RECONECTAR' --button1-action "sh $DIR/telefono/adb_reconectar.sh"
  fi
  exit 0
fi

date "+--- %d/%m %H:%M" >> "$LOG"
if hay_adb; then
  termux-notification-remove adb-caido
  termux-notification --id adb-ok --title 'ADB ✅' --content 'Ya estaba conectado.'
  exit 0
fi

termux-notification --id adb-caido --ongoing --priority high --title 'Reconectando ADB…' \
  --content 'Prendé "Depuración inalámbrica" (en la pantalla que se abrió) y volvé. Yo espero 3 minutos.'
am start -n 'com.android.settings/.Settings$WirelessDebuggingActivity' >/dev/null 2>&1 \
  || am start -a android.settings.APPLICATION_DEVELOPMENT_SETTINGS >/dev/null 2>&1
termux-vibrate -d 300

FIN=$(( $(date +%s) + 180 ))
OK=no
while [ "$(date +%s)" -lt "$FIN" ]; do
  # conectar(): mdns y, si no, busca el puerto de la Depuración inalámbrica
  if python -c "import sys; sys.path.insert(0, '$DIR'); from okx_ordenes import conectar; sys.exit(0 if conectar() else 1)" >> "$LOG" 2>&1; then
    OK=yes
    break
  fi
  sleep 5
done

if [ "$OK" != yes ]; then
  termux-notification --id adb-caido --ongoing --priority high --title 'ADB sigue desconectado ⚠️' \
    --content 'No vi la Depuración inalámbrica prendida. Prendela y tocá RECONECTAR de nuevo.' \
    --button1 'RECONECTAR' --button1-action "sh $DIR/telefono/adb_reconectar.sh"
  echo "no conectó" >> "$LOG"
  exit 1
fi

# Puerto fijo 5555: así ADB sigue andando aunque se apague la Depuración inalámbrica o cambie el wifi.
SERIAL=$(adb devices | awk '$2=="device"{print $1; exit}')
adb -s "$SERIAL" tcpip 5555 >> "$LOG" 2>&1
sleep 4
adb disconnect >/dev/null 2>&1
adb connect 127.0.0.1:5555 >> "$LOG" 2>&1
sleep 1
termux-notification-remove adb-caido
if adb devices | grep -q "127.0.0.1:5555.*device$"; then
  termux-notification --id adb-ok --title 'ADB ✅' --content 'Todo conectado. Los botones ya funcionan.'
else
  termux-notification --id adb-ok --title 'ADB ✅' --content 'Conectado por la Depuración inalámbrica (el 5555 no quedó: dejala prendida).'
fi
termux-vibrate -d 600
adb devices >> "$LOG" 2>&1
