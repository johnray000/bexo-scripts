# Cómo funciona hoy (24/11/2026)

Guía corta para retomar. Rama `recorrido-binance` (sin merge a `main` todavía). El detalle técnico del recorrido
está en `BINANCE_ORDEN.md`; esto es lo que hay que saber para usarlo.

## 1. Un comprobante, de punta a punta

```
Cliente manda la foto por WhatsApp
  → WAHA (VPS) → Apps Script guarda en Movimientos y lee el comprobante a los 90 s
  → ntfy: TARJETA  "💸 Nombre · 70.000 ARS → 40.950 Bs"  + "→ PM Banesco …4567 · la de siempre"
        [✅ Armar en Binance]  [💬 Ok fino | 💬 Pedir cuenta]  [🧾 Comprobante]
  → tocás ✅ Armar en Binance
  → Apps Script elige el anuncio en ese momento y avisa "⌛ Armando · anunciante · Bs" (precio, método, reservas)
  → el teléfono (escuchar_ntfy.py) recibe el link y corre binance_orden.py: abre Binance, filtra, busca el
    anuncio, completa monto y método y tilda la casilla
  → ntfy: "ORDEN LISTA ✅ · tocá Realizar Orden"   o   "me frené ⚠️ (motivo)"
        [🔁 Rearmar]  [✅ FIN]
  → vos tocás "Realizar Orden" en Binance (y liberás con tu huella)
  → tocás ✅ FIN → el comprobante pasa a CONTADO en Movimientos
```

| Botón | Dónde | Qué hace |
|---|---|---|
| ✅ Armar en Binance | tarjeta | Dispara el recorrido. Queda visible: sirve para reintentar (90 s de bloqueo contra el doble toque). |
| 💬 Ok fino | tarjeta | Le manda al cliente "Ok fino te aviso apenas tenga el capturé". Una vez por operación. |
| 💬 Pedir cuenta | tarjeta, si el cliente no tiene cuenta en la Agenda | "Ok fino…" (si no lo dijiste) + "Confírmame a qué cuenta". |
| 🧾 Comprobante | tarjeta | Abre la foto en Drive. |
| 🔁 Rearmar | aviso final | Vuelve a mandar la misma orden al teléfono. Para cuando se frenó o no llegaste a Realizar Orden. |
| ✅ FIN | aviso final | Igual que "Confirmar" en la página de la pre-orden: CONTADO, APROBADA, cuenta en Destino y un uso más en la Agenda. Tocalo solo con la venta hecha. |

Lo que nunca hace solo: tocar **Realizar Orden** ni liberar (eso pide tu huella).

## 2. Qué tiene que estar andando en el teléfono

- **El que escucha ntfy** (`telefono/escuchar_ntfy.py`). Lo arranca solo `alerta.sh` cada 15 min
  (`telefono/escuchar.sh vigilar`). A mano: `sh ~/bexo-scripts/telefono/escuchar.sh` (dice si ya estaba).
  Sin él, tocar "Armar" no hace nada en el teléfono. Log: `~/escuchar_ntfy.log`; el del recorrido: `~/binance_orden.log`.
- **ADB** (la Depuración inalámbrica). Después de reiniciar el teléfono Android la apaga: aparece la notificación
  fija con **RECONECTAR** (`adb_reconectar.sh`). Sin ADB el recorrido no puede tocar la pantalla.
- **El código al día**: `git -C ~/bexo-scripts pull` (rama `recorrido-binance`:
  `git -C ~/bexo-scripts branch --show-current`).
- `~/.bexo-ntfy` con el tema de ntfy (nunca va al repo: es público).

## 3. El intake (lo que escriben los clientes antes del comprobante)

- Con cada mensaje de un cliente, a los **75 s** (cuando la tanda de 60 s se cerró) un activador de una sola vez
  (`intakePorMensaje`, igual que la lectura de 90 s) mira qué pidió y lo anota en la hoja **Intake**.
- Si la respuesta sugerida trae **tasa, cálculo, alias o disponibilidad**, llega a ntfy como borrador con
  **📤 Enviar** (un solo uso; nada sale sin tu toque). Usa tus frases: "Si tengo disponibilidad", "0.585",
  "15.600 bs", "Puedes transferir a este alias", y para más de **250.000 pesos** dos alias + "Envía mitad y mitad".
- Lo dudoso queda a mano: incidentes, divisiones, Colombia/Brasil, ruta inversa (Bs allá → pesos acá),
  respuestas en dólares.
- Tasas: la neta de la hoja Tasas; BCV y euro de ve.dolarapi.com → Yadio → `TASA_BCV`/`TASA_EURO` de la config →
  la última buena guardada (72 h). `probarTasasIntake()` en el editor muestra cada fuente.
- Alias de cobro: el orden del dashboard (`CUENTAS_PAUSADAS = ['APB']`, `CUENTAS_AL_FINAL = ['BBJ']` en `5_Dashboard.gs`).
- `processBuffer` (cada 12 h) no tiene nada que ver con el intake: dejalo como está.
- Propiedad `INTAKE_MODO`: `borrador` (por defecto), `registro` (solo la hoja) o `apagado`.
- Pendiente de confirmar: que tus mensajes aparezcan como "vos" en la hoja Intake. Si no aparecen, WAHA no manda
  tus mensajes (falta el evento `message.any`; el diagnóstico del VPS lo avisa).

Diseño completo y números de tus chats: documento "Bexo · Diseño del intake de WhatsApp" (Claude Docs).

## 4. Si algo falla

| Pasa | Qué hacer |
|---|---|
| Toqué Armar y el teléfono no hace nada | `sh ~/bexo-scripts/telefono/escuchar.sh` (¿estaba escuchando?) y mirar ADB (notificación RECONECTAR). Después 🔁 Rearmar o Armar de nuevo. |
| "me frené ⚠️" | El motivo está en el aviso y guardó captura + xml en Descargas (`binance_*.png/.xml`). Mandalos si es una pantalla nueva. 🔁 Rearmar para reintentar. |
| "No hay anuncios…" | No había anuncio con ese método y monto en ese momento: esperar y Armar de nuevo. |
| La tarjeta dice "⚠️ Sin datos de cuenta" | El cliente no tiene cuenta en la Agenda: el recorrido busca con todos los métodos. Usá 💬 Pedir cuenta. |
| No llegan tarjetas | `probarNtfy()` / `probarTarjetaNtfy()` en el editor de Apps Script (¡no tocar Ok fino en la prueba: le escribe al cliente real!). |
| Probar el recorrido sin comprobante | `python ~/bexo-scripts/binance_orden.py --prueba 5000` |

## 5. Subir cambios

1. En el teléfono: `git -C ~/bexo-scripts pull`
2. Apps Script: `bash ~/bexo-scripts/apps-script/subir.sh` (sube y publica la versión nueva del /exec)

Lo del teléfono (`binance_orden.py`, `bexo_ntfy.py`) toma efecto con el `pull`: cada orden corre el código de nuevo.

## 6. Herramientas sueltas

- `telefono/limpiar_telefono.py`: libera espacio (pruebas, capturas, fotos y documentos viejos de WhatsApp). Menú
  por números y confirmación con BORRAR; `--ver N` lista un grupo.
- `vps/exportar_chats_waha.py`: baja los chats de clientes de WAHA (para las pruebas del intake; el archivo tiene
  datos de clientes y nunca va al repo).

## 7. Pruebas (antes de pedir una prueba en el teléfono)

```
python3 pruebas/simular_binance.py <carpeta con las pantallas grabadas>   # recorrido: 21 de 21
node pruebas/probar_tarjeta_ntfy_appscript.js                             # tarjeta, Armar, FIN: 28 de 28
node pruebas/probar_intake_appscript.js [chats_waha.json.gz]              # intake: casos + repetición con tus chats
node pruebas/probar_intake_vivo_appscript.js                              # hoja Intake, borradores, activador: 29 de 29
python3 pruebas/probar_ntfy_telefono.py                                   # teléfono: escuchar, Rearmar/FIN: 13 de 13
python3 pruebas/probar_limpiar_telefono.py                                # limpiador: 12 de 12
```

## 8. Lo que se hizo del 15 al 24/11

- 15/11: recorrido reescrito como bucle que reconoce pantallas; embudo de filtros; casilla de términos; reservas.
- 16/11: ntfy en vez de compartir desde WhatsApp; tarjeta del comprobante con "Armar"; relay del VPS (429 de ntfy).
- 17/11: método desde la cuenta del cliente (no tu cuenta de cobro); cortina y libro de órdenes; intake (diseño,
  análisis de 831 conversaciones + 5.839 mensajes de WAHA, clasificador nuevo, cálculo, borradores, hoja Intake);
  dashboard APB pausada / BBJ al final; tasas BCV con respaldo; método del filtro que se desmarcaba (17:21);
  Pedir cuenta; Rearmar y FIN.
- 19/11: limpiador del teléfono.
- 24/11: merge de `main` (alarma de ventas pagadas, hora de Binance); `escuchar.sh` lo deja corriendo solo; esta guía.

## 9. Pendiente

- Varias órdenes para una misma operación ("Falta otra…", una de cada cuatro).
- Confirmar que tus mensajes llegan al intake (`message.any`).
- Automatizar "Realizar Orden" (después de unos días de prueba; liberar sigue siendo con tu huella).
- Medir la velocidad del recorrido; probar "Guardar filtro para el próximo uso".
- Merge a `main` al final, con todo probado.
