# Revisión de la Brújula P2P

Tres capas. Ninguna manda avisos: se miran cuando algo no cierra o cada tanto.

## 1. Pruebas del cálculo (sin Google, en cualquier máquina)

    node pruebas/probar_brujula.js

Corre `apps-script/20_DashboardP2P.gs` y `22_RevisionBrujula.gs` con órdenes de mentira. Cada caso es algo que ya
falló en producción (anuncio viejo de Binance como "Revisar", OKX sin moneda, compra OKX repetida, subida atrasada,
anuncios OKX apagados sin motivo, etc.). Correrlas antes de subir cualquier cambio del tablero.

## 2. Revisión de los datos reales (hoja `Revision_Brujula`)

Cada vez que la Brújula pide los números (cada 10 min), el Apps Script revisa Ordenes_P2P y deja el resultado en la
hoja `Revision_Brujula` de la planilla "WZP INTAKE docker google cloud" y en `data.json` del VPS (campo `revision`).
Claude la lee con el conector de Google Sheets (`Revision_Brujula!A1:C40`). Cada fila:

- `ok`: comprobado y bien.
- `ojo`: puede estar bien pero no se puede comprobar (falta un dato o es un supuesto).
- `mal`: error en los datos o en el cálculo; el detalle dice en qué fila de Ordenes_P2P mirar.

Pruebas: subidas al día (Binance, Bybit, OKX), órdenes sin moneda, n° de orden repetido, OKX repetida entre API y app,
monto = cantidad × precio, fechas futuras, Binance sin n° de anuncio, lo que debés recalculado por otro camino,
cuántas filas de Binance tienen precio en vivo, y la última orden de cada exchange (para comparar con lo que john sabe).

## 3. Revisión del VPS (la corre john y pega la salida)

    sudo python3 /opt/dashboard-p2p/revisar_brujula.py

Muestra si el servicio anda, si el botón del teléfono está configurado, de cuándo es el último cálculo, qué dijo
Binance, las subidas, la revisión de datos y de dónde sale el precio de cada anuncio. Solo lee; no muestra la clave.
