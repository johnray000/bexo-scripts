// 14_TradersVes.gs — Mantiene al día la hoja traders_ves con tus órdenes P2P de Binance. No crea hojas.
// Las órdenes las manda subir_ordenes.py desde el teléfono (Termux, cada 4 horas) vía doPost,
// porque Binance no deja llamar a su API privada ni desde Apps Script (403) ni desde el VPS de EE.UU. (451).
// Propiedad del script requerida: ORDENES_TOKEN (la misma que ~/.subir-ordenes.env en el teléfono).
//
// Cómo suma sin guardar cada orden: traders_ves ya tiene los totales del export hasta TRADERS_HASTA
// (propiedad del script). Cada vuelta suma solo las órdenes terminadas entre TRADERS_HASTA y hace 2 horas,
// y corre TRADERS_HASTA. Las 2 horas dejan terminar las órdenes en curso antes de contarlas.
//
// La API tapa los apodos ("Cor***") pero trae el número de anuncio (columna F, Anuncios). El apodo completo sale de:
//   1) la primera carga: tu export (en Drive) cruzado con la API por número de orden;
//   2) cada vuelta: los anuncios que ve el relay (número de anuncio + apodo completo).
// Si todavía no se sabe, la fila queda como "Cor*** (anuncio …1234)" y se une sola cuando aparece.

var ENCABEZADOS_TRADERS_VES = ['Apodo', 'Órdenes completadas', 'Canceladas', 'USDT vendidos', 'Última orden', 'Anuncios'];
var EXPORT_C2C_NOMBRE = 'historial_c2c_6m_2026-10-14.csv';   // tu export, subido tal cual a Google Drive
var MARGEN_EN_CURSO_MS = 2 * 3600 * 1000;

/** Lo llama doPost cuando llega {ordenesP2P: [...], token}. Suma lo nuevo a traders_ves y responde. */
function recibirOrdenesP2P_(data) {
  var salida = function (obj) {
    return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
  };
  var props = PropertiesService.getScriptProperties();
  var token = props.getProperty('ORDENES_TOKEN');
  if (!token || data.token !== token) return salida({ error: 'no autorizado' });
  var lock = LockService.getScriptLock();
  try {
    lock.waitLock(30000);
    var r = actualizarTradersVes_(data.ordenesP2P || [], Number(data.desde) || 0);
    if (typeof agregarBinanceOrdenesP2P_ === 'function') r.registro = agregarBinanceOrdenesP2P_(data.ordenesP2P || []);   // 15_OKX.gs
    props.setProperty('ORDENES_ULTIMA_SUBIDA', String(Date.now()));
    return salida(r);
  } catch (e) {
    logError_('recibirOrdenesP2P_', e.message || e);
    return salida({ error: String(e.message || e) });
  } finally {
    lock.releaseLock();
  }
}

function tapado_(apodo) {
  return String(apodo).indexOf('***') !== -1;
}

/** "Cor*** (anuncio …1234)" → "Cor": las letras que Binance deja ver. */
function letrasVisibles_(apodo) {
  return String(apodo).split('*')[0];
}

function leerTradersVesFilas_(sh) {
  var n = ENCABEZADOS_TRADERS_VES.length;
  if (sh.getLastRow() < 2) return [];
  return sh.getRange(2, 1, sh.getLastRow() - 1, n).getValues()
    .filter(function (f) { return String(f[0]).trim() !== ''; })
    .map(function (f) {
      var anuncios = {};
      String(f[5] || '').split(',').forEach(function (a) { if (a.trim()) anuncios[a.trim()] = true; });
      return { apodo: String(f[0]).trim(), ok: Number(f[1]) || 0, canc: Number(f[2]) || 0,
               usdt: Number(f[3]) || 0, ultima: f[4] instanceof Date ? f[4] : (f[4] ? new Date(f[4]) : null),
               anuncios: anuncios };
    });
}

function escribirTradersVes_(sh, filas) {
  var n = ENCABEZADOS_TRADERS_VES.length;
  filas = filas.slice().sort(function (a, b) { return b.ok - a.ok || b.usdt - a.usdt; });
  if (sh.getLastRow() > 1) sh.getRange(2, 1, sh.getLastRow() - 1, n).clearContent();   // solo A:F
  sh.getRange(1, 1, 1, n).setValues([ENCABEZADOS_TRADERS_VES]).setFontWeight('bold');
  sh.setFrozenRows(1);
  if (!filas.length) return 0;
  sh.getRange(2, 6, filas.length, 1).setNumberFormat('@');   // los números de anuncio no entran en un número
  sh.getRange(2, 1, filas.length, n).setValues(filas.map(function (t) {
    return [t.apodo, t.ok, t.canc, Math.round(t.usdt * 100) / 100, t.ultima || '', Object.keys(t.anuncios).join(',')];
  }));
  sh.getRange(2, 5, filas.length, 1).setNumberFormat('yyyy-mm-dd');
  return filas.length;
}

/** Suma la fila b dentro de a (totales, anuncios y última orden). */
function unirTrader_(a, b) {
  a.ok += b.ok; a.canc += b.canc; a.usdt += b.usdt;
  if (b.ultima && (!a.ultima || b.ultima > a.ultima)) a.ultima = b.ultima;
  Object.keys(b.anuncios).forEach(function (k) { a.anuncios[k] = true; });
}

/** Número de anuncio → apodo completo, de los anuncios VES que ve el relay ahora (leerAnunciosP2P_ de 9_P2P.gs). */
function anunciosDelRelay_() {
  var consultas = [['', ''], ['', 10000], ['', 30000], ['', 100000],
                   ['PagoMovil', ''], ['Banesco', ''], ['Mercantil', ''], ['BancoDeVenezuela', ''],
                   ['BNCBancoNacional', ''], ['Bancamiga', '']];
  var vistos = {};
  consultas.forEach(function (c) {
    try {
      leerAnunciosP2P_('VES', 'SELL', c[0], c[1]).forEach(function (a) {
        if (a.adNo && a.apodo) vistos[String(a.adNo)] = String(a.apodo).trim();
      });
    } catch (e) {
      logError_('anunciosDelRelay_ ' + c.join('/'), e.message || e);   // sin anuncios igual se suman las órdenes
    }
  });
  return vistos;
}

/** Primera carga: número de orden → apodo completo, y la hora de la última orden del export. */
function leerExportC2C_() {
  var archivos = DriveApp.getFilesByName(EXPORT_C2C_NOMBRE);
  if (!archivos.hasNext()) throw new Error('No encuentro ' + EXPORT_C2C_NOMBRE + ' en tu Drive: subilo tal cual (Nuevo → Subir archivo)');
  var txt = archivos.next().getBlob().getDataAsString('UTF-8').replace(/^﻿/, '');
  var apodos = {}, hasta = 0;
  Utilities.parseCsv(txt).slice(1).forEach(function (f) {
    if (f.length < 13 || !f[0]) return;
    apodos[String(f[0])] = String(f[10]).trim();
    hasta = Math.max(hasta, new Date(String(f[12]).replace(' ', 'T') + '-03:00').getTime() || 0);
  });
  return { apodos: apodos, hasta: hasta };
}

/**
 * Suma a traders_ves las ventas USDT→VES terminadas entre TRADERS_HASTA y hace 2 horas.
 * `desde` es desde cuándo pidió el teléfono a Binance: si es posterior a TRADERS_HASTA, quedó un hueco.
 * La primera vez (sin TRADERS_HASTA) además aprende el número de anuncio de cada trader del export.
 */
function actualizarTradersVes_(lista, desde) {
  var props = PropertiesService.getScriptProperties();
  var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(HOJA_TRADERS_VES);
  if (!sh) throw new Error('No existe la hoja ' + HOJA_TRADERS_VES);
  var filas = leerTradersVesFilas_(sh);
  var porApodo = {}, porAnuncio = {};
  var indexar = function (t) {
    porApodo[t.apodo] = t;
    Object.keys(t.anuncios).forEach(function (a) { porAnuncio[a] = t; });
  };
  filas.forEach(indexar);

  var ventas = lista.filter(function (o) {
    return o.tipo === 'SELL' && o.activo === 'USDT' && o.fiat === 'VES' && o.anuncio;
  });

  // 1) Primera carga: el export dice quién es cada orden; así cada anuncio queda con su apodo completo.
  var hasta = Number(props.getProperty('TRADERS_HASTA')) || 0;
  var aprendidos = 0;
  if (!hasta) {
    var exp = leerExportC2C_();
    hasta = exp.hasta;
    ventas.forEach(function (o) {
      var t = porApodo[exp.apodos[String(o.numero)]];
      if (t && !t.anuncios[o.anuncio]) { t.anuncios[o.anuncio] = true; porAnuncio[o.anuncio] = t; aprendidos++; }
    });
  }

  // 2) Lo que ve el relay ahora: completa las filas tapadas.
  var relay = anunciosDelRelay_();
  filas.slice().forEach(function (t) {
    if (!tapado_(t.apodo)) return;
    var completo = Object.keys(t.anuncios).map(function (a) { return relay[a]; })
      .filter(function (ap) { return ap && ap.indexOf(letrasVisibles_(t.apodo)) === 0; })[0];
    if (!completo) return;
    delete porApodo[t.apodo];
    if (porApodo[completo]) {
      unirTrader_(porApodo[completo], t);
      filas.splice(filas.indexOf(t), 1);
    } else {
      t.apodo = completo;
    }
    indexar(porApodo[completo] || t);
  });

  // 3) Sumar las órdenes terminadas en la ventana (hasta, ahora - 2 h].
  var tope = Date.now() - MARGEN_EN_CURSO_MS;
  var sumadas = 0;
  ventas.forEach(function (o) {
    var final = o.estado === 'COMPLETED' || String(o.estado).indexOf('CANCELLED') === 0;
    if (!final || o.hora <= hasta || o.hora > tope) return;
    var visibles = letrasVisibles_(o.contraparte);
    var t = porAnuncio[o.anuncio];
    if (t && t.apodo.indexOf(visibles) !== 0) t = null;   // las letras no coinciden: no adivinar
    if (!t) {
      var completo = relay[o.anuncio];
      var apodo = completo && completo.indexOf(visibles) === 0 ? completo
                  : o.contraparte + ' (anuncio …' + String(o.anuncio).slice(-4) + ')';
      t = porApodo[apodo];
      if (!t) { t = { apodo: apodo, ok: 0, canc: 0, usdt: 0, ultima: null, anuncios: {} }; filas.push(t); }
      t.anuncios[o.anuncio] = true;
      indexar(t);
    }
    if (o.estado === 'COMPLETED') {
      t.ok++;
      t.usdt += Number(o.cantidad) || 0;
      var d = new Date(o.hora);
      if (!t.ultima || d > t.ultima) t.ultima = d;
    } else {
      t.canc++;
    }
    sumadas++;
  });

  if (desde > hasta) {   // el teléfono pidió a Binance desde una fecha posterior a lo ya sumado
    logError_('actualizarTradersVes_', 'Hueco: el teléfono no mandó nada desde ' + new Date(hasta) +
              '. Corré en Termux: python ~/bexo-scripts/subir_ordenes.py --dias 30');
  }
  props.setProperty('TRADERS_HASTA', String(Math.max(hasta, tope)));
  var total = escribirTradersVes_(sh, filas);
  return { ok: true, recibidas: lista.length, sumadas: sumadas, anunciosAprendidos: aprendidos, traders: total };
}

/**
 * Aviso si el teléfono no mandó nada en 2 días (apagado, Termux dormido o key vencida).
 * Corré instalarControlTradersVes UNA vez: lo revisa todos los días a las 9:30.
 */
function controlTradersVes() {
  var ms = Number(PropertiesService.getScriptProperties().getProperty('ORDENES_ULTIMA_SUBIDA')) || 0;
  if (Date.now() - ms > 2 * 24 * 3600 * 1000) {
    sendWhatsAppMessage_(MI_TELEFONO, '⚠️ traders_ves no se actualiza desde ' +
      (ms ? Utilities.formatDate(new Date(ms), Session.getScriptTimeZone(), 'd/M HH:mm') : 'nunca') +
      '. Revisá Termux en el teléfono.');
  }
}

function instalarControlTradersVes() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'controlTradersVes') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('controlTradersVes').timeBased().atHour(9).nearMinute(30).everyDays(1).create();
  Logger.log('Control instalado: controlTradersVes a las 9:30 (' + Session.getScriptTimeZone() + ')');
}
