# bexo-scripts

Scripts que corren en el teléfono (Termux). Sin claves: la key de Binance vive solo en
`~/.subir-ordenes.env` del teléfono.

- `subir_ordenes.py`: lee las órdenes P2P de Binance (solo lectura) y las manda al Apps Script.
- `telefono/subir.sh`: lo corre Termux cada 4 horas; antes baja la última versión de este repo.

Log en el teléfono: `tail -5 ~/subir.log`
- `alerta_compras.py`: alarma (notificación + voz) cuando alguien abre una orden en tu anuncio de compra;
  revisa cada 30 s. `telefono/alerta.sh` la arranca si no está corriendo (Termux lo corre cada 15 min).
  Log: `tail -5 ~/alerta.log`
