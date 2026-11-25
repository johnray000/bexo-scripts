#!/data/data/com.termux/files/usr/bin/sh
# Qué está consumiendo el teléfono AHORA. No deja nada corriendo: mira una vez y termina.
#   consumo.sh          informe en la terminal (también queda en ~/consumo_ultimo.txt)
#   consumo.sh notif    lo mismo, más un resumen en una notificación (para el acceso directo de Termux:Widget)
# Con ADB (puerto 5555, ver adb_reconectar.sh) ve TODO el teléfono; sin ADB solo ve lo de Termux.
# Para mirarlo en vivo (se corta con Ctrl+C):  adb -s 127.0.0.1:5555 shell top -d 3 -m 15
# Para cerrar una app que está consumiendo:     adb -s 127.0.0.1:5555 shell am force-stop NOMBRE.DE.LA.APP
OUT=~/consumo_ultimo.txt

elegir_serial() {   # prefiere el 5555; si no, cualquier ADB conectado
  adb devices 2>/dev/null | grep -q "^127.0.0.1:5555[[:space:]]*device$" || adb connect 127.0.0.1:5555 >/dev/null 2>&1
  L=$(adb devices 2>/dev/null | awk '$2=="device"{print $1}')
  if echo "$L" | grep -qx "127.0.0.1:5555"; then echo 127.0.0.1:5555; else echo "$L" | head -1; fi
}
SERIAL=""
command -v adb >/dev/null 2>&1 && SERIAL=$(elegir_serial)
A() { adb -s "$SERIAL" shell "$@" 2>/dev/null; }

informe() {
  echo "=== Consumo del teléfono $(date '+%d/%m %H:%M')"
  if [ -z "$SERIAL" ]; then
    echo "⚠️ Sin ADB: solo veo lo de Termux. Para ver todo el teléfono: sh ~/bexo-scripts/telefono/adb_reconectar.sh"
  else
    echo
    echo "--- PROCESADOR: lo que más usó en los últimos minutos (100% = un núcleo entero)"
    A dumpsys cpuinfo | awk '/^Load:/{print "Carga promedio (1/5/15 min): "$2" "$4" "$6} /^ *[0-9.]+% [0-9]+\//{if(n++<10)print} /TOTAL/{print}' | cut -c1-100

    echo
    echo "--- MEMORIA RAM"
    A cat /proc/meminfo | awk '/^MemTotal:/{t=$2} /^MemAvailable:/{a=$2} /^SwapTotal:/{st=$2} /^SwapFree:/{sf=$2}
      END{printf "Libre: %d MB de %d MB (%d%%)\n", a/1024, t/1024, (t?a*100/t:0); if(st) printf "Swap usada: %d MB de %d MB\n", (st-sf)/1024, st/1024}'
    echo "Apps que más RAM ocupan:"
    A dumpsys meminfo | awk '/by process:/{f=1;next} f&&/^ *$/{exit} f&&n++<12{v=$1; gsub(/[,K:]/,"",v); printf "  %5d MB  %s\n", v/1024, $2}'

    echo
    echo "--- BATERÍA Y TEMPERATURA"
    A dumpsys battery | awk '/^ *level:/{print "Carga: "$2"%"} /^ *temperature:/{t=$2/10; printf "Temperatura batería: %.1f °C%s\n", t, (t>=40?"  ⚠️ caliente: Android frena el procesador para enfriarlo":"")}'
    A dumpsys thermalservice | awk -F': ' '/Thermal Status/{s=$2+0; split("ninguno,leve,moderado,fuerte,crítico,emergencia,apagado",n,","); print "Freno por calor: "n[s+1]; exit}'

    echo
    echo "--- ALMACENAMIENTO"
    A df /data | awk 'NR==2{u=$5+0; g=$2; if(g ~ /^[0-9]+$/) g=sprintf("%.0f GB", g/1048576); printf "Usado: %s de %s%s\n", $5, g, (u>=90?"  ⚠️ casi lleno: eso frena el teléfono":"")}'

    echo
    echo "--- QUIÉN NO DEJA DORMIR AL TELÉFONO (wake locks activos)"
    A dumpsys power | sed -n '/Wake Locks: size=/,/^ *$/p' | head -12 | cut -c1-110
  fi

  echo
  echo "--- TERMUX (tus scripts). 'Desde' = hace cuánto que corre"
  ps -A -o pid,etime,rss,args 2>/dev/null | awk -v yo=$$ '
    NR==1 || $1==yo || / ps -A/ || /awk -v yo/ || /consumo\.sh|consumo_ultimo/ || $4 ~ /^\[/ {next}
    {
      cmd=""; for(i=4;i<=NF;i++) cmd=cmd" "$i
      q="otro"
      if (cmd ~ /alerta_compras/)       q="Alarma de compras y ventas Binance y Bybit: SIEMPRE, pregunta cada 2 min"
      else if (cmd ~ /while true/)      q="Vigilante del túnel: SIEMPRE, casi no gasta (espera)"
      else if (cmd ~ /ssh -N -R 1080/)  q="Túnel al VPS (MiDinero): SIEMPRE, conexión abierta"
      else if (cmd ~ /diagnostico/)     q="Diagnóstico del bot: cada 15 min, dura segundos"
      else if (cmd ~ /peya/)            q="Caza PeYa: solo mientras cazás"
      else if (cmd ~ /okx_ordenes|subir_ordenes|prex|itau|ocablue|mercadopago/) q="Lectura de órdenes/movimientos: solo mientras corre"
      else if (cmd ~ /(^| |\/)(node|clasp)( |$)/)      q="node / clasp: solo mientras lo usás"
      else if (cmd ~ /adb .*fork-server|adb -L/) q="Servidor ADB: queda abierto, casi no gasta"
      else if (cmd ~ /sshd/)            q="Servidor SSH de Termux"
      else if (cmd ~ /^ *(-?bash|-?sh|login)( |$)/ || cmd ~ /termux/) q="Terminal de Termux"
      else if (cmd ~ /^ *sleep/)        q="(pausa de algún script)"
      tot+=$3
      printf "  %6.1f MB  desde %-11s %s\n     %s\n", $3/1024, $2, q, substr(cmd,2,90)
    }
    END{printf "Total Termux: %.0f MB de RAM\n", tot/1024}'
}

informe | tee "$OUT"

if [ "$1" = notif ]; then
  RES=$(awk '
    /^--- PROCESADOR/{s="cpu"} /^--- MEMORIA/{s="ram"} /^--- TERMUX/{s="tx"}
    s=="cpu" && /^ *[0-9.]+% [0-9]+\// && c++<3 {split($2,a,"/"); sub(/:$/,"",a[2]); cpu=cpu (cpu?", ":"") $1" "a[2]}
    /^Libre:/{ram=$2" MB libres"}
    s=="ram" && /^ +[0-9]+ MB/ && r++<3 {top=top (top?", ":"") $3" "$1"MB"}
    /^Temperatura/{tmp=$3" °C"}
    /^Usado:/{dis=$2" lleno"}
    /^Total Termux/{tx=$3" MB"}
    /Sin ADB/{noadb=1}
    END{
      if(noadb) print "Sin ADB: solo veo Termux ("tx"). Tocá RECONECTAR en la notificación de ADB.";
      else printf "CPU: %s\nRAM: %s. Más pesadas: %s\nBatería %s · Disco %s · Termux %s", cpu, ram, top, tmp, dis, tx
    }' "$OUT")
  termux-notification --id consumo --title "Consumo del teléfono $(date +%H:%M)" --content "$RES" \
    --button1 'MIRAR DE NUEVO' --button1-action "sh /data/data/com.termux/files/home/bexo-scripts/telefono/consumo.sh notif"
fi
