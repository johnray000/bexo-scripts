# bexo-scripts

Scripts que corren en el teléfono (Termux). Sin claves: la key de Binance vive solo en
`~/.subir-ordenes.env` del teléfono.

- `subir_ordenes.py`: lee las órdenes P2P de Binance (solo lectura) y las manda al Apps Script.
- `bybit_ordenes.py`: lo mismo para Bybit (API P2P, key de solo lectura en `BYBIT_KEY`/`BYBIT_SECRET`); las manda a la
  hoja Ordenes_P2P con Exchange = Bybit y se unen por número de orden con las del export. `--probar` no sube nada.
- `telefono/subir.sh`: lo corre Termux cada 4 horas; antes baja la última versión de este repo. Corre los dos
  (Bybit solo si está `BYBIT_KEY` en el .env).

Log en el teléfono: `tail -5 ~/subir.log`
- `alerta_compras.py`: alarma (notificación + pitidos + voz) por las órdenes de tus anuncios de Binance: compra abierta
  (pitidos cada 5 min hasta que pagues) y venta nueva (un ding-ding al 75%; si en 10 min no tocaste YA ME ENTERÉ,
  uno más al máximo y nada más); revisa cada 30 s. `telefono/alerta.sh` la arranca si no está corriendo (Termux lo corre cada 15 min).
  Log: `tail -5 ~/alerta.log`
- `facturacion/prex.py`: lee las entradas de plata de Prex (lista de Movimientos + detalle de cada una) por ADB.
  La huella la ponés vos; solo lee. `--probar` las muestra y las guarda en Descargas/prex_entradas.csv.
  `--pantalla NOMBRE` guarda la pantalla de cualquier app en Descargas y vibra al terminar.
- `facturacion/itau.py`: lo mismo para la cuenta CC Pesos de Itaú (pestaña entradas; abre cada una para el ordenante).
- `facturacion/ocablue.py`: lo mismo para la Cuenta pesos de OCA Blue (Ver movimientos; abre cada entrada para el ordenante).
- `facturacion/mercadopago.py`: lo mismo para Mercado Pago (Tu dinero → Ver todos; lee nombre y hora de la lista).
  `telefono/movs_uy.sh` corre una de estas apps por botón (los martes, de a una).
- `telefono/adb_reconectar.sh`: después de reiniciar, alerta.sh pone la notificación "ADB desconectado" con RECONECTAR; abre la Depuración inalámbrica, se conecta y deja fijo el 5555. También como acceso directo (Termux:Widget, `~/.shortcuts`).
- `facturacion/midinero.py`: MiDinero desde su web, en el VPS (la app no deja leer la pantalla). Playwright + Chromium;
  `--explorar` guarda cada pantalla y los datos de la web. Necesita MIDINERO_EMAIL y MIDINERO_CLAVE en el .env.
  MiDinero bloquea IPs de fuera de Uruguay: el VPS sale por `telefono/tunel_vps.sh` (SSH del teléfono al VPS que deja
  un proxy SOCKS en 127.0.0.1:1080 del VPS; lo levanta alerta.sh cada 15 min si está VPS_SSH en el .env). Log: `~/tunel.log`.
- `apps-script/`: el código del Apps Script del bot (INTAKE WZP GOOGLE). Se sube a Google con
  `sh ~/bexo-scripts/apps-script/subir.sh` (usa clasp; instalación y uso en `apps-script/LEEME.md`).
- `telefono/consumo.sh`: qué está consumiendo el teléfono ahora (procesador, RAM por app, temperatura, disco,
  wake locks y cada script de Termux con hace cuánto corre). Mira una vez y termina: no deja nada corriendo.
  Con ADB ve todo el teléfono; sin ADB solo Termux. `consumo.sh notif` además deja el resumen en una notificación
  (para el acceso directo de Termux:Widget). Último informe: `cat ~/consumo_ultimo.txt`.
- `telefono/liberar.sh`: notificación fija con el botón LIBERAR (la pone alerta.sh): cierra OKX, Instagram, Telegram y Abitab ID (más las de
  `~/.liberar_extra`) y avisa cuánta RAM liberó. A Abitab además le saca el permiso de correr en segundo plano. Usa ADB.
- `vps/dashboard_p2p.py` + `vps/dashboard_index.html`: la Brújula P2P (tablero P2P) (márgenes punta a punta, qué anuncio mover,
  rutas, horas, cupos UYU, ventas sin depósito). Servidor de librería estándar en el VPS, puerto 8090, con usuario y clave;
  cada 10 min pide los números al Apps Script (`apps-script/20_DashboardP2P.gs`, `?dash=1&k=DASH_TOKEN`).
  Se instala o actualiza con `sudo bash dashboard_instalar.sh`. Log: `journalctl -u dashboard-p2p -n 20`.
- `binance_orden.py` (estado y pendientes en `BINANCE_ORDEN.md`): arma en la app de Binance la orden de una pre-orden y **se frena antes de colocarla**. Recibe el
  link "Abrir en Binance" (trae adNo, monto en Bs y método), revisa ese anuncio en Binance (límites, método), abre
  P2P → Vender → USDT → VES, pone monto y método en los filtros, busca el apodo, toca su Vender y en "Vender USDT"
  escribe los Bs y elige tu método. La casilla de términos y "Realizar Orden" no las toca nunca. La app no abre
  anuncios por link: va siempre por la lista. `--grabar` guarda cada pantalla mientras hacés el recorrido a mano
  (para ajustar los toques). Log: `tail -20 ~/binance_orden.log`; capturas en Descargas (`binance_*`).
