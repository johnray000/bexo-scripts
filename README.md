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
