// ==========================================
// 21_Ntfy.gs — Avisos a la app ntfy (con sonido, prioridad y botones) en vez de WhatsApp para lo que es tuyo.
//
// Propiedad del script: NTFY_TOPIC = el mismo nombre que ~/.bexo-ntfy en el teléfono (bexo-…). Sin ella, no hace nada.
// Temas en ntfy.sh:
//   NTFY_TOPIC         → lo que ves en la app ntfy (pre-órdenes, avances y resultados del teléfono).
//   NTFY_TOPIC + -cmd  → comandos para el teléfono: lo escucha telefono/escuchar_ntfy.py. El botón
//                        "Armar en Binance" manda ahí el link del anuncio y el teléfono arma la orden (nunca la coloca).
// ntfy.sh es un servidor público: el nombre del tema es la única protección. Nunca va un dato del cliente.
// ==========================================
var NTFY_URL = 'https://ntfy.sh';

function ntfyActivo_() {
  return !!CONFIG.NTFY_TOPIC;
}

/**
 * Publica en NTFY_TOPIC. opciones: { prioridad: 1-5 (3 normal, 4 alta), tags: ['moneybag'], acciones: [...] }.
 * Devuelve true si ntfy lo aceptó.
 */
function avisarNtfy_(titulo, texto, opciones) {
  if (!ntfyActivo_()) return false;
  opciones = opciones || {};
  try {
    var r = UrlFetchApp.fetch(NTFY_URL, {
      method: 'post', contentType: 'application/json', muteHttpExceptions: true,
      payload: JSON.stringify({ topic: CONFIG.NTFY_TOPIC, title: titulo, message: texto,
                                priority: opciones.prioridad || 3, tags: opciones.tags || [],
                                actions: opciones.acciones || [] })
    });
    var c = r.getResponseCode();
    if (c >= 200 && c < 300) return true;
    logError_('NTFY', c + ' ' + r.getContentText().slice(0, 200));
  } catch (e) {
    logError_('NTFY', e.message || e);
  }
  return false;
}

/** Botón "Armar en Binance": manda el link al tema de comandos; el teléfono lo escucha y arma la orden. */
function botonArmarNtfy_(link) {
  return { action: 'http', label: 'Armar en Binance', url: NTFY_URL + '/' + CONFIG.NTFY_TOPIC + '-cmd',
           method: 'POST', body: link, clear: false };
}

/** Un parámetro del link del anuncio (monto, pago, alt). '' si no está. */
function parametroLink_(link, nombre) {
  var m = String(link).match(new RegExp('[?&]' + nombre + '=([^&]*)'));
  return m ? decodeURIComponent(m[1]) : '';
}

/**
 * La pre-orden en ntfy: "💸 apodo · monto Bs · método", precio, reservas y el botón para armarla en el teléfono.
 * a: { apodo, precio } del anuncio elegido; lineaReservas: la de lineaAlternativas_ (9_P2P.gs) o ''.
 */
function avisarPreOrdenNtfy_(link, a, lineaReservas, prueba) {
  if (!link || !a) return false;
  var titulo = (prueba ? '🧪 PRUEBA · ' : '💸 ') + a.apodo + ' · ' + parametroLink_(link, 'monto') + ' Bs · ' +
               parametroLink_(link, 'pago');
  var texto = ['Precio ' + a.precio, lineaReservas || 'Sin reservas',
               'Tocá "Armar en Binance": el teléfono arma la orden y tilda la casilla; Realizar Orden lo tocás vos.']
              .join('\n');
  return avisarNtfy_(titulo, texto, { prioridad: 4, tags: [prueba ? 'test_tube' : 'moneybag'],
                                      acciones: [botonArmarNtfy_(link)] });
}

/** Prueba manual desde el editor: manda un aviso simple (sin botón) para ver que llega a la app. */
function probarNtfy() {
  Logger.log(ntfyActivo_() ? (avisarNtfy_('Prueba desde Google', 'Si ves esto, el Apps Script llega a ntfy.')
                              ? 'Enviado a ntfy.' : 'ntfy NO lo aceptó: mirá Errores.')
                           : 'Falta la propiedad NTFY_TOPIC (el contenido de ~/.bexo-ntfy en el teléfono).');
}
