// ==========================================
// MÓDULO 4: COMPROBANTES
// Reemplaza por completo al anterior.
// ANTES DE USAR: borrá la hoja "Movimientos" vieja.
// El código la recrea con las columnas nuevas.
// ==========================================

var MOV_SHEET    = 'Movimientos';
var VISION_URL   = 'https://api.deepseek.com/chat/completions';
var VISION_MODEL = 'deepseek-flash';
var VISION_KEY   = PropertiesService.getScriptProperties().getProperty('DEEPSEEK_KEY');
var MI_TELEFONO  = CONFIG.MI_TELEFONO;   // tu número, sin + ni espacios (0_Config.gs)
var MAX_INTENTOS = 3;
var TOPE_LECTURA_MS = 3 * 60 * 1000;   // procesarPendientes corta a los 3 min; lo que quede sigue la próxima hora

// Estados
var E_PEND = 'PENDIENTE';     // llegó la imagen, falta OCR
var E_LEID = 'LEIDO';         // OCR ok — todavía NO cuenta
var E_REVI = 'REVISAR';       // falta algo o confianza baja
var E_CONT = 'CONTADO';       // vos lo aprobaste → suma en el dashboard
var E_DESC = 'DESCARTADO';    // no era un comprobante
var E_DUPL = 'DUPLICADO';     // referencia repetida
var E_NOIM = 'NO_IMAGEN';     // PDF, audio, etc.

// Columnas (1-indexadas). Estos son los valores por defecto: el código
// los corrige leyendo los encabezados de la fila 1 (mapearColumnas_),
// así podés reordenar las columnas de Movimientos como quieras.
// Lo único que NO se puede hacer es renombrar los encabezados.
var C = {
  ESTADO:1, RECIBIDO:2, NOMBRE:3, MONTO:4, MONEDA:5, CUENTA:6, IMAGEN:7,
  INSTITUCION:8, TITULAR:9, FECHA_OP:10, REFERENCIA:11, CONFIANZA:12,
  TELEFONO:13, INTENTOS:14, DRIVE_ID:15, ID:16, RAW:17
};
var ENCABEZADOS = ['Estado','Recibido','Nombre','Monto','Moneda','Cuenta','Imagen',
                   'Institucion','Titular_Origen','Fecha_Op','Referencia','Confianza',
                   'Telefono','Intentos','Drive_ID','ID','Raw_JSON'];

// Clave de C → texto del encabezado (ESTADO → 'Estado', etc.)
var C_ENCABEZADO = {};
for (var k_ in C) C_ENCABEZADO[k_] = ENCABEZADOS[C[k_] - 1];

// Lee la fila 1 de Movimientos y actualiza C con la posición real de cada
// columna. Si falta un encabezado, deja el valor anterior y lo anota en Debug_Errores.
function mapearColumnas_(sh) {
  var ult = sh.getLastColumn();
  if (ult < 1) return;
  var head = sh.getRange(1, 1, 1, ult).getValues()[0].map(function (h) {
    return String(h).trim();
  });
  var faltan = [];
  for (var k in C_ENCABEZADO) {
    var i = head.indexOf(C_ENCABEZADO[k]);
    if (i === -1) faltan.push(C_ENCABEZADO[k]);
    else C[k] = i + 1;
  }
  if (faltan.length) logError_('COLUMNAS', 'Faltan encabezados en Movimientos: ' + faltan.join(', '));
}

// Ancho de fila que necesita el código (la columna más a la derecha)
function anchoMov_() {
  var max = 0;
  for (var k in C) max = Math.max(max, C[k]);
  return max;
}

// ==========================================
// 1. RECEPCIÓN — se llama desde doPost
//    Rápido: solo escribe una fila. Sin red.
// ==========================================
function encolarMovimiento_(phone, nombre, driveId) {
  var sh = hojaMovimientos_();

  // La fila se arma por nombre de columna, no por posición
  var fila = [];
  for (var j = 0; j < anchoMov_(); j++) fila.push('');
  fila[C.ESTADO - 1]   = E_PEND;
  fila[C.RECIBIDO - 1] = new Date();
  fila[C.NOMBRE - 1]   = nombre;
  fila[C.TELEFONO - 1] = phone;
  fila[C.INTENTOS - 1] = 0;
  fila[C.DRIVE_ID - 1] = driveId;
  fila[C.ID - 1]       = 'MOV-' + Utilities.formatDate(new Date(), 'GMT-3', 'yyyyMMdd-HHmmss');

  var lock = LockService.getScriptLock();
  var conLock = lock.tryLock(5000);
  var n;

  try {
    if (conLock) {
      sh.insertRowBefore(2);                       // arriba de todo
      n = 2;
      sh.getRange(n, 1, 1, fila.length).setValues([fila]);
    } else {
      sh.appendRow(fila);                          // hay un lote corriendo: al final
      n = sh.getLastRow();
    }
    sh.getRange(n, C.IMAGEN).setFormula('=HYPERLINK("' + linkDrive_(driveId) + '","ver")');
  } finally {
    if (conLock) lock.releaseLock();
  }
}

function linkDrive_(driveId) {
  return 'https://drive.google.com/file/d/' + driveId + '/view';
}

function hojaMovimientos_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(MOV_SHEET);
  if (!sh) {
    sh = ss.insertSheet(MOV_SHEET);
    sh.appendRow(ENCABEZADOS);
    sh.getRange(1, 1, 1, ENCABEZADOS.length).setFontWeight('bold');
    sh.setFrozenRows(1);
    sh.setColumnWidth(C.IMAGEN, 50);
  }
  mapearColumnas_(sh);
  return sh;
}

// ==========================================
// 2. PROCESAR PENDIENTES
// ==========================================
function procesarPendientes() {
  if (!ocrActivo_()) return 0;   // lectura apagada (casilla H3 del Dashboard, 7_CargaManual.gs)

  var lock = LockService.getScriptLock();
  if (!lock.tryLock(10000)) return 0;

  try {
    var sh = hojaMovimientos_();
    if (sh.getLastRow() < 2) return 0;

    var data = sh.getDataRange().getValues();
    var procesados = 0;

    // Referencias ya registradas, para detectar duplicados
    var refs = {};
    for (var k = 1; k < data.length; k++) {
      var r = data[k][C.REFERENCIA - 1];
      if (r) refs[String(r)] = true;
    }

    var inicio = Date.now();
    for (var i = 1; i < data.length; i++) {
      if (data[i][C.ESTADO - 1] !== E_PEND) continue;

      // Apps Script corta todo a los 6 min: si se nos va el tiempo, el resto queda PENDIENTE
      if (Date.now() - inicio > TOPE_LECTURA_MS) {
        logError_('TIEMPO', 'Lectura cortada a los 3 min, quedan PENDIENTE para la próxima vuelta');
        break;
      }

      var fila = i + 1;
      var driveId = data[i][C.DRIVE_ID - 1];
      var intentos = Number(data[i][C.INTENTOS - 1]) || 0;

      if (!driveId) { marcar_(sh, fila, E_REVI); continue; }

      if (intentos >= MAX_INTENTOS) {
        marcar_(sh, fila, E_REVI);
        logError_('MAX_INTENTOS', driveId);
        continue;
      }
      sh.getRange(fila, C.INTENTOS).setValue(intentos + 1);
      SpreadsheetApp.flush();   // el intento queda guardado aunque DeepSeek se cuelgue y maten la ejecución

      try {
        var file = DriveApp.getFileById(driveId);
        var mime = file.getMimeType();
        var blob = null;

        if (mime === 'image/jpeg' || mime === 'image/png' || mime === 'image/webp') {
          blob = file.getBlob();
        } else if (mime === 'application/pdf') {
          blob = pdfAImagen_(driveId);
        }
        if (!blob) { marcar_(sh, fila, E_NOIM); continue; }

        var b64 = Utilities.base64Encode(blob.getBytes());
        var p = leerComprobante_(b64);

        if (!p) continue;   // queda PENDIENTE, reintenta la próxima

        sh.getRange(fila, C.RAW).setValue(JSON.stringify(p));

        if (p.es_comprobante === false) {
          marcar_(sh, fila, E_DESC);
          procesados++;
          continue;
        }

        if (p.referencia && refs[String(p.referencia)]) {
          sh.getRange(fila, C.REFERENCIA).setValue(p.referencia);
          marcar_(sh, fila, E_DUPL);
          procesados++;
          continue;
        }
        if (p.referencia) refs[String(p.referencia)] = true;

        var cuenta = inferirCuenta_(p.destino_identificador);
        var problema = validarDestino_(p);

        sh.getRange(fila, C.MONTO).setValue(p.monto || '');
        sh.getRange(fila, C.MONEDA).setValue(p.moneda || '');
        sh.getRange(fila, C.CUENTA).setValue(cuenta || '');
        sh.getRange(fila, C.FECHA_OP).setValue(p.fecha || '');
        sh.getRange(fila, C.INSTITUCION).setValue(p.institucion || '');
        sh.getRange(fila, C.TITULAR).setValue(p.titular_origen || '');
        sh.getRange(fila, C.REFERENCIA).setValue(p.referencia || '');
        sh.getRange(fila, C.CONFIANZA).setValue(p.confianza || 0);

        var ok = (p.confianza >= 0.8) && p.monto && cuenta;
        marcar_(sh, fila, ok ? E_LEID : E_REVI);

        procesados++;

      } catch (err) {
        logError_('PROCESAR', driveId + ' | ' + err.message);
      }
    }

    ordenarMovimientos_(sh);
    return procesados;

  } finally {
    lock.releaseLock();
  }
}

function marcar_(sh, fila, estado) {
  sh.getRange(fila, C.ESTADO).setValue(estado);
}

// Un CBU/CVU argentino tiene EXACTAMENTE 22 digitos.
// Si el OCR se comio uno, no podemos confiar en la cuenta.
function validarDestino_(p) {
  if (!p || !p.destino_identificador) return 'sin_destino';
  var tipo = String(p.destino_tipo || '').toUpperCase();
  if (tipo === 'CBU' || tipo === 'CVU') {
    var d = String(p.destino_identificador).replace(/\D/g, '');
    if (d.length !== 22) return 'cbu_incompleto';
  }
  return null;
}

// ==========================================
// 3. OCR
// ==========================================
function leerComprobante_(b64) {

  var prompt =
    'Analiza esta imagen. Devuelve SOLO un objeto JSON valido, sin markdown ni explicacion, ' +
    'con estas claves exactas:\n' +
    '{"es_comprobante": true|false, "monto": number|null, "moneda": string|null, ' +
    '"fecha": "YYYY-MM-DD"|null, "institucion": string|null, "referencia": string|null, ' +
    '"titular_origen": string|null, "titular_destino": string|null, ' +
    '"destino_identificador": string|null, "destino_tipo": string|null, "confianza": 0-1}\n' +
    'REGLAS:\n' +
    '- es_comprobante: true SOLO si es un comprobante o constancia de transferencia bancaria ' +
    'o de billetera virtual. Cualquier otra cosa (foto personal, captura de chat, meme, ' +
    'documento, factura de servicio) es false y el resto de los campos van null.\n' +
    '- monto: numero plano sin simbolos ni separadores de miles. ' +
    'El formato $20.000,00 significa veinte mil → 20000. El punto separa MILES, la coma es decimal.\n' +
    '- institucion: banco o billetera emisora, por el logo o encabezado ' +
    '(ej: Cuenta DNI, Mercado Pago, Brubank). Copia el nombre tal cual.\n' +
    '- destino_identificador: CVU, CBU o ALIAS de QUIEN RECIBE, nunca del remitente. ' +
    'Copialo completo, digito por digito, sin espacios ni guiones.\n' +
    '- destino_tipo: "CVU", "CBU" o "ALIAS".\n' +
    '- Si un dato no se ve con claridad, null. No inventes.\n' +
    '- confianza menor a 0.7 si la imagen esta borrosa, cortada o dudosa.';

  var payload = {
    model: VISION_MODEL,
    max_tokens: 600,
    thinking: { type: 'disabled' },
    response_format: { type: 'json_object' },
    messages: [{
      role: 'user',
      content: [
        { type: 'text', text: prompt },
        { type: 'image_url', image_url: { url: 'data:image/jpeg;base64,' + b64 } }
      ]
    }]
  };

  var res = UrlFetchApp.fetch(VISION_URL, {
    method: 'post',
    contentType: 'application/json',
    headers: { 'Authorization': 'Bearer ' + VISION_KEY },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });

  if (res.getResponseCode() !== 200) {
    logError_('VISION_HTTP', res.getResponseCode() + ' | ' + res.getContentText());
    return null;
  }

  var txt = JSON.parse(res.getContentText()).choices[0].message.content;
  if (!txt) { logError_('VISION_NULL', res.getContentText()); return null; }

  var ini = txt.indexOf('{'), fin = txt.lastIndexOf('}');
  if (ini === -1 || fin === -1) { logError_('VISION_SIN_JSON', txt); return null; }

  try {
    var obj = JSON.parse(txt.substring(ini, fin + 1));
    if (obj.es_comprobante === undefined) { logError_('VISION_VACIO', txt); return null; }
    return obj;
  } catch (e) {
    logError_('VISION_JSON_MALO', txt);
    return null;
  }
}

// ==========================================
// 4. IDENTIFICACIÓN DE CUENTA
//    Por CVU / CBU / ALIAS. Nada de moneda ni logo.
// ==========================================
var MAPA_CUENTAS = {
  // --- ultimos 4 digitos del CVU/CBU ---
  '3664': 'LJ',
  '2852': 'NJ',
  '2957': 'PPJ',
  '5117': 'CDJ',
  '6299': 'PXJ',
  '5410': 'APJ',
  '4054': 'BLJ',
  '0011': 'BBD',
  '0025': 'RBJ',
  '7002': 'UJ',
  '3366': 'UD',
  '0011': 'BBD',
  '0012': 'BBJ',
  '4158': 'BTJ',
  '1529': 'G66J',
  '0563': 'ARQJ',
  // faltan: E, RBJ, UJ, BBJ, UD, APB

  // --- alias (los puntos dan igual, se normalizan) ---
  'john.ray.dni':     'CDJ',
  'john.ray.pay':     'PPJ',
  'john.ray.belo':    'BLJ',
  'john.ray.lemon':   'LJ',
  'john.ray.prex':    'PXJ',
  'john.ray.naranja': 'NJ',
  'john.ray.astro':   'APJ',
  'john.ray.reba':   'RBJ',
  'john.ray.uala':   'UJ',
  'john.diba.uala':   'UD',
  'john.diba.brubank':   'BBD',
  'JOHN.RAY.G66':   'G66J',
};

function normAlias_(s) {
  return String(s).toLowerCase().replace(/[\s.\-_]/g, '');
}

function inferirCuenta_(identificador) {
  if (!identificador) return null;
  var raw = String(identificador).trim();
  var digitos = raw.replace(/\D/g, '');

  // Numerico largo → CVU/CBU, comparamos ultimos 4
  if (digitos.length >= 10) return MAPA_CUENTAS[digitos.slice(-4)] || null;

  // Alias → normalizamos los DOS lados
  var k = normAlias_(raw);
  for (var key in MAPA_CUENTAS) {
    if (normAlias_(key) === k) return MAPA_CUENTAS[key];
  }
  return null;
}

// ==========================================
// 5. RESUMEN DEL DÍA POR WHATSAPP
// ==========================================
function resumenDelDia() {
  var sh = hojaMovimientos_();
  if (sh.getLastRow() < 2) return 'Sin comprobantes hoy.';

  var data = sh.getDataRange().getValues();
  var hoy = new Date(); hoy.setHours(0, 0, 0, 0);

  var leidos = [], revisar = [], pend = 0, total = {};

  for (var i = 1; i < data.length; i++) {
    var recibido = new Date(data[i][C.RECIBIDO - 1]);
    if (recibido < hoy) continue;

    var est    = data[i][C.ESTADO - 1];
    var nombre = data[i][C.NOMBRE - 1] || data[i][C.TELEFONO - 1];
    var monto  = data[i][C.MONTO - 1];
    var moneda = data[i][C.MONEDA - 1] || '';
    var cuenta = data[i][C.CUENTA - 1];

    if (est === E_PEND) { pend++; continue; }

    if (est === E_LEID) {
      leidos.push('• ' + nombre + ' — ' + fmt_(monto) + ' ' + moneda + ' → ' + cuenta);
      total[moneda] = (total[moneda] || 0) + Number(monto);
    }
    
    else if (est === E_REVI || est === E_NOIM) {
      var falta = est === E_NOIM ? 'formato no soportado'
        : !monto ? 'no se leyó el monto'
        : (!cuenta ? 'cuenta no reconocida' : 'revisar datos');
      revisar.push('• ' + nombre + ' — ' + (monto ? fmt_(monto) + ' ' + moneda : '?') +
                   ' (' + falta + ')\n  ' + linkDrive_(data[i][C.DRIVE_ID - 1]));
    }
  }

  if (!leidos.length && !revisar.length && !pend) return 'Sin comprobantes hoy.';

  var out = ['📋 Comprobantes de hoy', ''];

  if (leidos.length) {
    out.push('LEÍDOS (' + leidos.length + ') — falta tu OK');
    out.push(leidos.join('\n'));
    out.push('');
  }
  if (revisar.length) {
    out.push('⚠️ REVISAR (' + revisar.length + ')');
    out.push(revisar.join('\n'));
    out.push('');
  }
  if (pend) { out.push('Sin procesar: ' + pend); out.push(''); }

  var totLinea = [];
  for (var m in total) totLinea.push(fmt_(total[m]) + ' ' + m);
  if (totLinea.length) out.push('Total leído: ' + totLinea.join(' · ') + ' (aún no contado)');

  out.push(SpreadsheetApp.getActiveSpreadsheet().getUrl());

  return out.join('\n');
}

function fmt_(n) {
  if (!n && n !== 0) return '?';
  return Number(n).toLocaleString('es-AR');
}

// ==========================================
// 6. ACCIONES DEL MENÚ
// ==========================================

// Procesa lo pendiente y te manda el resumen
function revisarComprobantes() {
  var cant = procesarPendientes();
  sendWhatsAppMessage_(MI_TELEFONO, resumenDelDia());
  SpreadsheetApp.getActiveSpreadsheet().toast(
    cant + ' procesados. Resumen enviado.', 'Comprobantes', 5);
}

// Solo el resumen, sin procesar nada nuevo
function soloResumen() {
  sendWhatsAppMessage_(MI_TELEFONO, resumenDelDia());
}

// Después de revisar: pasa todos los LEIDOS a CONTADO de una
function contarTodosLosLeidos() {
  var ui = SpreadsheetApp.getUi();
  var sh = hojaMovimientos_();
  var data = sh.getDataRange().getValues();

  var filas = [];
  for (var i = 1; i < data.length; i++) {
    if (data[i][C.ESTADO - 1] === E_LEID) filas.push(i + 1);
  }
  if (!filas.length) { ui.alert('No hay filas en LEIDO.'); return; }

  var resp = ui.alert('Contar ' + filas.length + ' movimientos',
    'Van a pasar a CONTADO y entrar en el dashboard. ¿Los revisaste?',
    ui.ButtonSet.YES_NO);
  if (resp !== ui.Button.YES) return;

  filas.forEach(function (f) { marcar_(sh, f, E_CONT); });
  ui.alert(filas.length + ' movimientos contados.');
}

// ==========================================
// 7. TESTS
// ==========================================
function testVision() {
  var file = DriveApp.getFileById('18GZ353jem_MUMqM8sBdCvCwrpIoEzlm5');
  var b64 = Utilities.base64Encode(file.getBlob().getBytes());
  var p = leerComprobante_(b64);
  Logger.log(JSON.stringify(p, null, 2));
  Logger.log('CUENTA   → ' + inferirCuenta_(p && p.destino_identificador));
  Logger.log('PROBLEMA → ' + validarDestino_(p));
}

function testAlias() {
  ['john.ray.lemon', 'JOHN RAY LEMON', 'johnraylemon',
   '0000168300000011073664', '000016830000011073664'
  ].forEach(function (s) { Logger.log(s + '  →  ' + inferirCuenta_(s)); });
}

function testResumen() {
  Logger.log(resumenDelDia());
}

// PDF → imagen de la pagina 1, con la miniatura que Drive ya genera.
function pdfAImagen_(driveId) {
  try {
    var head = { headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
                 muteHttpExceptions: true };

    var res = UrlFetchApp.fetch(
      'https://www.googleapis.com/drive/v3/files/' + driveId + '?fields=thumbnailLink', head);
    if (res.getResponseCode() !== 200) { logError_('PDF_META', res.getContentText()); return null; }

    var link = JSON.parse(res.getContentText()).thumbnailLink;
    if (!link) { logError_('PDF_SIN_THUMB', driveId); return null; }

    link = link.replace(/=[^=]*$/, '=s1600');   // la miniatura viene chica, la pedimos grande

    var img = UrlFetchApp.fetch(link, head);
    if (img.getResponseCode() !== 200) { logError_('PDF_THUMB', img.getResponseCode()); return null; }

    return img.getBlob();
  } catch (err) {
    logError_('PDF', driveId + ' | ' + err.message);
    return null;
  }
}

function testPdf(driveId) {
  var id = driveId || '1ESrulPSq1RxmigDgEtgRmb-4z4P_7uu0';
  Logger.log('mime: ' + DriveApp.getFileById(id).getMimeType());
  var b = pdfAImagen_(id);
  if (!b) { Logger.log('no se pudo'); return; }
  Logger.log('imagen: ' + b.getBytes().length + ' bytes');
  Logger.log(JSON.stringify(leerComprobante_(Utilities.base64Encode(b.getBytes())), null, 2));
}

function ordenarMovimientos_(sh) {
  sh = sh || hojaMovimientos_();
  var n = sh.getLastRow() - 1;
  if (n < 2) return;
  sh.getRange(2, 1, n, Math.max(sh.getLastColumn(), anchoMov_()))
    .sort({ column: C.RECIBIDO, ascending: false });
}