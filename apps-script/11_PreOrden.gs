// ==========================================
// 11_PreOrden.gs — PRE-ÓRDENES P2P DESDE LOS COMPROBANTES (caso 1 a 1)
//
// 1. Cuando entra un comprobante de un cliente, doPost (2_Recepcion.gs) agenda UNA lectura para dentro de 90 s
//    (agendarLecturaRapida_). Esa lectura pasa el OCR y, para cada LEIDO en ARS sin pre-orden, manda UN mensaje con todo:
//    Bs a enviar, los datos de pago que mandó el cliente (Agenda) y el anuncio de Binance ya buscado, más el link "Revisar".
//    Los comprobantes en Bs a tus cuentas de Venezuela (MJ, MR, PMJ, PMR) mandan otra pre-orden, simple: cuánto
//    transferir en ARS (13_CuentasVes.gs).
//    Si no llega ningún comprobante, no corre nada. Respaldo: refrescarTodo (cada 2 h), con horario (9 a 23; de noche 0, 4 y 8).
// 2. El link abre una página con los datos (COPIAR), el comprobante, el monto corregible y tres botones:
//    "Buscar otro anuncio" (si el de WhatsApp ya no está; no cambia la planilla), "Confirmar" (CONTADO + Destino + Agenda)
//    y, ya confirmada, "Deshacer y corregir" (vuelve a LEIDO). Buscar otro anuncio funciona también después de confirmar.
//
// El estado vive en la columna "Orden P2P" de Movimientos (se crea sola al final):
//    vacío → ENVIADA → APROBADA.
// Interruptor: casilla K3 del Dashboard (por defecto APAGADO).
// Usa de otros archivos: hojaMovimientos_, C, E_LEID, E_CONT, linkDrive_ (4), tasaNetaActual_,
// prepararOrdenP2P_, fmtM_, claveNext_ (9), sendWhatsAppMessage_ (3), MI_TELEFONO, logError_, procesarPendientes (4),
// LINK_ANUNCIO, metodosParaCuenta_ (9), leerAgenda_, cuentasDelCliente_, usarCuentaAgenda_, desusarCuentaAgenda_,
// leerDatosPago_, lineasCuenta_, lineasDeCampos_, textoCuenta_, mayusculaInicial_, AG_AGENDADA (10), BUFFER_SHEET (2), completarVes_, esCuentaVe_,
// tasaBrutaPara_, leerTasasBrutas_, arsDeBs_, mensajePreOrdenVes_, paginaPreOrdenVes_, recalcularArsFila_,
// COL_TASA_VES, COL_ARS_VES (13).
// ==========================================
var PROP_PREORDEN = 'PREORDEN_ACTIVA';
var COL_ORDEN = 'Orden P2P';
var COL_DESTINO = 'Destino';   // a qué cuenta de Venezuela fue el pago (10_AgendaCuentas.gs)
var PRE_ENVIADA = 'ENVIADA';
// Mientras se arma y manda: si el envío se corta (relay colgado, WAHA caído, Apps Script cortado por tiempo),
// la fila queda en ENVIANDO y se reintenta sola a los PRE_REINTENTO_MIN minutos, hasta PRE_MAX_INTENTOS veces.
var PRE_ENVIANDO = 'ENVIANDO';
var PRE_REINTENTO_MIN = 15;
var PRE_MAX_INTENTOS = 3;
var PRE_APROBADA = 'APROBADA';
var MAX_PREORDENES_POR_VUELTA = 5;

function preOrdenActiva_() {
  return PropertiesService.getScriptProperties().getProperty(PROP_PREORDEN) === 'SI';
}

// La llama alEditar() cuando tocás K3 en el Dashboard
function fijarPreOrden_(activa) {
  PropertiesService.getScriptProperties().setProperty(PROP_PREORDEN, activa ? 'SI' : 'NO');
  var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Dashboard');
  if (sh) etiquetaPreOrden_(sh, activa);
}

// Texto al lado de la casilla K3 (lo usa también construirDashboard)
function etiquetaPreOrden_(sh, activa) {
  sh.getRange('L3').setValue(activa ? 'pre-órdenes ON' : 'pre-órdenes OFF')
    .setFontSize(8).setFontColor(activa ? '#1f9d55' : '#c0392b');
}

/** Número de la columna "Orden P2P". Si no existe, la crea al final de la fila 1. */
function colOrden_(sh) {
  return colEncabezado_(sh, COL_ORDEN);
}

/** Número de la columna con ese encabezado. Si no existe, la crea al final de la fila 1. */
function colEncabezado_(sh, nombre) {
  var ult = sh.getLastColumn();
  var head = sh.getRange(1, 1, 1, ult).getValues()[0].map(function (h) { return String(h).trim(); });
  var i = head.indexOf(nombre);
  if (i !== -1) return i + 1;
  sh.getRange(1, ult + 1).setValue(nombre).setFontWeight('bold');
  return ult + 1;
}

/** Busca la fila de un comprobante por su ID (MOV-...). Devuelve {fila, datos} o null. */
function filaPorId_(sh, id) {
  var datos = sh.getDataRange().getValues();
  for (var i = 1; i < datos.length; i++) {
    if (String(datos[i][C.ID - 1]) === String(id)) return { fila: i + 1, datos: datos[i] };
  }
  return null;
}

function linkPreOrden_(id) {
  var base = PropertiesService.getScriptProperties().getProperty('WEBAPP_URL') || ScriptApp.getService().getUrl();
  return base + '?p2p=pre&mov=' + encodeURIComponent(id) + '&k=' + claveNext_();
}

/** De 9 a 23 todas las horas; de noche solo a las 0, 4 y 8. */
function horaDePreOrden_() {
  var h = Number(Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'H'));
  return (h >= 9 && h < 23) || h % 4 === 0;
}

// ---- Pre-orden al llegar el comprobante (sin revisar cada hora) ----
var ESPERA_LECTURA_SEG = 90;   // junta las fotos que el cliente manda seguidas en una sola vuelta
var PROP_LECTURA_AGENDADA = 'LECTURA_AGENDADA';

/** La llama doPost (2_Recepcion.gs) cuando entra un comprobante de un cliente. Rápido: no llama a DeepSeek. */
function agendarLecturaRapida_() {
  try {
    if (!preOrdenActiva_()) return;
    var props = PropertiesService.getScriptProperties();
    var ya = Number(props.getProperty(PROP_LECTURA_AGENDADA)) || 0;
    // Fotos que llegan juntas (varios doPost en el mismo segundo): agenda solo la primera
    if (Date.now() - ya < 60 * 1000) return;
    // Ya hay una lectura en camino: esta foto entra en esa. Se mira el activador de verdad, no solo la marca,
    // así una marca vieja (lectura que no llegó a correr) no deja fotos sin leer.
    var hay = ScriptApp.getProjectTriggers().some(function (t) { return t.getHandlerFunction() === 'lecturaPorComprobante'; });
    if (hay) return;
    // Con la regla vieja (10 min) esta foto se salteaba: queda anotado para confirmar que era esto
    if (Date.now() - ya < 10 * 60 * 1000) logError_('AGENDAR_LECTURA', 'Marca sin activador (' + Math.round((Date.now() - ya) / 1000) + ' s): se agenda igual');
    props.setProperty(PROP_LECTURA_AGENDADA, String(Date.now()));
    ScriptApp.newTrigger('lecturaPorComprobante').timeBased().after(ESPERA_LECTURA_SEG * 1000).create();
  } catch (e) {
    logError_('AGENDAR_LECTURA', e.message || e);
  }
}

/** La corre el activador de una sola vez que crea agendarLecturaRapida_. Se borra a sí mismo. */
function lecturaPorComprobante() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'lecturaPorComprobante') ScriptApp.deleteTrigger(t);
  });
  PropertiesService.getScriptProperties().deleteProperty(PROP_LECTURA_AGENDADA);   // desde acá, una foto nueva agenda otra
  try { procesarPendientes(); } catch (e) { logError_('LECTURA_EVENTO', e.message || e); }
  try { completarVes_(); } catch (e) { logError_('VES', e.message || e); }   // Bs: cuenta, Tasa y ARS (13_CuentasVes.gs)
  enviarPreOrdenes(true);   // llegó un comprobante: sale al toque, sin mirar el horario
}

/** Para correr a mano desde el editor: manda las pendientes sin mirar el horario. */
function enviarPreOrdenesYa() { enviarPreOrdenes(true); }

/** La llaman lecturaPorComprobante (siempre = true, sin horario) y refrescarTodo (con horario). */
function enviarPreOrdenes(siempre) {
  if (!preOrdenActiva_() || (siempre !== true && !horaDePreOrden_())) return;
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(10000)) return;
  var nuevas = [];
  try {
    var sh = hojaMovimientos_();
    if (sh.getLastRow() < 2) return;
    var col = colOrden_(sh);
    var colT = colEncabezado_(sh, COL_TASA_VES), colA = colEncabezado_(sh, COL_ARS_VES);
    var datos = sh.getRange(1, 1, sh.getLastRow(), Math.max(sh.getLastColumn(), col, colT, colA)).getValues();
    var tasas = null;
    for (var i = 1; i < datos.length && nuevas.length < MAX_PREORDENES_POR_VUELTA; i++) {
      var d = datos[i];
      if (String(d[C.ESTADO - 1]).trim() !== E_LEID) continue;
      var moneda = String(d[C.MONEDA - 1]).trim().toUpperCase();
      var ves = moneda === 'VES' && esCuentaVe_(d[C.CUENTA - 1]);   // Bs a tus cuentas de Venezuela (13_CuentasVes.gs)
      if (moneda !== 'ARS' && !ves) continue;
      var marca = String(d[col - 1]).trim();
      var intento = marca === '' ? 1 : intentoTrabado_(marca);   // 0 = ya enviada o todavía en camino
      if (!intento) continue;
      if (intento > PRE_MAX_INTENTOS) {
        sh.getRange(i + 1, col).setValue('NO ENVIADA: ver Debug_Errores');
        logError_('PREORDEN', d[C.ID - 1] + ' | no se pudo mandar en ' + PRE_MAX_INTENTOS + ' intentos');
        continue;
      }
      var monto = Number(d[C.MONTO - 1]) || 0;
      if (!(monto > 0)) continue;
      var n = { id: String(d[C.ID - 1]), nombre: String(d[C.NOMBRE - 1] || d[C.TELEFONO - 1]),
                monto: monto, cuenta: d[C.CUENTA - 1] };
      if (ves) {
        var tv = Number(d[colT - 1]) || tasaBrutaPara_(d[C.RECIBIDO - 1], tasas = tasas || leerTasasBrutas_());
        if (!tv) continue;   // sin tasa no se puede calcular; queda para la próxima vuelta
        n.ves = true; n.cuentaMov = String(d[C.CUENTA - 1]); n.tasa = tv;
        n.ars = Number(d[colA - 1]) || arsDeBs_(monto, tv);
      }
      nuevas.push(n);
      // Se marca ENVIANDO antes de buscar el anuncio (así no se repite en cada vuelta) y ENVIADA recién cuando
      // WhatsApp confirma. Si el envío se corta a la mitad, se reintenta solo (intentoTrabado_).
      sh.getRange(i + 1, col).setValue(PRE_ENVIANDO + ' ' + Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'dd/MM HH:mm') + ' #' + intento);
    }
    SpreadsheetApp.flush();
  } catch (e) {
    logError_('PREORDEN', e.message || e);
  } finally {
    lock.releaseLock();
  }
  // Fuera del candado: buscar el anuncio tarda y no tiene que frenar la recepción ni la Agenda
  if (!nuevas.length) return;
  var tasa = tasaNetaActual_();
  var agenda = leerAgenda_();
  nuevas.forEach(function (n) {
    try {
      var ok;
      if (n.ves) {
        ok = whatsAppConfirmado_(mensajePreOrdenVes_(n));   // sin anuncio ni datos
      } else {
        var msj = mensajePreOrden_(n, tasa, agenda);
        ok = whatsAppConfirmado_(msj.orden);
        if (ok && msj.datos) whatsAppConfirmado_(msj.datos);
      }
      if (ok) marcarEnviada_(n.id);   // si no, queda ENVIANDO y se reintenta sola
    } catch (e) {
      logError_('PREORDEN', n.id + ' | ' + (e.message || e));
    }
  });
}

/** Número de intento si la fila quedó trabada en ENVIANDO hace más de PRE_REINTENTO_MIN minutos; si no, 0. */
function intentoTrabado_(marca) {
  var m = /^ENVIANDO (\d\d)\/(\d\d) (\d\d):(\d\d)(?: #(\d+))?/.exec(marca);
  if (!m) return 0;
  var ahora = new Date();
  var t = new Date(ahora.getFullYear(), Number(m[2]) - 1, Number(m[1]), Number(m[3]), Number(m[4]));
  if (t > ahora) t.setFullYear(t.getFullYear() - 1);   // marca de diciembre leída en enero
  if (ahora - t < PRE_REINTENTO_MIN * 60000) return 0;
  return (Number(m[5]) || 1) + 1;
}

/** Manda un WhatsApp a MI_TELEFONO y devuelve true solo si WAHA lo aceptó. */
function whatsAppConfirmado_(texto) {
  try {
    var r = UrlFetchApp.fetch(WAHA_URL + '/api/sendText', {
      method: 'post', contentType: 'application/json', muteHttpExceptions: true,
      headers: { 'X-Api-Key': WAHA_API_KEY },
      payload: JSON.stringify({ session: 'default', chatId: MI_TELEFONO + '@c.us', text: texto })
    });
    var c = r.getResponseCode();
    if (c >= 200 && c < 300) return true;
    logError_('PREORDEN_WHATSAPP', c + ' ' + r.getContentText().slice(0, 200));
  } catch (e) {
    logError_('PREORDEN_WHATSAPP', e.message || e);
  }
  return false;
}

/** Pasa la fila de ENVIANDO a ENVIADA. Busca por ID porque las filas nuevas entran arriba y corren las demás. */
function marcarEnviada_(id) {
  var sh = hojaMovimientos_();
  var col = colOrden_(sh);
  var ids = sh.getRange(2, C.ID, sh.getLastRow() - 1, 1).getValues();
  for (var i = 0; i < ids.length; i++) {
    if (String(ids[i][0]) !== String(id)) continue;
    var celda = sh.getRange(i + 2, col);
    if (/^ENVIANDO/.test(String(celda.getValue()))) {
      celda.setValue(PRE_ENVIADA + ' ' + Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'dd/MM HH:mm'));
    }
    return;
  }
}

/** Pre-orden y orden en un solo mensaje (Bs, estado de los datos y el anuncio de Binance) + los datos limpios aparte. */
function mensajePreOrden_(n, tasa, agenda) {
  var ctas = cuentasDelCliente_(n.nombre, agenda);
  var sug = cuentaSugerida_(n.nombre, ctas);   // la que mandó ahora, la que nombró en el chat o la de siempre
  var cuenta = sug.cuenta;
  var lineas = [
    '*' + n.nombre + '* · Enviar *' + fmtM_(n.monto * tasa, 0, true) + ' Bs*',
    'recibido ' + fmtM_(n.monto, 0) + ' ARS × ' + fmtM_(tasa, 3) + ' · ' + (n.cuenta || '?'),
    ''
  ];
  var mas = ctas.otras.length - (sug.motivo === 'reciente' ? 0 : 1);
  if (sug.motivo === 'reciente') {
    lineas.push('Datos: ' + (cuenta.estado === AG_AGENDADA ? 'agendados ✅' : 'nuevos 🆕') + ' (van en el mensaje de abajo)');
  } else if (sug.motivo === 'nombre') {
    lineas.push('Datos: no mandó; pidió a ' + mayusculaInicial_(cuenta.titular) + ', de la Agenda 📒 (abajo)');
  } else if (cuenta) {
    lineas.push('Datos: no mandó; los de siempre 📒 (' + cuenta.veces + (cuenta.veces === 1 ? ' vez' : ' veces') + ', abajo)');
  } else {
    lineas.push('Datos: no mandó todavía');
  }
  if (cuenta && mas > 0) lineas.push('Tiene ' + mas + ' cuenta' + (mas === 1 ? '' : 's') + ' más en la página');
  lineas.push('');
  // El link de la página va primero: desde ahí se abre Binance y, con Atrás, se vuelve a Confirmar
  lineas.splice(3, 0, '👉 Abrir, ir a Binance y confirmar:', linkPreOrden_(n.id), '');
  lineas.push(textoAnuncio_(n.monto, n.nombre, cuenta));
  // Los datos van en un segundo mensaje, limpios, para copiarlos de un toque
  return { orden: lineas.join('\n'), datos: cuenta ? lineasCuenta_(cuenta).join('\n') : '' };
}

var MAX_CUENTAS_A_LA_VISTA = 3;   // en la página, desde la 4.ª cuenta van en un desplegable
var HORAS_CHAT_TITULAR = 48;      // mensajes del cliente donde se busca el nombre del titular ("pasale a María Parica")

/**
 * Cuenta a proponer: 1) la que mandó ahora (reciente); 2) si no, una de la Agenda cuyo titular nombró en el chat
 * de las últimas 48 h (hoja Buffer); 3) si no, la de siempre (la más usada). {cuenta, motivo}.
 */
function cuentaSugerida_(cliente, ctas) {
  if (ctas.reciente) return { cuenta: ctas.reciente, motivo: 'reciente' };
  if (!ctas.otras.length) return { cuenta: null, motivo: '' };
  var txt = ' ' + normTxt_(textoChatCliente_(cliente)) + ' ';
  for (var i = 0; txt.trim() && i < ctas.otras.length; i++) {
    var w = normTxt_(ctas.otras[i].titular).split(' ').filter(String);
    // nombre y apellido (primera y última palabra del titular) tienen que aparecer en lo que escribió
    if (w.length >= 2 && txt.indexOf(' ' + w[0] + ' ') !== -1 && txt.indexOf(' ' + w[w.length - 1] + ' ') !== -1) {
      return { cuenta: ctas.otras[i], motivo: 'nombre' };
    }
  }
  return { cuenta: ctas.otras[0], motivo: 'siempre' };   // otras viene ordenada por veces usada
}

/** Lo que escribió el cliente en las últimas HORAS_CHAT_TITULAR horas (hoja Buffer de 2_Recepcion.gs). */
function textoChatCliente_(cliente) {
  try {
    var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(BUFFER_SHEET);
    if (!sh || sh.getLastRow() < 2) return '';
    var limite = Date.now() - HORAS_CHAT_TITULAR * 3600000;
    return sh.getRange(2, 1, sh.getLastRow() - 1, 4).getValues().filter(function (f) {
      return String(f[1]) === String(cliente) && f[3] instanceof Date && f[3].getTime() > limite;
    }).map(function (f) { return String(f[2]); }).join(' ');
  } catch (e) {
    logError_('PREORDEN_CHAT', e.message || e);
    return '';
  }
}

function normTxt_(t) {
  return String(t || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-zñ0-9]+/g, ' ').trim();
}

/**
 * El anuncio de Binance para ese monto y esa cuenta (texto de prepararOrdenP2P_ en 9_P2P.gs).
 * conEncabezado = false le saca las 2 primeras líneas (nombre y cálculo), que el mensaje de la pre-orden ya trae.
 */
function textoAnuncio_(monto, nombre, cuenta, conEncabezado, saltados) {
  try {
    var t = prepararOrdenP2P_(monto, nombre, saltados || [], null, metodosParaCuenta_(cuenta));
    return (!conEncabezado && /^\*/.test(t)) ? t.split('\n').slice(2).join('\n') : t;
  } catch (e) {
    logError_('PREORDEN_ANUNCIO', e.message || e);
    return 'No pude buscar el anuncio (' + (e.message || e) + '). Tocá "Buscar otro anuncio" en la página.';
  }
}

/** Miniatura del comprobante (imagen o PDF) para mostrarla dentro de la página, sin abrir otro link. */
function miniaturaComprobante_(driveId) {
  if (!driveId) return '';
  try {
    var head = { headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() }, muteHttpExceptions: true };
    var res = UrlFetchApp.fetch('https://www.googleapis.com/drive/v3/files/' + driveId + '?fields=thumbnailLink', head);
    var link = res.getResponseCode() === 200 ? JSON.parse(res.getContentText()).thumbnailLink : null;
    var blob;
    if (link) {
      var img = UrlFetchApp.fetch(link.replace(/=[^=]*$/, '=s900'), head);
      if (img.getResponseCode() === 200) blob = img.getBlob();
    }
    if (!blob) blob = DriveApp.getFileById(driveId).getBlob();   // sin miniatura: el archivo original
    if (!/^image\//.test(blob.getContentType())) return '';
    return 'data:' + blob.getContentType() + ';base64,' + Utilities.base64Encode(blob.getBytes());
  } catch (e) {
    logError_('PREORDEN_FOTO', driveId + ' | ' + e.message);
    return '';
  }
}

/** Página del link "Revisar". La llama doGet (9_P2P.gs) cuando p2p=pre. */
function paginaPreOrden_(p) {
  var esc = escHtml_;
  var movId = p.mov || p.id;   // "id" puede chocar con el visor de Google; los links nuevos usan "mov"
  var sh = hojaMovimientos_();
  var col = colOrden_(sh);
  var r = filaPorId_(sh, movId);
  if (!r) return HtmlService.createHtmlOutput('No encontré ese comprobante (¿lo borraste?)');
  if (String(r.datos[C.MONEDA - 1]).trim() === 'VES') return paginaPreOrdenVes_(p, sh, r, col);   // 13_CuentasVes.gs
  var d = r.datos, orden = String(d[col - 1] || '');
  var tasa = tasaNetaActual_();
  var monto = Number(d[C.MONTO - 1]) || 0;
  var aprobada = orden.indexOf(PRE_APROBADA) === 0;
  var foto = miniaturaComprobante_(d[C.DRIVE_ID - 1]);

  // Datos de Pago Móvil / transferencia (10_AgendaCuentas.gs). Dos vistas: #pend (elegir, antes de confirmar)
  // y #conf (la cuenta usada, después). Deshacer vuelve de #conf a #pend sin recargar.
  var cliente = String(d[C.NOMBRE - 1]);
  var usado = String(d[colEncabezado_(sh, COL_DESTINO) - 1] || '');
  var ctas = cuentasDelCliente_(cliente);
  var opcion = function (c, marcada, recibida) {
    var sello = c.estado === AG_AGENDADA
      ? '<span class="ag">✅ agendada · ' + c.veces + (c.veces === 1 ? ' vez' : ' veces') + '</span>'
      : '<span class="nu">🆕 nueva</span>';
    return '<label class="dt' + (recibida ? ' rec' : '') + '"><input type="radio" name="cta" value="' + esc(c.clave) + '"' +
      (marcada ? ' checked' : '') + '><div style="flex:1;min-width:0">' + bloqueDatos_(lineasCuenta_(c)) +
      '<div class="s">' + sello + '</div></div></label>';
  };
  var sug = cuentaSugerida_(cliente, ctas);
  // La sugerida primero (marcada); las demás detrás. Desde la 4.ª, en un desplegable.
  var lista = (ctas.reciente ? [ctas.reciente] : []).concat(ctas.otras);
  if (sug.cuenta && !ctas.reciente) lista = [sug.cuenta].concat(ctas.otras.filter(function (c) { return c !== sug.cuenta; }));
  var pend = [], resto = [];
  lista.forEach(function (c, i) {
    var o = opcion(c, c === sug.cuenta, c === ctas.reciente);
    (i < MAX_CUENTAS_A_LA_VISTA ? pend : resto).push(o);
  });
  if (sug.motivo === 'nombre') pend.unshift('<p class="av">No mandó datos: pidió a ' + esc(mayusculaInicial_(sug.cuenta.titular)) + ' (de la Agenda).</p>');
  else if (sug.motivo === 'siempre') pend.unshift('<p class="av">No mandó datos: te marqué la de siempre.</p>');
  if (resto.length) pend.push('<details><summary class="s">Ver ' + resto.length + ' cuenta' + (resto.length === 1 ? '' : 's') +
    ' más</summary>' + resto.join('') + '</details>');
  pend.push('<details' + (lista.length ? '' : ' open') + '><summary class="s">Otra cuenta: pegá los datos</summary>' +
    '<textarea id="tx" rows="4" placeholder="0102 0412... cédula..."></textarea></details>');
  if (!ctas.reciente && !ctas.otras.length) pend.unshift('<p class="av">Todavía no mandó datos de pago.</p>');
  var conf = usado ? '<div class="dt">' + '<div style="flex:1;min-width:0">' + bloqueDatos_(lineasDeCampos_(usado.split(' · '))) + '</div></div>'
                   : '<p class="s">Confirmada sin datos de pago.</p>';

  var css =
    '<style>' +
    'body{margin:0;background:#f2f4f7;font-family:-apple-system,Roboto,sans-serif;color:#1d2433}' +
    '.w{max-width:520px;margin:0 auto;padding:10px}' +
    '.c{background:#fff;border-radius:14px;padding:10px 14px;margin-bottom:10px;box-shadow:0 1px 3px rgba(0,0,0,.08)}' +
    'h1{font-size:18px;margin:0}.s{color:#6b7280;font-size:12px}' +
    '.t{font-size:12px;font-weight:700;letter-spacing:.05em;margin:0}' +
    '.out{border-left:6px solid #1f7a4d;padding:14px}.out .t{color:#1f7a4d}' +
    '.bs{font-size:40px;font-weight:800;color:#14532d;margin:2px 0 0;line-height:1.1}' +
    '.bs small{font-size:22px;font-weight:700}' +
    '.calc{color:#6b7280;font-size:13px;margin:2px 0 0}' +
    '.dt{display:flex;gap:10px;align-items:flex-start;border:1px solid #e5e7eb;border-radius:10px;padding:8px 10px;margin:8px 0 0}' +
    '.dt.rec{border-color:#1f7a4d;background:#f0faf4}.dt input{flex:none;margin:5px 2px 0;transform:scale(1.3)}' +
    '.dl{font-size:14px;line-height:1.3}.ag{color:#1f7a4d}.nu{color:#b45309}' +
    '.dc{display:flex;justify-content:space-between;align-items:center;gap:10px}' +
    '.cp{width:auto;flex:none;font-size:14px;font-weight:700;letter-spacing:.04em;color:#1f7a4d;background:#fff;border:2px solid #1f7a4d;' +
    'border-radius:10px;padding:12px 14px;margin:0}.cp.ok2{background:#1f7a4d;color:#fff}' +
    'details{margin-top:8px}textarea{width:100%;box-sizing:border-box;font-size:15px;padding:8px;border:1px solid #d0d5dd;border-radius:10px;margin-top:6px}' +
    '.av{background:#fff7e6;color:#8a5a00;border-radius:8px;padding:6px 10px;font-size:13px;margin:8px 0 0}' +
    '.an{font-size:14px;line-height:1.4;white-space:normal;word-break:break-word}.an a{color:#2563eb}.an a.bin{color:#1d2433}' +
    '.bin{display:block;text-align:center;font-size:17px;font-weight:700;color:#fff;background:#f0b90b;border-radius:12px;padding:12px;margin-top:8px;text-decoration:none}' +
    '.in{background:#f8fafc;box-shadow:none;border:1px solid #e5e7eb}.in .t{color:#9ca3af}' +
    '.ars{font-size:17px;font-weight:600;color:#6b7280;margin:2px 0 0}' +
    '.cta{font-size:12px;font-weight:600;color:#6b7280;background:#e5e7eb;border-radius:6px;padding:1px 7px;margin-left:6px;vertical-align:middle}' +
    '.rc{display:flex;justify-content:space-between;align-items:flex-start;gap:10px}' +
    '.th{width:60px;height:80px;object-fit:cover;object-position:top;border-radius:6px;border:1px solid #d0d5dd;flex:none;opacity:.9}' +
    '#zz{display:none;position:fixed;inset:0;background:rgba(0,0,0,.88);z-index:9;padding:10px;box-sizing:border-box}' +
    '#zz img{width:100%;height:100%;object-fit:contain}' +
    '.row{display:flex;gap:8px;align-items:center;margin-top:8px}' +
    'input[type=number]{flex:1;min-width:0;font-size:16px;color:#4b5563;padding:7px 9px;border:1px solid #d0d5dd;border-radius:10px;box-sizing:border-box;background:#fff}' +
    '.b{width:100%;font-size:18px;padding:12px;border:0;border-radius:12px;background:#1f7a4d;color:#fff;margin-top:8px}' +
    '.b2{background:#fff;color:#1f7a4d;border:2px solid #1f7a4d}.b3{background:#fff;color:#b42318;border:2px solid #f3b5ae;font-size:15px}' +
    '.dif{font-size:14px;font-weight:700;color:#b45309;background:#fff7e6;border-radius:8px;padding:6px 10px;margin:8px 0 0}' +
    '.b:disabled{opacity:.5}.ok{font-size:15px;color:#1f7a4d;margin:6px 0 0}.err{color:#b42318}' +
    '</style>';

  var cabecera =
    '<div class="c"><h1>' + esc(cliente || d[C.TELEFONO - 1]) + '</h1>' +
    '<div class="s" id="est">' + esc(d[C.ESTADO - 1]) + (orden ? ' · ' + esc(orden) : '') + '</div></div>';

  var enviar =
    '<div class="c out"><p class="t">ENVIAR EN VES</p>' +
    '<div class="bs"><span id="bs">' + fmtN_(monto * tasa, 0) + '</span> <small>Bs</small></div>' +
    '<p class="calc" id="calc">= ' + fmtN_(monto, 0) + ' ARS × ' + fmtN_(tasa, 3) + '</p>' +
    '<div id="pend"' + (aprobada ? ' style="display:none"' : '') + '>' + pend.join('') + '</div>' +
    '<div id="conf"' + (aprobada ? '' : ' style="display:none"') + '>' + conf + '</div></div>';

  var anuncio =
    '<div class="c"><p class="t" style="color:#6b7280">ANUNCIO DE BINANCE</p>' +
    '<div id="an" class="an s">' + (aprobada ? 'Si necesitás otro anuncio, buscalo acá.' : 'Buscando anuncio...') + '</div>' +
    '<p id="dif" class="dif" style="display:none"></p>' +
    '<button type="button" class="b b3" id="sal" style="display:none"></button>' +
    '<button type="button" class="b b2" id="bus">🔄 Buscar otro anuncio</button></div>';

  var recibido =
    '<div class="c in rc"><div style="flex:1;min-width:0"><p class="t">RECIBIDO EN ARS</p>' +
    '<div class="ars"><span id="mv">' + fmtN_(monto, 0) + '</span> ARS' +
    (d[C.CUENTA - 1] ? '<span class="cta">' + esc(d[C.CUENTA - 1]) + '</span>' : '') + '</div>' +
    (foto ? '' : '<div class="s">No pude cargar la foto.</div>') +
    '<div class="row"><span class="s">¿Mal leído?</span>' +
    '<input id="m" type="number" inputmode="decimal" value="' + esc(monto || '') + '"' + (aprobada ? ' disabled' : '') + '></div></div>' +
    (foto ? '<img class="th" src="' + foto + '" alt="comprobante" onclick="zz.style.display=\'block\'">' : '') + '</div>' +
    (foto ? '<div id="zz" onclick="this.style.display=\'none\'"><img src="' + foto + '" alt="comprobante"></div>' : '');

  var acciones =
    '<button type="button" class="b" id="ok"' + (aprobada ? ' style="display:none"' : '') + '>✅ Confirmar (pasa a CONTADO)</button>' +
    '<button type="button" class="b b3" id="un"' + (aprobada ? '' : ' style="display:none"') + '>↩️ Deshacer y corregir</button>' +
    '<p id="r" class="ok"></p>';

  var k = JSON.stringify(p.k), mov = JSON.stringify(movId);
  var js =
    '<script>var t=' + tasa + ',tt=' + JSON.stringify(fmtN_(tasa, 3)) + ',K=' + k + ',MOV=' + mov + ',A=' + aprobada + ';' +
    'function $(i){return document.getElementById(i);}var m=$("m");' +
    'function f(n){return Math.round(n).toLocaleString("es-AR");}' +
    'm.oninput=function(){var v=Number(m.value)||0;$("mv").textContent=f(v);$("calc").textContent="= "+f(v)+" ARS × "+tt;$("bs").textContent=f(v*t);};' +
    'function sel(){return A?["",""]:[(document.querySelector("input[name=cta]:checked")||{}).value||"",($("tx")||{}).value||""];}' +
    'function modo(a){A=a;$("pend").style.display=a?"none":"";$("conf").style.display=a?"":"none";' +
    '$("ok").style.display=a?"none":"";$("un").style.display=a?"":"none";m.disabled=a;}' +
    'function msg(x,e){$("r").className=e?"ok err":"ok";$("r").textContent=x;}' +
    'function run(b,fn,args,ok){b.disabled=true;msg("...");var g=google.script.run.withSuccessHandler(function(x){b.disabled=false;ok(x);})' +
    '.withFailureHandler(function(e){b.disabled=false;msg("Error: "+e.message,true);});g[fn].apply(g,args);}' +
    // copiar con un toque (execCommand anda dentro del marco de Apps Script; clipboard de respaldo)
    'function cp(v){var x=document.createElement("textarea");x.value=v;x.setAttribute("readonly","");x.style.position="fixed";x.style.opacity="0";' +
    'document.body.appendChild(x);x.select();x.setSelectionRange(0,99999);var ok=false;try{ok=document.execCommand("copy");}catch(e){}' +
    'document.body.removeChild(x);if(!ok&&navigator.clipboard)navigator.clipboard.writeText(v);}' +
    'document.addEventListener("click",function(e){var b=e.target.closest(".cp");if(!b)return;e.preventDefault();cp(b.getAttribute("data-v"));' +
    'b.classList.add("ok2");b.textContent="COPIADO";setTimeout(function(){b.classList.remove("ok2");b.textContent="COPIAR";},1200);});' +
    // Saltar un trader en esta página (p. ej. uno de confianza cuyo anuncio no se deja tomar): SALT se acumula,
    // REF es el primero que saltaste, para mostrar cuánto peor es el precio del siguiente.
    'var SALT=[],REF=null,ULT=null;' +
    'function pct(p){var d=(p/REF.precio-1)*100;return(d>0?"+":"")+d.toLocaleString("es-AR",{minimumFractionDigits:2,maximumFractionDigits:2})+"%";}' +
    'function buscar(b){var s=sel();$("an").innerHTML="Buscando anuncio...";$("sal").style.display="none";' +
    'run(b,"rebuscarAnuncioWeb",[K,MOV,Number(m.value),s[0],s[1],SALT],function(x){$("an").className="an";$("an").innerHTML=x.html;msg("");' +
    'ULT=x.apodo?x:null;if(ULT){$("sal").textContent="⛔ Saltar "+x.apodo+" y buscar el siguiente";$("sal").style.display="";}' +
    'if(REF&&ULT){$("dif").textContent="Diferencia vs "+REF.apodo+": "+pct(ULT.precio)+" (saltados: "+SALT.join(", ")+")";$("dif").style.display="";}' +
    'else if(REF){$("dif").textContent="Sin más anuncios (saltados: "+SALT.join(", ")+")";$("dif").style.display="";}});}' +
    '$("bus").onclick=function(){buscar(this);};' +
    '$("sal").onclick=function(){if(!ULT)return;if(!REF)REF=ULT;SALT.push(ULT.apodo);buscar(this);};' +
    '$("ok").onclick=function(){var s=sel();run(this,"confirmarPreOrdenWeb",[K,MOV,Number(m.value),s[0],s[1]],' +
    'function(x){$("conf").innerHTML=x.html;$("est").textContent=x.estado;modo(true);msg(x.msg);});};' +
    '$("un").onclick=function(){run(this,"deshacerPreOrdenWeb",[K,MOV],function(x){$("est").textContent=x.estado;modo(false);msg(x.msg);});};' +
    // Sin confirmar: busca el anuncio al abrir, así "Abrir en Binance" ya está; con Atrás volvés acá a Confirmar
    'if(!A)buscar($("bus"));' +
    '</script>';

  var html = '<meta name="viewport" content="width=device-width,initial-scale=1">' + css +
    '<div class="w">' + cabecera + enviar + anuncio + recibido + acciones + '</div>' + js;
  return HtmlService.createHtmlOutput(html).setTitle('Pre-orden');
}

function escHtml_(t) {
  return String(t === undefined || t === null ? '' : t).replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/** Bloque de datos de pago: las líneas en chico y un solo botón COPIAR que copia todo. */
function bloqueDatos_(lineas) {
  return '<div class="dc"><div class="dl">' + lineas.map(escHtml_).join('<br>') + '</div>' +
    '<button type="button" class="cp" data-v="' + escHtml_(lineas.join('\n')) + '">COPIAR</button></div>';
}

/** Cuenta para buscar el anuncio desde la página: datos pegados, la elegida o (si ya está confirmada) la de Destino. */
function cuentaParaBuscar_(r, sh, clave, texto) {
  if (texto && String(texto).trim()) {
    var p = leerDatosPago_(texto);
    if (!p) throw new Error('No reconocí los datos pegados (falta teléfono o cuenta, cédula o banco)');
    return p;
  }
  if (clave) return leerAgenda_().filter(function (x) { return x.clave === clave; })[0] || null;
  var f = String(r.datos[colEncabezado_(sh, COL_DESTINO) - 1] || '').split(' · ');
  return f.length >= 4 ? { tipo: f[0] === 'PM' ? 'PM' : 'TRANSF', banco: String(f[1]).slice(0, 4) } : null;
}

/**
 * Botón "Buscar otro anuncio". No cambia nada en la planilla: busca de nuevo y lo muestra en la página.
 * saltados = traders que salteaste en esta página ("Saltar X"): no se ofrecen aunque sean de confianza.
 * Devuelve { html, apodo, precio } para que la página pueda ofrecer saltarlo y calcular la diferencia.
 */
function rebuscarAnuncioWeb(k, id, monto, clave, texto, saltados) {
  if (k !== claveNext_()) throw new Error('No autorizado');
  if (!(monto > 0)) throw new Error('Monto inválido');
  var sh = hojaMovimientos_();
  var r = filaPorId_(sh, id);
  if (!r) throw new Error('No encontré ese comprobante');
  var nombre = String(r.datos[C.NOMBRE - 1] || r.datos[C.TELEFONO - 1]);
  var t = textoAnuncio_(monto, nombre, cuentaParaBuscar_(r, sh, clave, texto), false, saltados || []);
  var link = (t.match(new RegExp(LINK_ANUNCIO.replace(/[.?]/g, '\\$&') + '\\S+')) || [])[0];
  var u = link ? JSON.parse(PropertiesService.getScriptProperties().getProperty('P2P_ULTIMA') || '{}') : {};
  return {
    html: escHtml_(t).replace(/\*/g, '').replace(/(https?:\/\/[^\s<]+)/g, '<a target="_blank" href="$1">$1</a>')
      .replace(/\n/g, '<br>') + (link ? '<a class="bin" target="_blank" href="' + escHtml_(link) + '">Abrir en Binance</a>' : ''),
    apodo: u.apodo || '', precio: Number(u.precio) || 0
  };
}

/**
 * Botón Confirmar. Pasa a CONTADO, marca APROBADA, guarda la cuenta en Destino y la agenda. No busca anuncio
 * (ya vino con la pre-orden; si hace falta otro, "Buscar otro anuncio").
 * clave = cuenta elegida de la Agenda; texto = datos pegados (ganan sobre la elegida). Los dos pueden venir vacíos.
 */
function confirmarPreOrdenWeb(k, id, monto, clave, texto) {
  if (k !== claveNext_()) throw new Error('No autorizado');
  if (!(monto > 0)) throw new Error('Monto inválido');
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(15000)) throw new Error('Ocupado, probá de nuevo en unos segundos');
  try {
    var sh = hojaMovimientos_();
    var col = colOrden_(sh);
    var r = filaPorId_(sh, id);
    if (!r) throw new Error('No encontré ese comprobante');
    if (String(r.datos[col - 1]).indexOf(PRE_APROBADA) === 0) throw new Error('Ya estaba confirmada');
    var nombre = String(r.datos[C.NOMBRE - 1] || r.datos[C.TELEFONO - 1]);
    var cuenta = usarCuentaAgenda_(nombre, clave, texto);   // si los datos pegados no se entienden, corta acá
    sh.getRange(r.fila, colEncabezado_(sh, COL_DESTINO)).setValue(cuenta ? textoCuenta_(cuenta) : '');
    if (Number(r.datos[C.MONTO - 1]) !== monto) {
      sh.getRange(r.fila, C.MONTO).setValue(monto);
      if (String(r.datos[C.MONEDA - 1]).trim() === 'VES') recalcularArsFila_(sh, r.fila, monto);   // Bs: el ARS sigue al monto
    }
    sh.getRange(r.fila, C.ESTADO).setValue(E_CONT);
    var marca = PRE_APROBADA + ' ' + Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'dd/MM HH:mm');
    sh.getRange(r.fila, col).setValue(marca);
    SpreadsheetApp.flush();
    return {
      msg: 'Confirmada.' + (cuenta && cuenta.avisoCedula ? ' ⚠️ ' + cuenta.avisoCedula : ''),
      estado: E_CONT + ' · ' + marca,
      html: cuenta ? '<div class="dt"><div style="flex:1;min-width:0">' + bloqueDatos_(lineasCuenta_(cuenta)) + '</div></div>'
                   : '<p class="s">Confirmada sin datos de pago.</p>'
    };
  } finally {
    lock.releaseLock();
  }
}

/** Botón Deshacer: vuelve a LEIDO, borra Destino y le resta el uso a la cuenta. No se reenvía sola (queda ENVIADA). */
function deshacerPreOrdenWeb(k, id) {
  if (k !== claveNext_()) throw new Error('No autorizado');
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(15000)) throw new Error('Ocupado, probá de nuevo en unos segundos');
  try {
    var sh = hojaMovimientos_();
    var col = colOrden_(sh);
    var colDest = colEncabezado_(sh, COL_DESTINO);
    var r = filaPorId_(sh, id);
    if (!r) throw new Error('No encontré ese comprobante');
    if (String(r.datos[col - 1]).indexOf(PRE_APROBADA) !== 0) throw new Error('No estaba confirmada');
    desusarCuentaAgenda_(r.datos[colDest - 1]);
    sh.getRange(r.fila, colDest).setValue('');
    sh.getRange(r.fila, C.ESTADO).setValue(E_LEID);
    var marca = PRE_ENVIADA + ' ' + Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'dd/MM HH:mm') + ' (deshecha)';
    sh.getRange(r.fila, col).setValue(marca);
    SpreadsheetApp.flush();
    return { msg: 'Deshecha: corregí monto o datos y confirmá de nuevo.', estado: E_LEID + ' · ' + marca };
  } finally {
    lock.releaseLock();
  }
}

// Corré esto UNA vez desde el editor: borra el activador viejo que revisaba cada hora.
// Ya no hace falta: la pre-orden sale cuando llega el comprobante, y refrescarTodo queda de respaldo.
function quitarTriggerPreOrden() {
  var n = 0;
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'enviarPreOrdenes') { ScriptApp.deleteTrigger(t); n++; }
  });
  Logger.log('Activadores de enviarPreOrdenes borrados: ' + n);
}
