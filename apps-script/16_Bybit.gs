// 16_Bybit.gs — Órdenes P2P de Bybit en la hoja Ordenes_P2P (Exchange = Bybit).
//
// Dos fuentes, unidas por número de orden (una orden nunca se repite):
//   export — importarBybitP2P(): lee "bybit_historial.csv" de la carpeta "Historial P2P" de Drive (a mano).
//   api    — el teléfono (bybit_ordenes.py, cada 4 h con telefono/subir.sh) manda {ordenesBybit: [...], token}
//            y doPost llama a recibirOrdenesBybit_. Bybit bloquea las IP de EE.UU., por eso no se pide desde acá.
// Usa las funciones de 15_OKX.gs (hojaOrdenesP2P_, leerOrdenesP2P_, escribirOrdenesP2P_, leerCsvDrive_, fechaAR_,
// estadoP2P_, filaVacia_, C_).

var EXPORT_BYBIT_NOMBRE = 'bybit_historial.csv';

/** Ejecutar a mano: agrega a Ordenes_P2P las órdenes de Bybit del export. */
function importarBybitP2P() {
  var sh = hojaOrdenesP2P_();
  var filas = leerOrdenesP2P_(sh);
  var porNum = {};
  filas.forEach(function (f) { if (f[0] === 'Bybit' && f[C_['Orden']]) porNum[String(f[C_['Orden']])] = f; });
  var nuevas = 0, actualizadas = 0;

  leerCsvDrive_(EXPORT_BYBIT_NOMBRE).forEach(function (o) {
    var num = String(o['Order No']).trim();
    if (!num) return;
    var f = porNum[num];
    if (f) {
      f[C_['Estado']] = estadoP2P_(o['Status']);
      actualizadas++;
      return;
    }
    f = filaVacia_();
    f[0] = 'Bybit'; f[C_['Orden']] = num; f[C_['Creada']] = fechaAR_(o['Time']);
    f[C_['Tipo']] = o['Direction'] === 'BUY' ? 'Compra' : 'Venta';
    f[C_['Cripto']] = String(o['Coin Type']).toUpperCase(); f[C_['Cantidad']] = Number(o['Coin Amount']);
    f[C_['Moneda']] = o['Fiat Currency']; f[C_['Monto']] = Number(o['Fiat Amount']); f[C_['Precio']] = Number(o['Unit Price']);
    f[C_['Contraparte']] = String(o['Counterparty']).trim(); f[C_['Estado']] = estadoP2P_(o['Status']);
    f[C_['Comisión']] = Number(o['Transaction Fees'] || 0);
    f[C_['Fuente']] = 'export';
    filas.push(f);
    porNum[num] = f;
    nuevas++;
  });

  escribirOrdenesP2P_(sh, filas);
  Logger.log('Bybit: %s órdenes nuevas, %s ya estaban (total en la hoja %s)', nuevas, actualizadas, filas.length);
}

/** Lo llama doPost cuando llega {ordenesBybit: [...], token} desde el teléfono (bybit_ordenes.py). */
function recibirOrdenesBybit_(data) {
  var salida = function (obj) {
    return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
  };
  var token = PropertiesService.getScriptProperties().getProperty('ORDENES_TOKEN');
  if (!token || data.token !== token) return salida({ error: 'no autorizado' });
  var lock = LockService.getScriptLock();
  try {
    lock.waitLock(30000);
    var r = agregarBybitOrdenesP2P_(data.ordenesBybit || []);
    PropertiesService.getScriptProperties().setProperty('ORDENES_ULTIMA_BYBIT', String(Date.now()));   // lo muestra la Brújula
    // Tus anuncios con su estado (activo/pausado): la Brújula apaga los que Bybit dice que no están activos.
    if (Array.isArray(data.anunciosBybit)) {
      PropertiesService.getScriptProperties().setProperty('BYBIT_ANUNCIOS',
        JSON.stringify({ cuando: Date.now(), lista: data.anunciosBybit.slice(0, 40) }));
    }
    return salida(r);
  } catch (e) {
    logError_('recibirOrdenesBybit_', e.message || e);
    return salida({ error: String(e.message || e) });
  } finally {
    lock.releaseLock();
  }
}

/**
 * Cada orden: {numero, tipo: "BUY"|"SELL", activo, fiat, total, precio, cantidad, contraparte,
 * estado: "COMPLETED"|"CANCELLED"|"IN_APPEAL"|..., hora (ms), comision}.
 * Si ya está (del export o de una subida anterior) solo se actualiza el estado; si no, se agrega.
 */
function agregarBybitOrdenesP2P_(lista) {
  var sh = hojaOrdenesP2P_();
  var filas = leerOrdenesP2P_(sh);
  var porNum = {};
  filas.forEach(function (f) { if (f[0] === 'Bybit' && f[C_['Orden']]) porNum[String(f[C_['Orden']])] = f; });
  var nuevas = 0, yaEstaban = 0;
  lista.forEach(function (o) {
    var num = String(o.numero || '').trim();
    if (!num) return;
    var f = porNum[num];
    if (f) {   // ya está: una orden en curso que terminó o se canceló
      f[C_['Estado']] = estadoP2P_(o.estado);
      yaEstaban++;
      return;
    }
    f = filaVacia_();
    f[0] = 'Bybit'; f[C_['Orden']] = num; f[C_['Creada']] = new Date(Number(o.hora));
    f[C_['Tipo']] = o.tipo === 'BUY' ? 'Compra' : 'Venta';
    f[C_['Cripto']] = o.activo; f[C_['Cantidad']] = Number(o.cantidad); f[C_['Moneda']] = o.fiat;
    f[C_['Monto']] = Number(o.total); f[C_['Precio']] = Number(o.precio); f[C_['Contraparte']] = o.contraparte;
    f[C_['Estado']] = estadoP2P_(o.estado); f[C_['Comisión']] = Number(o.comision || 0);
    f[C_['Fuente']] = 'api';
    filas.push(f);
    porNum[num] = f;
    nuevas++;
  });
  escribirOrdenesP2P_(sh, filas);
  return { ok: true, recibidas: lista.length, nuevas: nuevas, yaEstaban: yaEstaban };
}
