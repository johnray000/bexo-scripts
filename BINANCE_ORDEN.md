# Pre-orden → app de Binance (estado al 15/11/2026, tarde)

Rama: `recorrido-binance` (todavía sin merge a `main`; regla del proyecto: una rama, un solo merge al final, probado).

## Qué se quiere

Con los datos de una pre-orden (Apps Script `apps-script/11_PreOrden.gs` + `9_P2P.gs`, que ya elige el anuncio por API
vía el relay del VPS y valida método, límites y "no acepto terceros"), el teléfono recorre **solo** la app de Binance
hasta **un paso antes de colocar la orden**: john tilda la casilla de términos y toca "Realizar Orden" él mismo.

## Piezas

| Archivo | Qué hace |
|---|---|
| `binance_orden.py` | El recorrido. `python binance_orden.py "LINK"`. `--buscar [MONTO] [MÉTODO]` lista anuncios como la pre-orden; `--prueba [MONTO] [MÉTODO] [PUESTO]` elige uno y corre el recorrido (para probar sin pre-orden). Modos: `--grabar [SEG]` (60 s por defecto; graba mientras john hace el camino a mano, en una carpeta nueva `binance_grabacion_HHMMSS`; vibra largo al empezar, cortito por cada pantalla guardada y dos veces al terminar), `--pantalla NOMBRE`. |
| `okx_ordenes.py` | Funciones compartidas de ADB: `adb()`, `conectar()` (reintenta el 5555 ~30 s), `bloqueado()`, `tamano_pantalla()`. |
| `apps-script/9_P2P.gs` | El link del anuncio trae `&monto=<Bs>&pago=<método>` (línea con `LINK_ANUNCIO`). **Falta subirlo** (`sh ~/bexo-scripts/apps-script/subir.sh`). |
| `telefono/binance_orden.sh` | Lo que corre el botón: notificación + log en `~/binance_orden.log`. |
| `telefono/termux-url-opener` | Compartir el link "Abrir en Binance" → Termux → corre el recorrido. **Falta instalarlo** en `~/bin/`. |
| `pruebas/simular_binance.py` | Prueba sin teléfono contra las pantallas grabadas (13 casos + `que_es` de todas las pantallas + búsqueda de prueba + apodo ausente). Tiene que dar "13 de 13 casos bien". |

Pantallas grabadas (no en el repo: muestran saldos), en los archivos del proyecto `p2p/binance_app/grabacion/`:
`01` Seleccionar divisa · `02`/`03` panel Filtrar (embudo) · `04` lista P2P con filtros · `05`/`06` "Vender USDT" ·
`quiero_vender.xml` (hoja que abre el chip **Monto**, 15/11 02:13) · `seleccionar_activo.xml` (15/11 02:08) ·
de la grabación 15/11 15:27: `lista_ars_comprar.xml`, `filtrar.xml`, `lista_ves.xml`, `orden_wen2.xml` (la lista de
archivos y qué es cada uno está arriba de `pruebas/simular_binance.py`).

## Cómo trabaja (reescrito el 15/11 a la tarde)

Antes era una secuencia fija de pasos y cada diferencia con la grabación lo rompía. Ahora es un bucle: lee la
pantalla, `que_es()` dice cuál de las conocidas es (`PANTALLAS`) y hace **una** acción:

| Pantalla | Acción |
|---|---|
| Binance no está al frente | cierra la cortina; actividad de inicio → monkey → link `app.binance.com` |
| inicio (animado, no se lee) | toca P2P (por texto o por posición `BOTON_P2P`) |
| p2p | en orden: pestaña Vender (una vez) · moneda si no es VES · si el chip de método dice otro método (no "Pago" ni el tuyo) se frena · **embudo** hasta que el filtro quede verificado · todo listo → busca el apodo (hasta 10 pantallas) y toca SU Vender |
| filtrar (panel del embudo) | 1ª apertura: solo apaga "Solo anuncios comerciables" y confirma (la app descarta ese Confirmar). 2ª: deja `INTERRUPTORES` como deben (los tres apagados), comprobando cada toque, escribe el monto y confirma. Si después el chip Monto no lo muestra, se vuelve a abrir |
| monto (hoja "Quiero vender" del chip Monto) | no se usa: si quedó abierta, pone el monto y confirma, y después igual pasa por el embudo |
| divisa | toca VES |
| activo | BACK (no se elige nada: USDT ya está). Si el chip de activo no dice USDT, se frena y pide ponerlo a mano |
| cartel | Cerrar / Omitir / OK |
| orden vieja abierta | BACK |
| desconocida | una vuelta de espera; si sigue, **se frena** y guarda captura para grabarla |

Si repite la misma acción 3 veces sin avanzar, o pasan 30 vueltas, se frena. La fila de filtros se ubica por
posición (la fila debajo de la pestaña Vender: activo · monto · pago), no por resource-id.

**Orden ("Vender USDT"):** solo toca "En VES" (si el campo está en USDT) y el campo del monto (si no dice el monto).
La fila del método no se toca: si no es el tuyo, avisa. **Seguridad:** desde que toca el Vender del anunciante,
`tocar()` solo acepta toques marcados como permitidos y además rechaza cualquier texto `PROHIBIDO` (vender,
confirmar, realizar, aceptar, haz clic, todo…). Nunca coloca la orden.

## Lo que ya se sabe (no repetir)

- **La app NO abre anuncios, perfiles ni P2P por link.** Probados 25 (c2c/p2p/app.binance.com, `adv?code=`,
  `p2p/adv`, `adDetail`, `advertiserDetail`, `bnc://…`): solo `app.binance.com` y `bnc://app.binance.com` abren la app,
  y todos muestran "Este enlace no funciona". **Ir siempre por la lista.**
- El chip **Monto** de la lista abre la hoja **"Quiero vender"** (no "Filtrar"). Es lo que frenaba la corrida de las 02:13.
- **Ruta elegida por john: el filtro general (embudo)**, no el chip Monto. Al abrirlo vienen prendidos "Solo anuncios
  comerciables" y "Solo comerciantes Verificados"; "Pro" viene apagado. john apaga **los tres** (15/11 15:27). Con
  comerciables apagado aparecen anuncios "Restringido" (no se pueden tomar).
- El embudo **a veces no abre al primer toque**, y **la primera vez que se confirma el filtro la app lo descarta**: hay
  que volver a entrar y confirmar de nuevo. Por eso: 1ª apertura solo apaga "comerciables" y confirma; después se
  carga todo, y se abre hasta una apertura sin cambios (verificación).
- **Corrida 15/11 15:56**: llegó sola hasta la lista (VES, 5,000, interruptores verificados) pero no encontró a
  CloudMoneySolutions en 10 pantallas: **sin filtro de método la lista es muy larga**. Falta elegir el método (john: se
  elige en la segunda apertura, "el o los métodos"): pantalla no grabada.
- Los interruptores traen `checked` en el xml. La barra de abajo (P2P · Órdenes · Anuncios) **no siempre sale** en el
  xml: la lista se reconoce por Comprar + Vender + Rápido / Comercio por bloques.
- En ARS la fila de filtros trae además casillas "Pro" y "Nuevo usuario"; en VES no.
- **El chip "Pago" no se toca**: en la orden el método vino solo en Pago Movil (wen2, 15:27). La lista de métodos no está
  grabada. Si el chip quedó en otro método, el recorrido se frena y pide sacarlo a mano.
- El xml de una grabación se guarda unos instantes antes que su png: pueden no coincidir del todo.
- Paquete `com.binance.dev`; actividad de inicio `com.eaas.launcher.activities.main.MainActivity`; P2P es
  `com.binance.c2c.main.FiatMainActivity`. `am start -a MAIN -c LAUNCHER <paquete>` NO la abre.
- El atributo `selected` viene siempre en false: no sirve para saber qué pestaña está activa.
- En `nodos()` solo se miran nodos del paquete de Binance: si no, lo que imprime Termux (el apodo) da falsos positivos.
- ADB: el 5555 se activa con wifi (botón RECONECTAR / `telefono/adb_reconectar.sh`) y **sigue andando con datos
  móviles**; al cambiar de red se reinicia y rechaza unos segundos (por eso los reintentos). Después de reiniciar el
  teléfono hay que pasar una vez por un wifi. No hace falta root ni Shizuku.
- john prefiere comandos de a uno, numerados, con una línea que diga qué hacen (sin `&&` ni `;`).

## Pendiente, en orden

1. ~~Grabar el embudo~~ (hecho 15:27). Corrida 15:56: llegó a la lista con todo bien, pero no encontró a
   CloudMoneySolutions (anuncio de la madrugada) bajando 10 pantallas.
1b. **Grabar la parte de métodos de pago del panel Filtrar** (john: en la 2ª apertura se eligen ahí). No está grabada.
2. Probar en el teléfono el recorrido completo con un adNo vigente:
   `python ~/bexo-scripts/binance_orden.py "https://c2c.binance.com/es-LA/adv?code=<adNo>&monto=<Bs>&pago=PagoMovil"`.
   Si se frena: deja `binance_*.png` y `.xml` en Descargas.
3. Subir el Apps Script (`subir.sh`) para que el link traiga monto y método.
4. Instalar el botón Compartir: `mkdir -p ~/bin`, `cp ~/bexo-scripts/telefono/termux-url-opener ~/bin/`,
   `chmod +x ~/bin/termux-url-opener` (revisar antes que no exista otro `termux-url-opener`).
5. Probar desde la página de la pre-orden: mantener apretado "Abrir en Binance" → Compartir → Termux.
6. Merge de `recorrido-binance` a `main` y en el teléfono `git -C ~/bexo-scripts checkout main`.
