# Cómo funciona hoy (24/11/2026)

Guía corta para retomar. El teléfono y el VPS usan siempre `main` (ver CLAUDE.md). El detalle técnico del recorrido
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
- **El código al día**: `sh ~/bexo-scripts/actualizar.sh` (pasa a `main`, baja lo último y sube el Apps Script).
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
- Tus mensajes: para que el intake sepa si ya contestaste, WAHA tiene que mandarlos (evento `message.any`).
  `ssh <vps> python3 - aplicar < ~/bexo-scripts/vps/webhook_tus_mensajes.py` (sin `aplicar` solo muestra cómo está;
  `volver` lo deshace). doPost ignora un mensaje repetido por su id.
- **Cuánto acierta**: `resumenIntake()` en el editor manda a ntfy los últimos 7 días (sugerido vs lo que contestaste
  en 30 min: acierta / faltó / sobró, y qué quedó a mano). Necesita tus mensajes registrados.
- **Importante**: subí a Apps Script siempre desde la rama que tiene todo. Del 18 al 24/11 el intake estuvo apagado
  porque se subió desde `main` sin él; desde el 26/11 está todo en `main`.

**Cómo viene (revisión del 26/11):** 46 tandas registradas (17/11 y del 24 al 26/11; del 18 al 24 estuvo apagado).
Las fotos → "Ok fino" bien en todas. 8 borradores: 6 bien (disponibilidad, 40$ BCV → pesos, alias), 2 mejorables
que ya se corrigieron el 26/11 junto con la ruta inversa y la charla corta; Yape/Plin (Perú) pasa a "otra ruta".
Todavía **0 mensajes tuyos registrados**: sin eso `resumenIntake()` no puede medir el acierto (issue #57).

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

Un solo comando en el teléfono, siempre desde `main` (ver CLAUDE.md):

```
sh ~/bexo-scripts/actualizar.sh
```

Pasa el teléfono a `main`, baja lo último, reinicia el que escucha ntfy y sube el Apps Script. Las ramas son solo
para trabajar: lo que está listo se mergea a `main` ese día.

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

## 9. Pendiente (Issues de GitHub)

Lo pendiente vive en los **Issues** del repo (github.com/johnray000/bexo-scripts/issues): cada uno con su lista de
pasos. Para anotar algo nuevo: app de GitHub → bexo-scripts → Issues → New, o decíselo a Claude ("anotalo como issue").
El repo es público: nada de datos de clientes en los issues.

- #54 Recorrido más rápido (que la oferta no se vaya antes del click): primero medir cada etapa.
- #55 Pop-ups y mensajes que se atraviesan: cada uno se graba y se agrega, sin adivinar.
- #56 Varias órdenes para una misma operación ("Falta otra…").
- #57 Intake: confirmar que tus mensajes llegan (`message.any`).
- #58 Automatizar "Realizar Orden" (liberar sigue siendo con tu huella).

Estado al 24/11: el recorrido completo anda bien (`--prueba 5000 PagoMovil`) cuando no se atraviesa ningún pop-up.
