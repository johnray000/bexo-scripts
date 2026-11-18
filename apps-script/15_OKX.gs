// 15_OKX.gs — Registro de órdenes P2P de todos los exchanges en la hoja Ordenes_P2P (una fila por orden).
//
// De dónde sale cada fila (columna Fuente):
//   export  — tus exports CSV (Binance "Historial de órdenes C2C" y OKX "Descargar informe"), cargados una vez
//             con importarHistorialP2P(). Son las filas más completas.
//   api     — Binance: las órdenes que manda el teléfono cada 4 h (subir_ordenes.py → recibirOrdenesP2P_ en 14).
//             OKX: la API común (key de solo lectura), cada 4 h desde acá. Solo da la cripto que entra o sale:
//               117 "Fulfill an order" = compra completada (hora de cierre)
//               116 "Place an order"   = venta abierta (las cripto quedan en garantía; hora de creación)
//               118 "Cancel an order"  = esa venta se canceló
//   app     — OKX: el teléfono lee la lista Órdenes → Completadas (okx_ordenes.py) y completa moneda, monto,
//             precio y contraparte de las filas que vinieron de la API.
// Las columnas que una fuente no da quedan vacías.
//
// Propiedades del script: OKX_KEY, OKX_SECRET, OKX_PASSPHRASE (key de solo lectura), ORDENES_TOKEN (la del teléfono).

var HOJA_ORDENES_P2P = 'Ordenes_P2P';
var ENCABEZADOS_ORDENES_P2P = ['Exchange', 'Orden', 'Creada', 'Cerrada', 'Tipo', 'Cripto', 'Cantidad', 'Moneda',
                               'Monto', 'Precio', 'Método de pago', 'Contraparte', 'Estado', 'Comisión', 'Rol',
                               'Anuncio', 'Fuente', 'Ref API', 'Ref app'];
var C_ = {};   // índice de cada columna por nombre: C_['Cantidad'] = 6
ENCABEZADOS_ORDENES_P2P.forEach(function (h, i) { C_[h] = i; });
var EXPORT_BINANCE_NOMBRE = 'binance_historial_2024-10_2026-11.csv';   // subidos tal cual a Google Drive
var EXPORT_OKX_NOMBRE = 'okx_historial_2024-10_2026-11.csv';
var CARPETA_HISTORIAL_P2P = 'Historial P2P';   // carpeta de Drive donde van los exports
var OKX_VENTA_CERRADA_MS = 6 * 3600 * 1000;   // una venta de la API sin "Cancel" después de 6 h se da por completada

function pedirOKX_(ruta) {
  var p = PropertiesService.getScriptProperties();
  ['OKX_KEY', 'OKX_SECRET', 'OKX_PASSPHRASE'].forEach(function (k) {
    if (!p.getProperty(k)) throw new Error('Falta la propiedad del script ' + k + ' (revisá que el nombre esté igual, sin espacios).');
  });
  var hora = new Date().toISOString();
  var firma = Utilities.base64Encode(
    Utilities.computeHmacSha256Signature(hora + 'GET' + ruta, p.getProperty('OKX_SECRET')));
  var r = UrlFetchApp.fetch('https://www.okx.com' + ruta, {
    muteHttpExceptions: true,
    headers: {
      'OK-ACCESS-KEY': p.getProperty('OKX_KEY'), 'OK-ACCESS-SIGN': firma,
      'OK-ACCESS-TIMESTAMP': hora, 'OK-ACCESS-PASSPHRASE': p.getProperty('OKX_PASSPHRASE')
    }
  });
  var res = JSON.parse(r.getContentText());
  if (res.code !== '0') throw new Error('OKX ' + r.getResponseCode() + ': ' + r.getContentText().slice(0, 300));
  return res.data || [];
}

/** La hoja con los encabezados de ahora. Si existía con otras columnas (versión anterior), la rehace. */
function hojaOrdenesP2P_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(HOJA_ORDENES_P2P) || ss.insertSheet(HOJA_ORDENES_P2P);
  var n = ENCABEZADOS_ORDENES_P2P.length;
  var actual = sh.getLastColumn() ? sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].join('|') : '';
  if (actual !== ENCABEZADOS_ORDENES_P2P.join('|')) {
    sh.clear();
    sh.getRange(1, 1, 1, n).setValues([ENCABEZADOS_ORDENES_P2P]).setFontWeight('bold');
    sh.setFrozenRows(1);
  }
  return sh;
}

function leerOrdenesP2P_(sh) {
  if (sh.getLastRow() < 2) return [];
  return sh.getRange(2, 1, sh.getLastRow() - 1, ENCABEZADOS_ORDENES_P2P.length).getValues();
}

/** Escribe todas las filas, la más nueva arriba. */
function escribirOrdenesP2P_(sh, filas) {
  var n = ENCABEZADOS_ORDENES_P2P.length;
  filas.sort(function (a, b) { return new Date(b[C_['Creada']]) - new Date(a[C_['Creada']]); });
  if (sh.getLastRow() > 1) sh.getRange(2, 1, sh.getLastRow() - 1, n).clearContent();
  if (!filas.length) return;
  sh.getRange(2, C_['Orden'] + 1, filas.length, 1).setNumberFormat('@');   // números de orden de 20 dígitos
  sh.getRange(2, C_['Anuncio'] + 1, filas.length, 3).setNumberFormat('@');
  sh.getRange(2, 1, filas.length, n).setValues(filas);
  sh.getRange(2, C_['Creada'] + 1, filas.length, 2).setNumberFormat('dd/MM/yyyy HH:mm:ss');
}

function filaVacia_() {
  return ENCABEZADOS_ORDENES_P2P.map(function () { return ''; });
}

function mismaCantidad_(a, b) {
  return Math.abs(Number(a) - Number(b)) < 0.005;
}

/** "2026-11-02 21:35:30" (hora de Argentina, UTC-3) → Date. */
function fechaAR_(s) {
  var p = String(s).match(/(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):?(\d{2})?/);
  if (!p) return '';
  return new Date(Date.UTC(+p[1], +p[2] - 1, +p[3], +p[4], +p[5], +(p[6] || 0)) + 3 * 3600 * 1000);
}

function leerCsvDrive_(nombre) {
  var carpetas = DriveApp.getFoldersByName(CARPETA_HISTORIAL_P2P);
  var it = carpetas.hasNext() ? carpetas.next().getFilesByName(nombre) : DriveApp.getFilesByName(nombre);
  if (!it.hasNext()) throw new Error('No encuentro "' + nombre + '" en la carpeta "' + CARPETA_HISTORIAL_P2P +
                                     '" de tu Google Drive. Subilo tal cual (sin abrirlo con Hojas de cálculo).');
  var texto = it.next().getBlob().getDataAsString('UTF-8').replace(/^﻿/, '');
  var tabla = Utilities.parseCsv(texto);
  var enc = tabla.shift();
  return tabla.filter(function (f) { return f.length === enc.length; }).map(function (f) {
    var o = {};
    enc.forEach(function (h, i) { o[h.trim()] = f[i]; });
    return o;
  });
}

var ESTADOS_P2P_ = {
  COMPLETED: 'Completada', Completed: 'Completada', Fulfilled: 'Completada',
  CANCELLED: 'Cancelada', Cancelled: 'Cancelada', 'System cancelled': 'Cancelada', CANCELLED_BY_SYSTEM: 'Cancelada',
  Canceled: 'Cancelada', IN_APPEAL: 'En apelación', Unpaid: 'En curso'
};

function estadoP2P_(s) {
  return ESTADOS_P2P_[s] || (s ? 'En curso' : '');
}

/** Ejecutar una vez: carga los dos exports (Binance y OKX) como historia. Lo que ya está no se repite. */
function importarHistorialP2P() {
  var sh = hojaOrdenesP2P_();
  var filas = leerOrdenesP2P_(sh);
  var hay = {};
  filas.forEach(function (f) { if (f[C_['Orden']]) hay[f[0] + '|' + f[C_['Orden']]] = true; });
  var antes = filas.length;

  leerCsvDrive_(EXPORT_BINANCE_NOMBRE).forEach(function (o) {
    var num = String(o['Número de Pedido']).trim();
    if (!num || hay['Binance|' + num]) return;
    var f = filaVacia_();
    f[0] = 'Binance'; f[C_['Orden']] = num; f[C_['Creada']] = fechaAR_(o['Hora de creación']);
    f[C_['Tipo']] = o['Tipo de orden'] === 'Buy' ? 'Compra' : 'Venta';
    f[C_['Cripto']] = o['Activo']; f[C_['Cantidad']] = Number(o['Cantidad']);
    f[C_['Moneda']] = o['Tipo de Fiat']; f[C_['Monto']] = Number(o['Precio Total']); f[C_['Precio']] = Number(o['Precio']);
    f[C_['Contraparte']] = String(o['Contraparte']).trim(); f[C_['Estado']] = estadoP2P_(o['Estado']);
    f[C_['Comisión']] = Number(o['Tarifa de creador'] || o['Comisión de tomador'] || 0);
    f[C_['Rol']] = o['Tarifa de creador'] ? 'Anunciante' : 'Tomador';
    f[C_['Fuente']] = 'export';
    filas.push(f);
    hay['Binance|' + num] = true;
  });

  // Filas de OKX que entraron por la API o la app (sin número de orden): el export las completa en vez de repetirlas.
  var sinNumero = filas.filter(function (f) { return f[0] === 'OKX' && !f[C_['Orden']]; });
  leerCsvDrive_(EXPORT_OKX_NOMBRE).forEach(function (o) {
    var num = String(o['Order No']).trim();
    if (!num || hay['OKX|' + num]) return;
    var creada = fechaAR_(o['Created date']), cerrada = fechaAR_(o['Updated date']);
    var tipo = o['Order type'] === 'Buy' ? 'Compra' : 'Venta', cripto = String(o['Crypto']).toUpperCase();
    var f = null;
    sinNumero.forEach(function (g) {
      if (f || g[C_['Tipo']] !== tipo || g[C_['Cripto']] !== cripto || !mismaCantidad_(g[C_['Cantidad']], o['Volume'])) return;
      var dc = Math.abs(new Date(g[C_['Creada']]) - creada), dz = g[C_['Cerrada']] ? Math.abs(new Date(g[C_['Cerrada']]) - cerrada) : Infinity;
      if (dz <= 5000 || dc <= (g[C_['Fuente']] === 'api' ? 5000 : 60000)) f = g;
    });
    if (f) sinNumero.splice(sinNumero.indexOf(f), 1);
    else { f = filaVacia_(); filas.push(f); }
    f[0] = 'OKX'; f[C_['Orden']] = num; f[C_['Creada']] = fechaAR_(o['Created date']); f[C_['Cerrada']] = fechaAR_(o['Updated date']);
    f[C_['Tipo']] = o['Order type'] === 'Buy' ? 'Compra' : 'Venta';
    f[C_['Cripto']] = String(o['Crypto']).toUpperCase(); f[C_['Cantidad']] = Number(o['Volume']);
    f[C_['Moneda']] = o['Currency']; f[C_['Monto']] = Number(o['Amount']); f[C_['Precio']] = Number(o['Price']);
    f[C_['Método de pago']] = o['Payment method']; f[C_['Contraparte']] = o['Counterparty'];
    f[C_['Estado']] = estadoP2P_(o['Status']); f[C_['Fuente']] = 'export';
    hay['OKX|' + num] = true;
  });

  escribirOrdenesP2P_(sh, filas);
  Logger.log('Historia cargada: %s órdenes nuevas (total %s)', filas.length - antes, filas.length);
}

/** Lo llama recibirOrdenesP2P_ (14) con las órdenes de Binance que manda el teléfono: agrega las que faltan. */
function agregarBinanceOrdenesP2P_(lista) {
  var sh = hojaOrdenesP2P_();
  var filas = leerOrdenesP2P_(sh);
  var porNum = {};
  filas.forEach(function (f) { if (f[0] === 'Binance') porNum[f[C_['Orden']]] = f; });
  var nuevas = 0;
  lista.forEach(function (o) {
    var f = porNum[o.numero];
    if (f) {   // ya está: solo se actualiza el estado (una orden en curso que terminó)
      f[C_['Estado']] = estadoP2P_(o.estado);
      return;
    }
    f = filaVacia_();
    f[0] = 'Binance'; f[C_['Orden']] = o.numero; f[C_['Creada']] = new Date(o.hora);
    f[C_['Tipo']] = o.tipo === 'BUY' ? 'Compra' : 'Venta';
    f[C_['Cripto']] = o.activo; f[C_['Cantidad']] = o.cantidad; f[C_['Moneda']] = o.fiat;
    f[C_['Monto']] = o.total; f[C_['Precio']] = o.precio; f[C_['Contraparte']] = o.contraparte;
    f[C_['Estado']] = estadoP2P_(o.estado);
    if (o.comision !== undefined && o.comision !== '') f[C_['Comisión']] = Number(o.comision);
    if (o.rol) f[C_['Rol']] = o.rol === 'MAKER' ? 'Anunciante' : 'Tomador';
    f[C_['Anuncio']] = o.anuncio; f[C_['Fuente']] = 'api';
    filas.push(f);
    porNum[o.numero] = f;
    nuevas++;
  });
  escribirOrdenesP2P_(sh, filas);
  return nuevas;
}

/** Cada 4 horas (activador): movimientos de Funding de OKX del último mes; se unen a las filas que ya están. */
function traerMovimientosOKX() {
  var lock = LockService.getScriptLock();
  try {
    lock.waitLock(30000);
    var movs = [], despues = '';
    for (var i = 0; i < 30; i++) {
      var datos = pedirOKX_('/api/v5/asset/bills?limit=100' + (despues ? '&after=' + despues : ''));
      movs = movs.concat(datos);
      if (datos.length < 100) break;
      despues = datos[datos.length - 1].billId;
    }
    movs.sort(function (a, b) { return Number(a.ts) - Number(b.ts); });   // del más viejo al más nuevo

    var sh = hojaOrdenesP2P_();
    var filas = leerOrdenesP2P_(sh);
    var vistos = {};
    filas.forEach(function (f) { String(f[C_['Ref API']]).split('/').forEach(function (id) { if (id) vistos[id] = true; }); });
    var nuevas = 0, unidas = 0, canceladas = 0;

    movs.forEach(function (m) {
      if (vistos[m.billId] || ['116', '117', '118'].indexOf(m.type) === -1) return;
      var cant = Math.abs(Number(m.balChg)), ts = Number(m.ts);
      var tipo = m.type === '117' ? 'Compra' : 'Venta';
      // La fila que ya está (del export o de la app): compra → hora de cierre; venta → hora de creación;
      // cancelación → hora de cierre de la venta cancelada. Si hay varias, la más cercana en hora.
      var col = m.type === '116' ? 'Creada' : 'Cerrada';
      var mejor = null, dif = Infinity;
      filas.forEach(function (f) {
        if (f[0] !== 'OKX' || f[C_['Tipo']] !== tipo || f[C_['Cripto']] !== m.ccy || !mismaCantidad_(f[C_['Cantidad']], cant)) return;
        var ref = String(f[C_['Ref API']]);
        if (m.type === '118' ? ref.indexOf('/') !== -1 : ref !== '') return;   // cada movimiento, una sola fila
        var d, entra;
        if (f[C_[col]] && f[C_['Fuente']] !== 'app') {   // hora exacta (export, o API para la venta abierta)
          d = ts - new Date(f[C_[col]]).getTime();
          entra = Math.abs(d) <= 5000;
        } else {                                // sin esa hora: se mide desde la creación (la app no tiene segundos)
          d = ts - new Date(f[C_['Creada']]).getTime();
          entra = d >= -60000 && d <= (m.type === '116' ? 3 * 60000 : 3 * 3600 * 1000);
          if (m.type === '117' && f[C_['Estado']] === 'Cancelada') entra = false;
        }
        if (entra && Math.abs(d) < dif) { dif = Math.abs(d); mejor = f; }
      });
      if (m.type === '118') {
        if (mejor) {
          mejor[C_['Estado']] = 'Cancelada';
          mejor[C_['Ref API']] = (mejor[C_['Ref API']] ? mejor[C_['Ref API']] + '/' : '') + m.billId;
          canceladas++;
        }
        return;
      }
      if (mejor) {
        mejor[C_['Ref API']] = m.billId;
        unidas++;
        return;
      }
      var f = filaVacia_();
      f[0] = 'OKX'; f[C_['Creada']] = new Date(ts); f[C_['Tipo']] = tipo; f[C_['Cripto']] = m.ccy; f[C_['Cantidad']] = cant;
      if (m.type === '117') f[C_['Cerrada']] = new Date(ts);
      f[C_['Estado']] = m.type === '117' ? 'Completada' : 'En curso';
      f[C_['Fuente']] = 'api'; f[C_['Ref API']] = m.billId;
      filas.push(f);
      nuevas++;
    });

    var ahora = Date.now();
    filas.forEach(function (f) {
      if (f[0] === 'OKX' && f[C_['Fuente']] === 'api' && f[C_['Estado']] === 'En curso' &&
          ahora - new Date(f[C_['Creada']]).getTime() > OKX_VENTA_CERRADA_MS) f[C_['Estado']] = 'Completada';
    });
    escribirOrdenesP2P_(sh, filas);
    Logger.log('OKX: %s movimientos, %s órdenes nuevas, %s unidas a filas que ya estaban, %s canceladas',
               movs.length, nuevas, unidas, canceladas);
    return { movimientos: movs.length, nuevas: nuevas, unidas: unidas, canceladas: canceladas };
  } catch (e) {
    logError_('traerMovimientosOKX', e.message || e);
    throw e;
  } finally {
    lock.releaseLock();
  }
}

/** Lo llama doPost cuando llega {ordenesOKX: [...], token} desde el teléfono. */
function recibirOrdenesOKX_(data) {
  var salida = function (obj) {
    return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
  };
  var token = PropertiesService.getScriptProperties().getProperty('ORDENES_TOKEN');
  if (!token || data.token !== token) return salida({ error: 'no autorizado' });
  var lock = LockService.getScriptLock();
  try {
    lock.waitLock(30000);
    return salida(completarOrdenesOKX_(data.ordenesOKX || []));
  } catch (e) {
    logError_('recibirOrdenesOKX_', e.message || e);
    return salida({ error: String(e.message || e) });
  } finally {
    lock.releaseLock();
  }
}

/**
 * Cada orden de la app: {fecha: "02/11/2026 21:35" (hora de Argentina), tipo: "Comprar"|"Vender",
 * cripto, cantidad, moneda, monto, precio, contraparte, estado: "Completada"|"Cancelada"|...}.
 * Si la orden ya está completa (export), no se toca. Si vino de la API, se completa. Si no está, se agrega.
 */
function completarOrdenesOKX_(lista) {
  var sh = hojaOrdenesP2P_();
  var filas = leerOrdenesP2P_(sh);
  var porRef = {};
  filas.forEach(function (f) { if (f[C_['Ref app']]) porRef[f[C_['Ref app']]] = f; });
  var unidas = 0, agregadas = 0, yaEstaban = 0;

  lista.forEach(function (o) {
    var p = String(o.fecha).match(/(\d+)\/(\d+)\/(\d+)\s+(\d+):(\d+)/);
    if (!p) return;
    var t = Date.UTC(+p[3], +p[2] - 1, +p[1], +p[4], +p[5]) + 3 * 3600 * 1000;   // Argentina = UTC-3
    var tipo = o.tipo === 'Comprar' ? 'Compra' : 'Venta';
    var ref = [o.fecha, o.tipo, o.cripto, o.cantidad, o.monto, o.moneda].join('|');
    if (porRef[ref]) {
      porRef[ref][C_['Estado']] = o.estado;
      return;
    }
    // Candidatas: mismo tipo, cripto y cantidad, creada en ese minuto (las del export, con segundos) o,
    // si vino de la API sin hora de creación exacta: compra → cerrada hasta 3 h después; venta → el mismo minuto.
    var fila = null, dif = Infinity, completa = false;
    filas.forEach(function (f) {
      if (f[0] !== 'OKX' || f[C_['Ref app']] || f[C_['Tipo']] !== tipo || f[C_['Cripto']] !== o.cripto ||
          !mismaCantidad_(f[C_['Cantidad']], o.cantidad)) return;
      var d = new Date(f[C_['Creada']]).getTime() - t;
      var entra;
      if (f[C_['Fuente']] === 'export') entra = d >= 0 && d < 60000;
      else if (tipo === 'Compra') entra = o.estado === 'Completada' && d >= -60000 && d <= 3 * 3600 * 1000;
      else entra = d >= -60000 && d <= 3 * 60000;
      if (entra && Math.abs(d) < dif) { dif = Math.abs(d); fila = f; completa = f[C_['Fuente']] === 'export'; }
    });
    if (fila && completa) {
      fila[C_['Ref app']] = ref;
      yaEstaban++;
    } else if (fila) {
      fila[C_['Creada']] = new Date(t);
      fila[C_['Moneda']] = o.moneda; fila[C_['Monto']] = Number(o.monto); fila[C_['Precio']] = Number(o.precio);
      fila[C_['Contraparte']] = o.contraparte; fila[C_['Estado']] = o.estado;
      fila[C_['Fuente']] = 'api+app'; fila[C_['Ref app']] = ref;
      unidas++;
    } else {
      fila = filaVacia_();
      fila[0] = 'OKX'; fila[C_['Creada']] = new Date(t); fila[C_['Tipo']] = tipo; fila[C_['Cripto']] = o.cripto;
      fila[C_['Cantidad']] = Number(o.cantidad); fila[C_['Moneda']] = o.moneda; fila[C_['Monto']] = Number(o.monto);
      fila[C_['Precio']] = Number(o.precio); fila[C_['Contraparte']] = o.contraparte; fila[C_['Estado']] = o.estado;
      fila[C_['Fuente']] = 'app'; fila[C_['Ref app']] = ref;
      filas.push(fila);
      agregadas++;
    }
    porRef[ref] = fila;
  });
  escribirOrdenesP2P_(sh, filas);
  return { ok: true, recibidas: lista.length, unidas: unidas, agregadas: agregadas, yaEstaban: yaEstaban };
}

/** Ejecutar una vez, después de importarHistorialP2P: trae OKX ahora y deja el activador cada 4 horas. */
function instalarOKX() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'traerMovimientosOKX') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('traerMovimientosOKX').timeBased().everyHours(4).create();
  traerMovimientosOKX();
}
