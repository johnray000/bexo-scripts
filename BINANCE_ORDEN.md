# Pre-orden → app de Binance (estado al 15/11/2026, tarde)

Rama: `recorrido-binance` (todavía sin merge a `main`; regla del proyecto: una rama, un solo merge al final, probado).

## Qué se quiere

Con los datos de una pre-orden (Apps Script `apps-script/11_PreOrden.gs` + `9_P2P.gs`, que ya elige el anuncio por API
vía el relay del VPS y valida método, límites y "no acepto terceros"), el teléfono recorre **solo** la app de Binance
hasta **un paso antes de colocar la orden**: john tilda la casilla de términos y toca "Realizar Orden" él mismo.

## Piezas

| Archivo | Qué hace |
|---|---|
| `binance_orden.py` | El recorrido. `python binance_orden.py "LINK"`. Modos: `--grabar [SEG]` (60 s por defecto; graba mientras john hace el camino a mano, en una carpeta nueva `binance_grabacion_HHMMSS`; vibra largo al empezar, cortito por cada pantalla guardada y dos veces al terminar), `--pantalla NOMBRE`. |
| `okx_ordenes.py` | Funciones compartidas de ADB: `adb()`, `conectar()` (reintenta el 5555 ~30 s), `bloqueado()`, `tamano_pantalla()`. |
| `apps-script/9_P2P.gs` | El link del anuncio trae `&monto=<Bs>&pago=<método>` (línea con `LINK_ANUNCIO`). **Falta subirlo** (`sh ~/bexo-scripts/apps-script/subir.sh`). |
| `telefono/binance_orden.sh` | Lo que corre el botón: notificación + log en `~/binance_orden.log`. |
| `telefono/termux-url-opener` | Compartir el link "Abrir en Binance" → Termux → corre el recorrido. **Falta instalarlo** en `~/bin/`. |
| `pruebas/simular_binance.py` | Prueba sin teléfono contra las pantallas grabadas (11 casos + apodo ausente). Tiene que dar "11 de 11 casos bien". |

Pantallas grabadas (no en el repo: muestran saldos), en los archivos del proyecto `p2p/binance_app/grabacion/`:
`01` Seleccionar divisa · `02`/`03` panel Filtrar (embudo) · `04` lista P2P con filtros · `05`/`06` "Vender USDT" ·
`quiero_vender.xml` (hoja que abre el chip **Monto**, 15/11 02:13) · `seleccionar_activo.xml` (15/11 02:08).

## Cómo trabaja (reescrito el 15/11 a la tarde)

Antes era una secuencia fija de pasos y cada diferencia con la grabación lo rompía. Ahora es un bucle: lee la
pantalla, `que_es()` dice cuál de las conocidas es (`PANTALLAS`) y hace **una** acción:

| Pantalla | Acción |
|---|---|
| Binance no está al frente | cierra la cortina; actividad de inicio → monkey → link `app.binance.com` |
| inicio (animado, no se lee) | toca P2P (por texto o por posición `BOTON_P2P`) |
| p2p | en orden: pestaña Vender (una vez) · moneda si no es VES · **embudo** (siempre una vez por corrida; si no abre a la primera, lo toca de nuevo) · chip de método si no es el método · todo listo → busca el apodo (hasta 10 pantallas) y toca SU Vender |
| filtrar (panel del embudo) | apaga "Solo comerciantes Pro" si está prendido (viene prendido por defecto) · escribe el monto · Confirmar (si el teclado tapa Confirmar, lo baja) |
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
- **Ruta elegida por john: el filtro general (embudo)**, no el chip Monto: ahí se apaga "Solo comerciantes Pro". El embudo a veces no abre a la primera. Los interruptores traen `checked` en el xml (se leen bien). Ojo: en la grabación 02 Pro estaba apagado y "Solo comerciantes Verificados" prendido: confirmar con la grabación nueva.
- Con el método sin elegir, el chip dice **"Pago"**. La lista de métodos que abre **no está grabada**.
- Paquete `com.binance.dev`; actividad de inicio `com.eaas.launcher.activities.main.MainActivity`; P2P es
  `com.binance.c2c.main.FiatMainActivity`. `am start -a MAIN -c LAUNCHER <paquete>` NO la abre.
- El atributo `selected` viene siempre en false: no sirve para saber qué pestaña está activa.
- En `nodos()` solo se miran nodos del paquete de Binance: si no, lo que imprime Termux (el apodo) da falsos positivos.
- ADB: el 5555 se activa con wifi (botón RECONECTAR / `telefono/adb_reconectar.sh`) y **sigue andando con datos
  móviles**; al cambiar de red se reinicia y rechaza unos segundos (por eso los reintentos). Después de reiniciar el
  teléfono hay que pasar una vez por un wifi. No hace falta root ni Shizuku.
- john prefiere comandos de a uno, numerados, con una línea que diga qué hacen (sin `&&` ni `;`).

## Pendiente, en orden

1. **Grabar embudo + lista de métodos**: `python ~/bexo-scripts/binance_orden.py --grabar 90`, y a mano: P2P → Vender →
   embudo → apagar "Solo comerciantes Pro" → Confirmar → chip "Pago" → elegir Pago Movil (y confirmar si lo pide) →
   volver a la lista. Con eso se agrega la pantalla `metodos` y su caso al simulador.
2. Probar en el teléfono el recorrido completo con un adNo vigente:
   `python ~/bexo-scripts/binance_orden.py "https://c2c.binance.com/es-LA/adv?code=<adNo>&monto=<Bs>&pago=PagoMovil"`.
   Si se frena: deja `binance_*.png` y `.xml` en Descargas.
3. Subir el Apps Script (`subir.sh`) para que el link traiga monto y método.
4. Instalar el botón Compartir: `mkdir -p ~/bin`, `cp ~/bexo-scripts/telefono/termux-url-opener ~/bin/`,
   `chmod +x ~/bin/termux-url-opener` (revisar antes que no exista otro `termux-url-opener`).
5. Probar desde la página de la pre-orden: mantener apretado "Abrir en Binance" → Compartir → Termux.
6. Merge de `recorrido-binance` a `main` y en el teléfono `git -C ~/bexo-scripts checkout main`.
