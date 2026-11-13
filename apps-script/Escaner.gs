// ==========================================
// MÓDULO 14: ESCÁNER DE COMPROBANTES PERDIDOS (solo lectura)
// ==========================================
// Lee de WAHA los chats de tus clientes (Directorio) de los últimos N días, junta las fotos y PDF que
// ELLOS mandaron, y las cruza con Movimientos por teléfono y hora. Te manda por WhatsApp las que no tienen fila.
//
// Solo lectura: no escribe en ninguna hoja, no baja imágenes, no manda nada a los clientes.
// Necesita que WAHA tenga el store prendido (desde el 9/11). El historial que tiene arranca ~7/9.
//
// cargarFaltantes(): además de avisar, CARGA los que faltan en Movimientos (ver más abajo).
//
// Usa de otros archivos: WAHA_API_KEY, DIR_SHEET, guardarEnDrive_, logError_ (2), sendWhatsAppMessage_ (3),
// MI_TELEFONO, C, E_PEND, E_REVI, hojaMovimientos_, anchoMov_, linkDrive_, procesarPendientes (4), colOrden_ (11).

var ESC_WAHA = CONFIG.WAHA_URL;   // 0_Config.gs
var ESC_SESION = 'default';
var ESCANER_DIAS = 30;           // cuántos días hacia atrás (Movimientos arranca el 8/10)
var ESC_MARGEN_ANTES_MIN = 10;   // una fila puede tener hora hasta 10 min ANTES que la foto (relojes)
var ESC_MARGEN_DESPUES_H = 24;   // ...y hasta 24 h DESPUÉS (WAHA a veces entregó tarde)
var ESC_EXCLUIR = ['john ray', 'gudy'];   // nombres del Directorio que no se revisan (vos, bloqueados)
// Números fuera del Directorio que no querés ver (familia, amigos): propiedad ESC_IGNORAR_NUMEROS, separados por coma.
var ESC_IGNORAR_NUMEROS = listaConfig_('ESC_IGNORAR_NUMEROS');
var ESC_MAX_CHARS = 3500;        // largo máximo del WhatsApp; el resto queda en el registro

function escanearComprobantes(dias, conOtros) {
  dias = Number(dias) || ESCANER_DIAS;
  var r = escanearWaha_(dias, conOtros === true);
  var texto = textoEscaner_(r, dias);
  Logger.log(texto);
  sendWhatsAppMessage_(MI_TELEFONO, texto.length > ESC_MAX_CHARS
    ? texto.substring(0, ESC_MAX_CHARS) + '\n…(sigue en Ejecuciones → registro)' : texto);
  return texto;
}

function escanear7dias() { return escanearComprobantes(7); }

/** Lo que corre el activador de los lunes: 7 días, clientes + números fuera del Directorio. */
function escaneoSemanal() { return escanearComprobantes(7, true); }

/** Revisión a mano de números fuera del Directorio, 30 días. */
function revisarNoAgendados() { return escanearComprobantes(30, true); }

/** Ejecutalo UNA vez: crea el activador de los lunes a las 9. Si ya existía, lo reemplaza. */
function activarEscanerSemanal() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'escaneoSemanal') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('escaneoSemanal').timeBased().onWeekDay(ScriptApp.WeekDay.MONDAY).atHour(9).create();
  Logger.log('Listo: escaneoSemanal corre los lunes entre las 9 y las 10.');
}

function esExcluidoTel_(k) {
  return k === tel8_(MI_TELEFONO) || ESC_IGNORAR_NUMEROS.some(function (t) { return tel8_(t) === k; });
}

function escanear30dias() { return escanearComprobantes(30); }

function escanearWaha_(dias, conOtros) {
  var desde = Math.floor(Date.now() / 1000) - dias * 86400;
  var ss = SpreadsheetApp.getActiveSpreadsheet();

  // --- 1. Clientes del Directorio: últimos 8 dígitos → nombre ---
  var clientes = {}, excluidos = {};
  ss.getSheetByName(DIR_SHEET).getDataRange().getValues().slice(1).forEach(function (f) {
    var k = tel8_(f[0]);
    var n = String(f[1] || f[0]);
    if (ESC_EXCLUIR.some(function (x) { return n.toLowerCase().indexOf(x) > -1; })) { if (k) excluidos[k] = true; return; }
    if (k) clientes[k] = n;
  });

  // --- 2. Chats de WAHA de esos clientes ---
  var lidAPn = {};
  try {
    (escGet_('/api/' + ESC_SESION + '/lids?limit=5000') || []).forEach(function (x) {
      if (x && x.lid && x.pn) lidAPn[String(x.lid)] = String(x.pn);
    });
  } catch (e) { /* versión sin /lids: se usan solo los chats @c.us */ }

  var chats = [], vistos = {}, otrosChats = [];
  (escGet_('/api/' + ESC_SESION + '/chats?limit=5000') || []).forEach(function (c) {
    var id = typeof c.id === 'string' ? c.id : (c.id && c.id._serialized) || '';
    if (!id || /@g\.us|@newsletter|@broadcast/.test(id)) return;
    var tel = /@lid$/.test(id) ? (lidAPn[id] || '') : id;
    var k = tel8_(tel.split('@')[0]);
    var ts = Number(c.conversationTimestamp || c.timestamp || 0);
    if (ts && ts < desde) return;                 // sin actividad en el período
    if (k && !clientes[k] && conOtros && !excluidos[k] && !esExcluidoTel_(k)) {
      otrosChats.push({ id: id, k: k, nombre: String(c.name || tel.split('@')[0]), tel: tel.split('@')[0].replace(/\D/g, ''), otro: true });
      return;
    }
    if (!k || !clientes[k]) return;
    chats.push({ id: id, k: k, nombre: clientes[k], tel: tel.split('@')[0].replace(/\D/g, '') });
    vistos[k] = true;
  });

  // --- 3. Fotos y PDF que mandó cada cliente (en tandas de 20) ---
  var fotos = [], otros = {};
  var todos = chats.concat(otrosChats);
  for (var i = 0; i < todos.length; i += 20) {
    var tanda = todos.slice(i, i + 20);
    var resps = UrlFetchApp.fetchAll(tanda.map(function (c) {
      return { url: ESC_WAHA + '/api/' + ESC_SESION + '/chats/' + encodeURIComponent(c.id) +
             '/messages?limit=1000&downloadMedia=false&filter.fromMe=false&filter.timestamp.gte=' + desde,
               headers: { 'X-Api-Key': WAHA_API_KEY }, muteHttpExceptions: true };
    }));
    resps.forEach(function (res, j) {
      if (res.getResponseCode() !== 200) return;
      var c = tanda[j];
      (JSON.parse(res.getContentText()) || []).forEach(function (m) {
        if (m.fromMe || Number(m.timestamp) < desde || !esComprobanteMedia_(m)) return;
        if (c.otro) {
          var o = otros[c.id] = otros[c.id] || { nombre: c.nombre, tel: c.tel, n: 0, ultima: 0, texto: '' };
          o.n++;
          if (Number(m.timestamp) > o.ultima) { o.ultima = Number(m.timestamp); o.texto = String(m.body || ''); }
          var pn = m._data && (m._data.pushName || (m._data.Info && m._data.Info.PushName));   // el nombre que el contacto puso en su WhatsApp
          if (pn && !o.perfil) o.perfil = String(pn);
          return;
        }
        fotos.push({ k: c.k, nombre: c.nombre, ts: Number(m.timestamp), texto: String(m.body || ''),
                     chatId: c.id, msgId: (typeof m.id === 'string' ? m.id : (m.id && m.id._serialized) || ''), tel: c.tel });
      });
    });
  }

  // --- 4. Movimientos: horas de las filas por teléfono ---
  var mv = ss.getSheetByName('Movimientos').getDataRange().getValues();
  var h = mv[0].map(function (x) { return String(x).trim(); });
  var iTel = h.indexOf('Telefono'), iId = h.indexOf('ID'), iRec = h.indexOf('Recibido');
  var filas = {};
  for (var r = 1; r < mv.length; r++) {
    var k = tel8_(mv[r][iTel]);
    if (!k) continue;
    var f = fechaDeIdMov_(mv[r][iId]);
    var manual = !f;
    if (manual && mv[r][iRec] instanceof Date) f = mv[r][iRec];
    if (f) (filas[k] = filas[k] || []).push({ t: Math.floor(f.getTime() / 1000), manual: manual, usada: false });
  }

  // --- 5. Cruce: cada foto se empareja con la primera fila libre en su ventana ---
  fotos.sort(function (a, b) { return a.ts - b.ts; });
  Object.keys(filas).forEach(function (k) { filas[k].sort(function (a, b) { return a.t - b.t; }); });
  var tz = Session.getScriptTimeZone();
  var dia = function (s) { return Utilities.formatDate(new Date(s * 1000), tz, 'yyyyMMdd'); };
  var faltan = fotos.filter(function (fo) {
    var lista = filas[fo.k] || [];
    for (var x = 0; x < lista.length; x++) {
      var fi = lista[x];
      if (fi.usada) continue;
      var ok = fi.manual ? dia(fi.t) === dia(fo.ts)
        : fi.t >= fo.ts - ESC_MARGEN_ANTES_MIN * 60 && fi.t <= fo.ts + ESC_MARGEN_DESPUES_H * 3600;
      if (ok) { fi.usada = true; return false; }
    }
    return true;
  });

  var listaOtros = Object.keys(otros).map(function (x) { return otros[x]; })
    .sort(function (a, b) { return b.ultima - a.ultima; });
  return { faltan: faltan, totalFotos: fotos.length, chats: chats.length, otros: listaOtros, conOtros: !!conOtros,
           clientes: Object.keys(clientes).length, sinChat: Object.keys(clientes).length - Object.keys(vistos).length };
}

// Foto o PDF (no audio, video ni sticker). Mira el mensaje crudo de NOWEB.
function esComprobanteMedia_(m) {
  if (!m.hasMedia) return false;
  // NOWEB trae _data.message; GOWS trae _data.Message. Se mira todo _data, sin importar mayúsculas.
  var s = JSON.stringify(m._data || {});
  if (/"imageMessage"/i.test(s)) return true;
  if (/"documentMessage"/i.test(s)) return /"mimetype":"(application\/pdf|image\/[a-z]+)"/i.test(s);
  if (/"(audioMessage|videoMessage|stickerMessage|ptvMessage)"/i.test(s)) return false;
  var mt = String((m.media && m.media.mimetype) || '');
  return /^image\/|application\/pdf/i.test(mt);
}

function textoEscaner_(r, dias) {
  var tz = Session.getScriptTimeZone();
  var L = ['🔎 *Escáner de comprobantes* · últimos ' + dias + ' días',
           r.chats + ' chats de clientes, ' + r.totalFotos + ' fotos/PDF recibidos.', ''];
  if (!r.faltan.length) L.push('✅ Todas tienen su fila en Movimientos.');
  else textoFaltan_(r, L, tz);
  if (r.conOtros) textoOtros_(r, L, tz);
  return L.join('\n');
}

function textoFaltan_(r, L, tz) {
  L.push('*' + r.faltan.length + ' sin fila en Movimientos* (puede haber fotos que no eran comprobantes):', '');
  var porCliente = {}, orden = [];
  r.faltan.slice().reverse().forEach(function (f) {
    if (!porCliente[f.nombre]) { porCliente[f.nombre] = []; orden.push(f.nombre); }
    porCliente[f.nombre].push(f);
  });
  orden.forEach(function (n) {
    var fs = porCliente[n];
    L.push('• *' + n + '* (' + fs.length + ')');
    fs.forEach(function (f) {
      L.push('   ' + Utilities.formatDate(new Date(f.ts * 1000), tz, 'dd/MM HH:mm') +
             (f.texto ? ' · "' + f.texto.substring(0, 40) + '"' : ''));
    });
  });
}

function textoOtros_(r, L, tz) {
  L.push('');
  if (!r.otros.length) { L.push('👤 Nadie fuera del Directorio te mandó fotos.'); return; }
  L.push('👤 *Fotos de números que NO están en el Directorio: ' + r.otros.length + '*',
         '(el bot no las registra; si es cliente, agregalo al Directorio y corré cargarFaltantes)');
  var hist = nombresHistorial_();
  r.otros.forEach(function (o) {
    var nombre = o.perfil || hist[tel8_(o.tel)] || (o.nombre !== o.tel ? o.nombre : '') || 'sin nombre';
    L.push('• *' + nombre + '* · ' + o.n + (o.n === 1 ? ' foto' : ' fotos') + ', última ' +
           Utilities.formatDate(new Date(o.ultima * 1000), tz, 'dd/MM HH:mm') +
           (o.texto ? ' · "' + o.texto.substring(0, 30) + '"' : '') +
           '\n   wa.me/' + o.tel);
  });
}

// Nombre que quedó en Historial para cada teléfono (por si WhatsApp no trae el nombre del perfil)
function nombresHistorial_() {
  var out = {};
  try {
    var hs = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Historial');
    if (!hs || hs.getLastRow() < 2) return out;
    var v = hs.getDataRange().getValues(), h = v[0].map(function (x) { return String(x).trim(); });
    var cT = h.indexOf('Teléfono'), cN = h.indexOf('Nombre');
    for (var i = 1; i < v.length; i++) {
      var k = tel8_(v[i][cT]), n = String(v[i][cN] || '').trim();
      if (k && n && n !== 'Sin Nombre' && !out[k]) out[k] = n;
    }
  } catch (e) {}
  return out;
}

function escGet_(path) {
  var res = UrlFetchApp.fetch(ESC_WAHA + path, { headers: { 'X-Api-Key': WAHA_API_KEY }, muteHttpExceptions: true });
  if (res.getResponseCode() !== 200) throw new Error('WAHA ' + res.getResponseCode() + ' en ' + path);
  return JSON.parse(res.getContentText());
}

function tel8_(t) { var d = String(t || '').replace(/\D/g, ''); return d.length >= 8 ? d.slice(-8) : ''; }

// MOV-20261109-152104 → fecha
function fechaDeIdMov_(id) {
  var m = /^MOV-(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})/.exec(String(id || ''));
  return m ? new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]) : null;
}

// ==========================================
// CARGAR LOS QUE FALTAN
// ==========================================
// Para cada foto/PDF sin fila: la baja de WAHA, la guarda en Drive y la pone en Movimientos como PENDIENTE,
// con la fecha y hora en que la mandó el cliente. DeepSeek la lee igual que siempre (mismo prompt).
// Si WhatsApp ya no tiene la imagen, la fila queda en REVISAR sin foto: ponés el Monto (y la Cuenta) a mano.
//
// - Columna "Orden P2P" = RECUPERADO → NO manda pre-orden (son pagos viejos).
// - Nada suma en el Dashboard hasta que vos lo pases a CONTADO, como siempre.
// - Si un comprobante ya lo tenías cargado a mano, DeepSeek lo marca DUPLICADO por la referencia.
// - Se puede correr de nuevo: lo que ya cargó no lo vuelve a cargar.

var ESC_MAX_CARGA = 15;   // máximo por corrida (el resto, en la siguiente)

function cargarFaltantes(dias) {
  dias = Number(dias) || ESCANER_DIAS;
  var r = escanearWaha_(dias);
  var tz = Session.getScriptTimeZone();
  var conFoto = [], sinFoto = [];

  r.faltan.slice(0, ESC_MAX_CARGA).forEach(function (f, i) {
    var driveId = null;
    try {
      var m = escGet_('/api/' + ESC_SESION + '/chats/' + encodeURIComponent(f.chatId) +
                      '/messages/' + encodeURIComponent(f.msgId) + '?downloadMedia=true');
      if (m && m.media && m.media.url && !m.media.error) driveId = guardarEnDrive_(m.media.url, f.tel, m.media.mimetype);
    } catch (e) { logError_('ESCANER', f.nombre + ' ' + f.ts + ' | ' + (e.message || e)); }
    try {
      agregarFilaRecuperada_(f, driveId, i);
      (driveId ? conFoto : sinFoto).push(f);
    } catch (e) { logError_('ESCANER', 'fila ' + f.nombre + ' | ' + (e.message || e)); }
  });

  var fmt = function (f) { return '• ' + Utilities.formatDate(new Date(f.ts * 1000), tz, 'dd/MM HH:mm') + ' · ' + f.nombre; };
  var L = ['📥 *Comprobantes recuperados* · últimos ' + dias + ' días', ''];
  if (!r.faltan.length) L.push('✅ No faltaba nada.');
  if (conFoto.length) L.push('*' + conFoto.length + ' cargados con foto* (PENDIENTE → los lee DeepSeek):', conFoto.map(fmt).join('\n'), '');
  if (sinFoto.length) L.push('*' + sinFoto.length + ' sin foto* (WhatsApp ya no la tiene). Quedaron en REVISAR: poné Monto y Cuenta:', sinFoto.map(fmt).join('\n'), '');
  if (r.faltan.length > ESC_MAX_CARGA) L.push('Quedan ' + (r.faltan.length - ESC_MAX_CARGA) + ' más: corré cargarFaltantes otra vez.');
  L.push('No se manda pre-orden de estos. Revisalos en Movimientos y pasalos a CONTADO.');
  var texto = L.join('\n');
  Logger.log(texto);
  sendWhatsAppMessage_(MI_TELEFONO, texto);

  if (conFoto.length) {
    try { procesarPendientes(); } catch (e) { logError_('ESCANER', 'lectura: ' + (e.message || e)); }
  }
  return texto;
}

function agregarFilaRecuperada_(f, driveId, i) {
  var sh = hojaMovimientos_();
  var colO = colOrden_(sh);
  var ancho = Math.max(anchoMov_(), colO);
  var fila = [];
  for (var j = 0; j < ancho; j++) fila.push('');
  var cuando = new Date(f.ts * 1000);
  fila[C.ESTADO - 1]   = driveId ? E_PEND : E_REVI;
  fila[C.RECIBIDO - 1] = cuando;
  fila[C.NOMBRE - 1]   = f.nombre;
  fila[C.TELEFONO - 1] = f.tel;
  fila[C.INTENTOS - 1] = 0;
  fila[C.DRIVE_ID - 1] = driveId || '';
  fila[C.ID - 1]       = 'MOV-' + Utilities.formatDate(cuando, 'GMT-3', 'yyyyMMdd-HHmmss') + '-R' + (i + 1);
  fila[colO - 1]       = 'RECUPERADO';
  if (!driveId) fila[C.RAW - 1] = '{"recuperado":"sin imagen en WhatsApp"' + (f.texto ? ',"texto":' + JSON.stringify(f.texto) : '') + '}';

  var lock = LockService.getScriptLock();
  var conLock = lock.tryLock(10000);
  try {
    sh.insertRowBefore(2);
    sh.getRange(2, 1, 1, fila.length).setValues([fila]);
    if (driveId) sh.getRange(2, C.IMAGEN).setFormula('=HYPERLINK("' + linkDrive_(driveId) + '","ver")');
  } finally {
    if (conLock) lock.releaseLock();
  }
}
