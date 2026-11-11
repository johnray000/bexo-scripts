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
  `telefono/movs_uy.sh` corre Prex y después Itaú (botón de los martes).
- `facturacion/midinero.py`: MiDinero desde su web, en el VPS (la app no deja leer la pantalla). Playwright + Chromium;
  `--explorar` guarda cada pantalla y los datos de la web. Necesita MIDINERO_EMAIL y MIDINERO_CLAVE en el .env.
  MiDinero bloquea IPs de fuera de Uruguay: el VPS sale por `telefono/tunel_vps.sh` (SSH del teléfono al VPS que deja
  un proxy SOCKS en 127.0.0.1:1080 del VPS; lo levanta alerta.sh cada 15 min si está VPS_SSH en el .env). Log: `~/tunel.log`.
- `cazar_p2p.py`: cazar oportunidades P2P en OKX, Bybit y Binance. Paso 1 (`--grabar okx|bybit|binance`): mientras
  hacés a mano el recorrido hasta el botón final (sin tocarlo), graba cada pantalla, cada toque y los tiempos, y deja
  un .zip en Descargas para armar el recorrido automático. No toca nada. `--enlaces APP` lista los enlaces directos.
