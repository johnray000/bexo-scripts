# Pre-orden → app de Binance (estado al 15/11/2026)

Rama: `recorrido-binance` (todavía sin merge a `main`; regla del proyecto: una rama, un solo merge al final, probado).

## Qué se quiere

Con los datos de una pre-orden (Apps Script `apps-script/11_PreOrden.gs` + `9_P2P.gs`, que ya elige el anuncio por API
vía el relay del VPS y valida método, límites y "no acepto terceros"), el teléfono recorre **solo** la app de Binance
hasta **un paso antes de colocar la orden**: john tilda la casilla de términos y toca "Realizar Orden" él mismo.

## Piezas

| Archivo | Qué hace |
|---|---|
| `binance_orden.py` | El recorrido. `python binance_orden.py "LINK"`. Modos: `--grabar` (graba pantallas mientras john hace el camino a mano), `--pantalla NOMBRE`. |
| `okx_ordenes.py` | Funciones compartidas de ADB: `adb()`, `conectar()` (reintenta el 5555 ~30 s), `bloqueado()`, `tamano_pantalla()`. |
| `apps-script/9_P2P.gs` | El link del anuncio ahora trae `&monto=<Bs>&pago=<método>` (línea con `LINK_ANUNCIO`). **Falta subirlo** (`sh ~/bexo-scripts/apps-script/subir.sh`). |
| `telefono/binance_orden.sh` | Lo que corre el botón: notificación + log en `~/binance_orden.log`. |
| `telefono/termux-url-opener` | Compartir el link "Abrir en Binance" → Termux → corre el recorrido. **Falta instalarlo** en `~/bin/`. |
| `pruebas/simular_binance.py` | Prueba sin teléfono contra las pantallas grabadas. |

Pantallas grabadas (xml + png) del 15/11: en los archivos del proyecto, `p2p/binance_app/grabacion/`
(no en el repo: muestran saldos). 01 = Seleccionar divisa, 02/03 = panel Filtrar, 04 = portada P2P con filtros,
05/06 = "Vender USDT". `orden_banesco.png` = la misma pantalla con el método en Banesco.

## El recorrido (binance_orden.py)

1. Lee del link `code` (adNo), `monto` (Bs) y `pago` (ej. `PagoMovil`). Pide el detalle del anuncio a
   `p2p.binance.com/bapi/c2c/v2/public/c2c/adv/selected-adv/<adNo>` (desde el teléfono responde; desde Google no):
   apodo, precio, límites, métodos. Si el monto no entra o el método no está, se frena sin abrir nada.
2. `traer_binance`: abre la app (actividad de inicio → monkey → link `https://app.binance.com/es-LA`, que siempre
   abre la app aunque muestre "Este enlace no funciona"). Cierra la cortina de notificaciones.
3. `abrir_p2p`: el inicio de Binance es animado y uiautomator se cuelga ahí: si no se lee en 8 s, toca P2P por
   posición (`BOTON_P2P` = 15,2 % del ancho, 30,5 % del alto). Sabe que llegó si ve Comprar + Vender + Anuncios.
4. `preparar_lista`: pestaña Vender (el "Vender" de más arriba). **USDT y la moneda son menús**: solo se tocan si
   no dicen ya USDT / VES. Moneda distinta (ARS, UYU…) → "Seleccionar divisa" → botón VES. Monto: el filtro con
   resource-id `tv_amount` abre "Filtrar" → EditText → Confirmar. Método: el filtro a la derecha del monto (dice
   "Pago" o el método); si no es el de la pre-orden, lo toca y elige el método (**esa lista no está grabada**).
5. `buscar_en_lista`: busca el apodo (baja hasta 10 pantallas) y toca el "Vender" de su tarjeta.
6. `completar_orden` (pantalla "Vender USDT"): "En VES", el monto (EditText; ya viene con el monto del filtro),
   la fila del método entre "Vendes" e "Info. del anunciante" (si no es el método, la toca y elige). Devuelve si
   monto y método quedaron bien. Guarda captura `binance_listo_*.png`.

**Seguridad:** desde que toca el Vender del anunciante, `Toques.xy` se niega a tocar cualquier texto que cumpla
`PROHIBIDO` (vender, confirmar, realizar, aceptar, haz clic, todo…). Nunca coloca la orden.

## Lo que ya se sabe (no repetir)

- **La app NO abre anuncios, perfiles ni P2P por link.** Probados 25 (c2c/p2p/app.binance.com, `adv?code=`,
  `p2p/adv`, `adDetail`, `advertiserDetail`, `bnc://…`): solo `app.binance.com` y `bnc://app.binance.com` abren la app,
  y todos muestran "Este enlace no funciona". La app ya no deja compartir anuncios; el perfil se comparte como link
  corto `binance.com/…/qr/dplk…` que no se puede armar. **Ir siempre por la lista.**
- Paquete `com.binance.dev`; actividad de inicio `com.eaas.launcher.activities.main.MainActivity`; P2P es
  `com.binance.c2c.main.FiatMainActivity`. `am start -a MAIN -c LAUNCHER <paquete>` NO la abre.
- En `nodos()` solo se miran nodos del paquete de Binance: si no, lo que imprime Termux (el apodo) da falsos positivos.
- ADB: el 5555 se activa con wifi (botón RECONECTAR / `telefono/adb_reconectar.sh`) y **sigue andando con datos
  móviles**; al cambiar de red se reinicia y rechaza unos segundos (por eso los reintentos). Después de reiniciar el
  teléfono hay que pasar una vez por un wifi. No hace falta root ni Shizuku.
- john prefiere comandos de a uno, numerados, con una línea que diga qué hacen (sin `&&` ni `;`).

## Pendiente, en orden

1. **Probar en el teléfono el recorrido completo** (la última corrida llegó a P2P → Vender y se trabó tocando el
   menú USDT; ya está corregido y pasa la simulación):
   `python ~/bexo-scripts/binance_orden.py "https://c2c.binance.com/es-LA/adv?code=<adNo>&monto=<Bs>&pago=PagoMovil"`
   con un adNo vigente (sacarlo de una pre-orden de hoy). Si se frena: deja `binance_*.png` y `.xml` en Descargas.
2. Si el método del filtro no es el de la pre-orden, ver la lista de métodos (no grabada) y ajustar.
3. Subir el Apps Script (`subir.sh`) para que el link traiga monto y método.
4. Instalar el botón Compartir: `mkdir -p ~/bin`, `cp ~/bexo-scripts/telefono/termux-url-opener ~/bin/`,
   `chmod +x ~/bin/termux-url-opener` (revisar antes que no exista otro `termux-url-opener`).
5. Probar desde la página de la pre-orden: mantener apretado "Abrir en Binance" → Compartir → Termux.
6. Merge de `recorrido-binance` a `main` y en el teléfono `git -C ~/bexo-scripts checkout main`.
