/**
 * 18_Diagnostico.gs — Etapas 5 y 6 del diagnóstico del bot (las 1 a 4 las revisa el VPS: vps/diagnostico.py).
 *
 * Solo LEE: no escribe en ninguna hoja, no manda mensajes, no toca activadores.
 * Responde qué pasó con los comprobantes de las últimas 24 h: si se leyeron, si quedaron en REVISAR,
 * si salió la pre-orden, y si algo está apagado (K3) o dando errores (Debug_Errores).
 *
 * - Llega por doPost: {diagnostico: true, token, buscar?}. Mismo token que las órdenes (ORDENES_TOKEN).
 * - buscar (opcional): nombre o número; agrega los comprobantes de ese cliente de los últimos 7 días
 *   y si está en el Directorio.
 *
 * Instalación (una vez):
 *   1. Archivo nuevo en Apps Script: 18_Diagnostico, pegar todo esto.
 *   2. En 2_Recepcion.gs, en doPost, debajo de
 *        const data = JSON.parse(e.postData.contents);
 *      agregar la línea
 *        if (data.diagnostico) return diagnosticoPlanilla_(data);
 *   3. Redesplegar: Implementar → Administrar implementaciones → ✏️ → Nueva versión.
 *
 * Usa de otros archivos: C, E_PEND, E_LEID, E_REVI, hojaMovimientos_ (4), DIR_SHEET (1), BUFFER_SHEET (2),
 * COL_ORDEN, preOrdenActiva_, horaDePreOrden_, PROP_LECTURA_AGENDADA (11), esCuentaVe_ (13, si existe).
 */
var DIAG_HORAS = 24;          // ventana de comprobantes que se revisan
var DIAG_HORAS_BUSCAR = 168;  // al rastrear un cliente: 7 días

function diagnosticoPlanilla_(data) {
  var salida = function (obj) {
    return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
  };
  var token = PropertiesService.getScriptProperties().getProperty('ORDENES_TOKEN');
  if (!token || data.token !== token) return salida({ error: 'no autorizado' });
  try {
    return salida(diagnosticoDatos_(String(data.buscar || '')));
  } catch (e) {
    return salida({ error: String(e.message || e) });
  }
}

/** Para probar desde el editor: muestra en el registro lo mismo que recibe el VPS. */
function probarDiagnostico() {
  Logger.log(JSON.stringify(diagnosticoDatos_(''), null, 1));
}

function diagnosticoDatos_(buscar) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var ahora = Date.now();
  var props = PropertiesService.getScriptProperties();
  var r = { ok: true, ahora: ahora };

  // --- Interruptores ---
  r.preorden = typeof preOrdenActiva_ === 'function' ? preOrdenActiva_() : null;
  r.horaPreorden = typeof horaDePreOrden_ === 'function' ? horaDePreOrden_() : null;
  var bandeja = ss.getSheetByName('Bandeja_Entrada');
  r.bot = bandeja ? String(bandeja.getRange('J1').getValue()) : '';
  var agendada = Number(props.getProperty(typeof PROP_LECTURA_AGENDADA !== 'undefined' ? PROP_LECTURA_AGENDADA : 'LECTURA_AGENDADA')) || 0;
  r.lecturaAgendadaHace = agendada ? Math.round((ahora - agendada) / 1000) : null;
  r.activadores = ScriptApp.getProjectTriggers().map(function (t) { return t.getHandlerFunction(); });

  // --- Buffer: último mensaje que llegó a la planilla (cualquier cliente) ---
  var buf = ss.getSheetByName(typeof BUFFER_SHEET !== 'undefined' ? BUFFER_SHEET : 'Buffer');
  r.ultimoBuffer = 0;
  if (buf && buf.getLastRow() > 1) {
    buf.getRange(2, 4, buf.getLastRow() - 1, 1).getValues().forEach(function (f) {
      var t = f[0] instanceof Date ? f[0].getTime() : 0;
      if (t > r.ultimoBuffer) r.ultimoBuffer = t;
    });
  }

  // --- Último mensaje que llegó a la planilla por el webhook ---
  // El Buffer se vacía solo (processBuffer pasa todo a Bandeja_Entrada y de ahí a Historial), así que se mira
  // la fecha más nueva de las tres hojas: Buffer col D, Bandeja_Entrada col B, Historial col B.
  r.ultimoMensaje = r.ultimoBuffer;
  ['Bandeja_Entrada', 'Historial'].forEach(function (nombre) {
    var h = ss.getSheetByName(nombre);
    if (!h || h.getLastRow() < 2) return;
    h.getRange(2, 2, h.getLastRow() - 1, 1).getValues().forEach(function (f) {
      var t = f[0] instanceof Date ? f[0].getTime() : 0;
      if (t > r.ultimoMensaje && t <= ahora + 60000) r.ultimoMensaje = t;
    });
  });

  // --- Movimientos: comprobantes recientes ---
  // Lo nuevo entra arriba (fila 2); con lote corriendo, abajo. Se leen las primeras 400 y las últimas 100 filas,
  // no la hoja entera (con años de filas, leer todo tarda y el diagnóstico se ponía lento).
  var sh = hojaMovimientos_();
  var ancho = sh.getLastColumn(), ult = sh.getLastRow();
  var head = sh.getRange(1, 1, 1, ancho).getValues()[0].map(function (h) { return String(h).trim(); });
  var arriba = Math.min(400, ult - 1);
  var datos = [head].concat(arriba > 0 ? sh.getRange(2, 1, arriba, ancho).getValues() : []);
  var desdeAbajo = Math.max(arriba + 2, ult - 99);
  if (ult >= desdeAbajo) datos = datos.concat(sh.getRange(desdeAbajo, 1, ult - desdeAbajo + 1, ancho).getValues());
  var iOrden = head.indexOf(typeof COL_ORDEN !== 'undefined' ? COL_ORDEN : 'Orden P2P');
  var q = buscar.toLowerCase().trim();
  var qDig = q.replace(/\D/g, '');
  var desde = ahora - DIAG_HORAS * 3600 * 1000;
  var desdeBuscar = ahora - DIAG_HORAS_BUSCAR * 3600 * 1000;
  r.comprobantes = [];
  r.cliente = [];
  for (var i = 1; i < datos.length; i++) {
    var d = datos[i];
    var rec = d[C.RECIBIDO - 1] instanceof Date ? d[C.RECIBIDO - 1].getTime() : 0;
    if (!rec || rec < Math.min(desde, q ? desdeBuscar : desde)) continue;
    var moneda = String(d[C.MONEDA - 1]).trim().toUpperCase();
    var fila = {
      recibido: rec,
      nombre: String(d[C.NOMBRE - 1]),
      telefono: String(d[C.TELEFONO - 1]),
      estado: String(d[C.ESTADO - 1]).trim(),
      monto: Number(d[C.MONTO - 1]) || 0,
      moneda: moneda,
      orden: iOrden >= 0 ? String(d[iOrden]).trim() : '',
      // Solo ARS, o Bs a una cuenta de Venezuela de John, generan pre-orden (ver enviarPreOrdenes)
      llevaPreorden: moneda === 'ARS' ||
        (moneda === 'VES' && typeof esCuentaVe_ === 'function' && esCuentaVe_(d[C.CUENTA - 1]))
    };
    if (rec >= desde) r.comprobantes.push(fila);
    if (q && rec >= desdeBuscar) {
      var tel = fila.telefono.replace(/\D/g, '');
      var coincide = qDig.length >= 6 ? tel.slice(-8) === qDig.slice(-8) : fila.nombre.toLowerCase().indexOf(q) !== -1;
      if (coincide) r.cliente.push(fila);
    }
  }
  r.comprobantes.sort(function (a, b) { return b.recibido - a.recibido; });
  r.cliente.sort(function (a, b) { return b.recibido - a.recibido; });
  r.comprobantes = r.comprobantes.slice(0, 40);
  r.cliente = r.cliente.slice(0, 10);

  // --- Directorio (solo al rastrear) ---
  if (q) {
    r.directorio = [];
    var dir = ss.getSheetByName(typeof DIR_SHEET !== 'undefined' ? DIR_SHEET : 'Directorio');
    if (dir && dir.getLastRow() > 1) {
      dir.getRange(2, 1, dir.getLastRow() - 1, 2).getValues().forEach(function (f) {
        var tel = String(f[0]).replace(/\D/g, ''), nom = String(f[1]);
        var ok = qDig.length >= 6 ? (tel.length >= 8 && tel.slice(-8) === qDig.slice(-8)) : nom.toLowerCase().indexOf(q) !== -1;
        if (ok && r.directorio.length < 5) r.directorio.push({ telefono: tel, nombre: nom });
      });
    }
  }

  // --- Debug_Errores: lo de las últimas 24 h ---
  r.errores = [];
  var dbg = ss.getSheetByName('Debug_Errores');
  if (dbg && dbg.getLastRow() > 1) {
    var n = Math.min(200, dbg.getLastRow() - 1);
    dbg.getRange(dbg.getLastRow() - n + 1, 1, n, 3).getValues().forEach(function (f) {
      var t = f[0] instanceof Date ? f[0].getTime() : 0;
      if (t >= desde) r.errores.push({ cuando: t, etapa: String(f[1]), detalle: String(f[2]).substring(0, 120) });
    });
    r.errores.sort(function (a, b) { return b.cuando - a.cuando; });
    r.errores = r.errores.slice(0, 8);
  }
  return r;
}
