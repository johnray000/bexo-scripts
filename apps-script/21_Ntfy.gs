// ==========================================
// 21_Ntfy.gs — Avisos a la app ntfy (con sonido, prioridad y botones) en vez de WhatsApp para lo que es tuyo.
//
// Propiedad del script: NTFY_TOPIC = el mismo nombre que ~/.bexo-ntfy en el teléfono (bexo-…). Sin ella, no hace nada.
// Temas en ntfy.sh:
//   NTFY_TOPIC         → lo que ves en la app ntfy (pre-órdenes, avances y resultados del teléfono).
//   NTFY_TOPIC + -cmd  → comandos para el teléfono: lo escucha telefono/escuchar_ntfy.py. El botón
//                        "Armar en Binance" manda ahí el link del anuncio y el teléfono arma la orden (nunca la coloca).
// ntfy.sh es un servidor público: el nombre del tema es la única protección. Nunca va un dato del cliente.
// Google NO publica directo en ntfy.sh: sus IPs son compartidas y ntfy.sh corta por cupo diario (429, 16/11). Va por
// el relay del VPS (POST /ntfy, vps/relay_binance.py), que publica con la IP propia del VPS.
// ==========================================
var NTFY_URL = 'https://ntfy.sh';

/** Publica un JSON de ntfy (topic, title, message, …) por el relay del VPS; si el relay no anda, directo. */
function publicarNtfy_(cuerpo) {
  var payload = JSON.stringify(cuerpo), r;
  try {
    var token = PropertiesService.getScriptProperties().getProperty('RELAY_TOKEN');
    r = UrlFetchApp.fetch(RELAY_URL + '/ntfy?token=' + encodeURIComponent(token),
                          { method: 'post', contentType: 'application/json', payload: payload, muteHttpExceptions: true });
    if (r.getResponseCode() === 200) return true;
    logError_('NTFY', 'relay ' + r.getResponseCode() + ' ' + r.getContentText().slice(0, 200));
  } catch (e) {
    logError_('NTFY', 'relay ' + (e.message || e));
  }
  r = UrlFetchApp.fetch(NTFY_URL, { method: 'post', contentType: 'application/json', payload: payload,
                                    muteHttpExceptions: true });   // último recurso (puede dar 429)
  if (r.getResponseCode() < 300) return true;
  logError_('NTFY', r.getResponseCode() + ' ' + r.getContentText().slice(0, 200));
  return false;
}

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
    return publicarNtfy_({ topic: CONFIG.NTFY_TOPIC, title: titulo, message: texto,
                           priority: opciones.prioridad || 3, tags: opciones.tags || [],
                           actions: opciones.acciones || [] });
  } catch (e) {
    logError_('NTFY', e.message || e);
    return false;
  }
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
  var titulo = (prueba ? 'PRUEBA · ' : '') + a.apodo + ' · ' + parametroLink_(link, 'monto') + ' Bs · ' +
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

// ---- Tarjeta por comprobante: revisás y aprobás desde la notificación ----
// Cuando un comprobante en ARS queda leído, llega a ntfy: nombre corto, monto, Bs estimados, banco, hora, últimos 4 de
// la referencia y % de lectura (ntfy.sh es público: nada de titular, teléfono ni cuenta completa).
// "✅ Armar en Binance" llama al Apps Script (doGet ?p2p=armar), que elige el anuncio EN ESE MOMENTO (frases, reservas)
// y manda el link al teléfono (tema -cmd). Así el anuncio está fresco cuando aprobás.
var ARMAR_BLOQUEO_S = 90;   // un segundo toque del mismo botón dentro de este tiempo no busca otra vez

var MAX_NOMBRE_TARJETA = 22;   // más largo rompe el título de la notificación

/** El nombre del contacto sin el prefijo "BEXO" ("BEXO Juan Pérez García" → "Juan Pérez García"), cortado con "…". */
function nombreTarjeta_(nombre) {
  var t = String(nombre || '').replace(/^\s*bexo\b[\s\-_:.·|]*/i, '').replace(/\s+/g, ' ').trim() || '?';
  return t.length > MAX_NOMBRE_TARJETA ? t.slice(0, MAX_NOMBRE_TARJETA - 1).trim() + '…' : t;
}

/** Últimos 4 caracteres de la referencia ("…1234"), o '' si no hay. */
function finReferencia_(ref) {
  var r = String(ref || '').replace(/\s/g, '');
  return r ? '…' + r.slice(-4) : '';
}

/** "1.234.567" sin decimales, con punto de miles (para el título de la tarjeta). */
function fmtEntero_(n) {
  return String(Math.round(Number(n) || 0)).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
}

function urlArmar_(id) {
  var base = PropertiesService.getScriptProperties().getProperty('WEBAPP_URL') || ScriptApp.getService().getUrl();
  return base + '?p2p=armar&id=' + encodeURIComponent(id) + '&k=' + claveNext_();
}

/**
 * Tarjeta del comprobante en ntfy. n: { id, nombre, monto (ARS), institucion, ref, hora, confianza, driveId }.
 * tasa: tasa neta (Bs por ARS). Devuelve true si ntfy la aceptó (false si ntfy no está configurado).
 */
function avisarComprobanteNtfy_(n, tasa, prueba) {
  if (!ntfyActivo_() || !n || !n.id) return false;
  var titulo = (prueba ? 'PRUEBA · ' : '') + nombreTarjeta_(n.nombre) + ' · ' + fmtEntero_(n.monto) + ' ARS → ' +
               fmtEntero_(n.monto * tasa) + ' Bs';
  var conf = Number(n.confianza);
  var detalle = [n.institucion, n.hora, finReferencia_(n.ref) && 'ref ' + finReferencia_(n.ref),
                 conf > 0 ? 'lectura ' + Math.round(conf <= 1 ? conf * 100 : conf) + ' %' : '']
                .filter(String).join(' · ');
  var acciones = [{ action: 'http', label: '✅ Armar en Binance', url: urlArmar_(n.id), method: 'GET', clear: true }];
  if (n.driveId) {
    acciones.push({ action: 'view', label: '🧾 Comprobante', url: 'https://drive.google.com/file/d/' + n.driveId + '/view' });
  }
  // un solo emoji: el de la etiqueta (ntfy lo pone delante del título)
  return avisarNtfy_(titulo, detalle || 'Comprobante leído',
                     { prioridad: 4, tags: [prueba ? 'test_tube' : 'moneybag'], acciones: acciones });
}

/**
 * Prueba manual desde el editor: manda la tarjeta (🧪) del último comprobante en ARS de Movimientos. Si tocás
 * "Armar en Binance", el teléfono arma una orden de verdad por ese monto (Realizar Orden lo tocás vos o no).
 */
function probarTarjetaNtfy() {
  var datos = hojaMovimientos_().getDataRange().getValues();
  for (var i = datos.length - 1; i >= 1; i--) {
    var d = datos[i];
    if (String(d[C.MONEDA - 1]).trim().toUpperCase() !== 'ARS' || !(Number(d[C.MONTO - 1]) > 0) || !d[C.ID - 1]) continue;
    var n = { id: String(d[C.ID - 1]), nombre: String(d[C.NOMBRE - 1] || d[C.TELEFONO - 1]), monto: Number(d[C.MONTO - 1]),
              institucion: String(d[C.INSTITUCION - 1] || ''), ref: d[C.REFERENCIA - 1], confianza: d[C.CONFIANZA - 1],
              driveId: String(d[C.DRIVE_ID - 1] || ''),
              hora: d[C.RECIBIDO - 1] instanceof Date ?
                    Utilities.formatDate(d[C.RECIBIDO - 1], Session.getScriptTimeZone(), 'HH:mm') : '' };
    Logger.log(avisarComprobanteNtfy_(n, tasaNetaActual_(), true) ? 'Tarjeta enviada: ' + n.id
                                                                   : 'No se envió (¿falta NTFY_TOPIC?)');
    return;
  }
  Logger.log('No hay comprobantes en ARS en Movimientos.');
}

/** Manda un link al tema de comandos (lo escucha telefono/escuchar_ntfy.py). */
function mandarAlTelefono_(link) {
  return publicarNtfy_({ topic: CONFIG.NTFY_TOPIC + '-cmd', message: link });
}

/**
 * El botón "✅ Armar en Binance" (doGet ?p2p=armar&id=…&k=…): busca el comprobante, elige el anuncio ahora (misma
 * lógica que la pre-orden: textoAnuncio_ → prepararOrdenP2P_) y manda el link al teléfono. Avisa en ntfy qué eligió.
 */
function armarDesdeNtfy_(id) {
  var cache = CacheService.getScriptCache();
  if (cache.get('ARMAR_' + id)) return 'ya estaba armando';
  cache.put('ARMAR_' + id, '1', ARMAR_BLOQUEO_S);
  try {
    var f = filaPorId_(hojaMovimientos_(), id);
    if (!f) {
      avisarNtfy_('No encontré el comprobante', String(id), { prioridad: 4, tags: ['warning'] });
      return 'no encontrado';
    }
    var d = f.datos;
    var nombre = String(d[C.NOMBRE - 1] || d[C.TELEFONO - 1]), monto = Number(d[C.MONTO - 1]) || 0;
    if (String(d[C.MONEDA - 1]).trim().toUpperCase() !== 'ARS' || !(monto > 0)) {
      avisarNtfy_('No es un comprobante en ARS', nombreTarjeta_(nombre), { prioridad: 4, tags: ['warning'] });
      return 'no ARS';
    }
    var texto = textoAnuncio_(monto, nombre, d[C.CUENTA - 1], false);
    var link = linkAnuncioDe_(texto);
    if (!link) {
      avisarNtfy_('Sin anuncio · ' + nombreTarjeta_(nombre), String(texto).slice(0, 300), { prioridad: 4, tags: ['warning'] });
      return 'sin anuncio';
    }
    if (!mandarAlTelefono_(link)) {
      avisarNtfy_('No pude avisarle al teléfono', 'ntfy no aceptó el comando', { prioridad: 4, tags: ['warning'] });
      return 'ntfy falló';
    }
    var u = JSON.parse(PropertiesService.getScriptProperties().getProperty('P2P_ULTIMA') || '{}');
    var reservas = String(texto).split('\n').filter(function (l) { return l.indexOf('🔁') === 0; })[0] || 'Sin reservas';
    avisarNtfy_('Armando · ' + (u.apodo || '?') + ' · ' + parametroLink_(link, 'monto') + ' Bs',
                'Precio ' + (u.precio || '?') + '\n' + reservas, { prioridad: 2, tags: ['hourglass'] });
    return 'ok';
  } catch (e) {
    logError_('NTFY_ARMAR', id + ' | ' + (e.message || e));
    avisarNtfy_('Error al armar', String(e.message || e).slice(0, 200), { prioridad: 4, tags: ['warning'] });
    return 'error';
  }
}
