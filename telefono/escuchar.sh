#!/data/data/com.termux/files/usr/bin/sh
# Deja corriendo telefono/escuchar_ntfy.py (lo que recibe el botón "Armar en Binance" y arma la orden).
#   sh ~/bexo-scripts/telefono/escuchar.sh           a mano: lo arranca si no está y dice cómo quedó
#   sh ~/bexo-scripts/telefono/escuchar.sh vigilar   lo llama alerta.sh cada 15 min: lo arranca si no está, sin hablar
# Nunca arranca un segundo: dos a la vez armarían cada orden dos veces. Log en ~/escuchar_ntfy.log.
PID=~/.escuchar_ntfy.pid
corriendo() {
  if command -v pgrep >/dev/null 2>&1; then
    pgrep -f "telefono/escuchar_ntfy.py" >/dev/null 2>&1 && return 0
  fi
  [ -f "$PID" ] && kill -0 "$(cat "$PID")" 2>/dev/null
}
if corriendo; then
  [ "$1" = vigilar ] || echo "✅ Ya está escuchando ntfy (el botón Armar en Binance funciona)."
  exit 0
fi
if [ ! -f ~/.bexo-ntfy ]; then
  [ "$1" = vigilar ] || echo "⚠️ Falta ~/.bexo-ntfy (el tema de ntfy): sin eso no puede escuchar."
  exit 1
fi
termux-wake-lock
nohup python ~/bexo-scripts/telefono/escuchar_ntfy.py >> ~/escuchar_ntfy.log 2>&1 &
echo $! > "$PID"
[ "$1" = vigilar ] || echo "✅ Escuchando ntfy. Log: ~/escuchar_ntfy.log"
