
/**
 * 17_MovimientosUY.gs — Recibe los movimientos que leen los scripts del teléfono (facturacion/prex.py, después
 * MiDinero, OCA, Itaú, Mercado Pago) y los anota en la hoja "Movs UY" de la planilla Registro BEXO.
 *
 * - Llega por doPost: {movimientosUY: [...], cta: 'Prex', token}. Mismo token que las órdenes (ORDENES_TOKEN).
 * - Nunca duplica: un movimiento ya anotado (misma cuenta + N° de referencia) se saltea.
 * - Lo nuevo va arriba, ordenado por fecha. No toca la hoja "Facturas UY".
 * - Guarda cuándo se leyó cada cuenta por última vez (propiedad MOVS_UY_ULTIMA_<cta>), para avisar si se atrasa.
 *
 * Instalación: este archivo + en 2_Recepcion.gs, en doPost, debajo de
 *   const data = JSON.parse(e.postData.contents);
 * la línea
 *   if (data.movimientosUY) return recibirMovimientosUY_(data);
 * Ejecutar una vez instalarMovsUY (pide permiso para abrir Registro BEXO y crea la hoja "Movs UY")
 * y redesplegar (Implementar → Administrar implementaciones → ✏️ → Nueva versión).
 */
var REGISTRO_BEXO_ID = CONFIG.REGISTRO_BEXO_ID;   // 0_Config.gs
var HOJA_MOVS_UY = 'Movs UY';
var ENC_MOVS_UY = ['fecha', 'monto', 'nombre', 'cta', 'hora', 'referencia', 'detalle', 'leído'];

function recibirMovimientosUY_(data) {
  var salida = function (obj) {
    return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
  };
  var props = PropertiesService.getScriptProperties();
  var token = props.getProperty('ORDENES_TOKEN');
  if (!token || data.token !== token) return salida({ error: 'no autorizado' });
  var lock = LockService.getScriptLock();
  try {
    lock.waitLock(30000);
    var r = agregarMovimientosUY_(data.movimientosUY || []);
    if (data.cta) props.setProperty('MOVS_UY_ULTIMA_' + data.cta, String(Date.now()));
    r.ok = true;
    return salida(r);
  } catch (e) {
    logError_('recibirMovimientosUY_', e.message || e);
    return salida({ error: String(e.message || e) });
  } finally {
    lock.releaseLock();
  }
}

/** Ejecutar una vez desde el editor: pide el permiso para abrir Registro BEXO y crea la hoja "Movs UY". */
function instalarMovsUY() {
  var sh = hojaMovsUY_();
  Logger.log('Hoja lista: ' + sh.getParent().getName() + ' → ' + sh.getName());
}

function hojaMovsUY_() {
  var ss = SpreadsheetApp.openById(REGISTRO_BEXO_ID);
  var sh = ss.getSheetByName(HOJA_MOVS_UY);
  if (!sh) {
    sh = ss.insertSheet(HOJA_MOVS_UY);
    sh.getRange(1, 1, 1, ENC_MOVS_UY.length).setValues([ENC_MOVS_UY]).setFontWeight('bold');
    sh.setFrozenRows(1);
    sh.getRange('A:A').setNumberFormat('dd/MM/yyyy');
    sh.getRange('B:B').setNumberFormat('#,##0');
    sh.getRange('E:F').setNumberFormat('@');
    sh.getRange('H:H').setNumberFormat('dd/MM HH:mm');
  }
  return sh;
}

/** "07/11/26 - 13:08" (Prex) → Date. También acepta "07/11/2026" sin hora. */
function fechaMovUY_(s) {
  var m = String(s || '').match(/(\d{1,2})\/(\d{1,2})\/(\d{2,4})(?:\D+(\d{1,2}):(\d{2}))?/);
  if (!m) return null;
  var anio = Number(m[3]) < 100 ? 2000 + Number(m[3]) : Number(m[3]);
  var texto = ('0' + m[1]).slice(-2) + '/' + ('0' + m[2]).slice(-2) + '/' + anio + ' ' +
              ('0' + (m[4] || '0')).slice(-2) + ':' + (m[5] || '00');
  // Se arma en la zona horaria de Registro BEXO para que la planilla muestre el mismo día que la app.
  var zona = SpreadsheetApp.openById(REGISTRO_BEXO_ID).getSpreadsheetTimeZone();
  return Utilities.parseDate(texto, zona, 'dd/MM/yyyy HH:mm');
}

/** "07/11/26 - 13:08" → "13:08"; sin hora → "". */
function horaMovUY_(s) {
  var m = String(s || '').match(/\D(\d{1,2}):(\d{2})/);
  return m ? ('0' + m[1]).slice(-2) + ':' + m[2] : '';
}

function agregarMovimientosUY_(lista) {
  var sh = hojaMovsUY_();
  var ya = {};
  var ult = sh.getLastRow();
  if (ult > 1) {
    sh.getRange(2, 4, ult - 1, 3).getValues().forEach(function (f) {   // D cta, E hora, F referencia
      if (f[2] !== '') ya[f[0] + '|' + f[2]] = true;
    });
  }
  var nuevas = [], repetidas = 0, sinRef = 0, ahora = new Date();
  lista.forEach(function (m) {
    var ref = String(m.referencia || '').trim();
    if (!ref) { sinRef++; return; }                 // sin referencia no se puede asegurar que no se duplique
    var clave = m.cta + '|' + ref;
    if (ya[clave]) { repetidas++; return; }
    ya[clave] = true;
    var f = fechaMovUY_(m.fecha_hora);
    nuevas.push([f, Number(m.monto), m.titular || m.descripcion || '', m.cta,
                 horaMovUY_(m.fecha_hora), ref,
                 m.descripcion || '', ahora]);
  });
  if (nuevas.length) {
    nuevas.sort(function (a, b) { return (b[0] || 0) - (a[0] || 0); });   // lo más nuevo arriba
    sh.insertRowsAfter(1, nuevas.length);
    sh.getRange(2, 1, nuevas.length, ENC_MOVS_UY.length).setValues(nuevas);
    sh.getRange(2, 2, nuevas.length, 1).setNumberFormat('#,##0');   // montos sin decimales
  }
  return { nuevas: nuevas.length, repetidas: repetidas, sinReferencia: sinRef };
}

/** Supervisión: los miércoles a la mañana avisa por WhatsApp si alguna cuenta no se leyó en los últimos 8 días
 *  (el botón del teléfono aparece los martes). Instalar una vez con instalarControlMovsUY. */
var CTAS_MOVS_UY = ['Prex', 'Itau', 'MiDinero'];   // se suman OcaBlue y MercadoPago a medida que tengan lector

function controlMovsUY() {
  var props = PropertiesService.getScriptProperties();
  var atrasadas = CTAS_MOVS_UY.filter(function (cta) {
    var ms = Number(props.getProperty('MOVS_UY_ULTIMA_' + cta)) || 0;
    return Date.now() - ms > 8 * 24 * 3600 * 1000;
  });
  if (atrasadas.length) {
    sendWhatsAppMessage_(MI_TELEFONO, '⚠️ Movimientos UY sin leer hace más de 8 días: ' + atrasadas.join(', ') +
      '. En el teléfono tocá "LEER MOVIMIENTOS UY" (o en Termux: sh ~/bexo-scripts/telefono/movs_uy.sh).');
  }
}

function instalarControlMovsUY() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'controlMovsUY') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('controlMovsUY').timeBased().onWeekDay(ScriptApp.WeekDay.WEDNESDAY).atHour(10).create();
  Logger.log('Control instalado: controlMovsUY los miércoles a las 10 (' + Session.getScriptTimeZone() + ')');
}