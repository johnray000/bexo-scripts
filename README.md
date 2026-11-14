# bexo-scripts

Scripts que corren en el teléfono (Termux). Sin claves: la key de Binance vive solo en
`~/.subir-ordenes.env` del teléfono.

- `subir_ordenes.py`: lee las órdenes P2P de Binance (solo lectura) y las manda al Apps Script.
- `telefono/subir.sh`: lo corre Termux cada 4 horas; antes baja la última versión de este repo.

Log en el teléfono: `tail -5 ~/subir.log`
- `alerta_compras.py`: alarma (notificación + voz) cuando alguien abre una orden en tu anuncio de compra;
  revisa cada 30 s. `telefono/alerta.sh` la arranca si no está corriendo (Termux lo corre cada 15 min).
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
