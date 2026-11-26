# bexo-scripts

Todo lo que mueve el negocio de john: comprobantes por WhatsApp, órdenes P2P (Binance, Bybit, OKX, Bitget),
la Brújula P2P y el intake de clientes. El radar de spreads vive en otro repo (`johnray000/radar-p2p`).

## Dónde corre cada cosa

| Carpeta | Corre en | Cómo se actualiza |
|---|---|---|
| `apps-script/` | Google Apps Script (planilla "WZP INTAKE docker google cloud") | `sh ~/bexo-scripts/actualizar.sh` en el teléfono |
| `telefono/`, `*.py` de la raíz | Teléfono (Termux + ADB) | el mismo `actualizar.sh` (los scripts leen de `~/bexo-scripts`) |
| `vps/dashboard_*`, `vps/revisar_brujula.py` | VPS, servicio `dashboard-p2p` (Brújula P2P, puerto 8091) | `curl -fsSL https://raw.githubusercontent.com/johnray000/bexo-scripts/main/vps/actualizar_brujula.sh \| sudo bash` |
| `vps/` (resto) | VPS (WAHA, relay, cron) | cada script dice cómo se instala |

## Reglas

- **El teléfono y el VPS usan siempre `main`.** Las ramas son solo para trabajar. Cuando algo está listo
  para que john lo pruebe, se mergea a `main` ese día y se le pasa un único comando (`actualizar.sh` o
  `actualizar_brujula.sh`). Nunca pedirle que cambie de rama ni que instale desde otra rama.
- El repo es público: ningún dato privado en el código (van en Propiedades del script, ver `apps-script/0_Config.gs`).
- Comandos para john: numerados, uno por bloque, con una línea de qué hace, sin `&&` ni `;`.
- Textos en español rioplatense. john no quiere avisos de error que no sepa qué hacer con ellos.

## Para seguir leyendo

- `COMO_FUNCIONA.md`: el recorrido de un comprobante, los botones y qué tiene que estar andando.
- `pruebas/BRUJULA_REVISION.md`: cómo revisar los números de la Brújula (`node pruebas/probar_brujula.js`).
- `apps-script/LEEME.md`: clasp y `subir.sh`.
