/**
 * 22_RevisionBrujula.gs — Revisión de los datos de la Brújula P2P.
 *
 * No manda avisos ni se ve en la página: cada vez que la Brújula pide los números (cada 10 min) se revisan las
 * órdenes y el resultado queda en la hoja "Revision_Brujula" (y en data.json del VPS, campo "revision").
 * Claude la lee cuando john dice que algo no cierra, o cada tanto, y sabe en qué fila mirar.
 *
 * Cada prueba da {estado: 'ok' | 'ojo' | 'mal', prueba, detalle}:
 *   ok  = comprobado y bien
 *   ojo = puede estar bien, pero no lo puedo comprobar (dato faltante o supuesto)
 *   mal = hay un error en los datos o en el cálculo
 */
var HOJA_REVISION_BRUJULA = 'Revision_Brujula';

function revisarBrujula_(ords, salida, desde, ahora, zona) {
  var r = [];
  var add = function (estado, prueba, detalle) { r.push({ estado: estado, prueba: prueba, detalle: detalle }); };
  var f = function (d) { return Utilities.formatDate(d, zona, 'dd/MM HH:mm'); };
  var filas = function (lista) { return lista.slice(0, 8).map(function (o) { return o.fila; }).join(', ') + (lista.length > 8 ? '…' : ''); };
  var ok = ords.filter(function (o) { return o.estado === 'Completada' && o.cant > 0; });
  var ciclo = ok.filter(function (o) { return o.f >= desde; });

  // 1. Subidas de órdenes al día
  (salida.subidas || []).forEach(function (x) {
    if (x.fuente === 'OKX app') return;
    if (x.hace === null) add('ojo', 'Subida ' + x.fuente, 'Todavía no hay registro de la última subida (se anota desde el 24/11).');
    else add(x.atrasada ? 'mal' : 'ok', 'Subida ' + x.fuente, 'Última subida ' + x.cuando + ' (hace ' + x.hace + ' h; se sube cada 4 h).');
  });

  // 2. Órdenes sin moneda en el ciclo
  var sinMon = ciclo.filter(function (o) { return !o.mon; });
  if (sinMon.length) add('ojo', 'Órdenes sin moneda', sinMon.length + ' completadas del ciclo sin moneda (filas ' + filas(sinMon) + '). ' +
    'Si son OKX: correr el historial de OKX en el teléfono.');
  else add('ok', 'Órdenes sin moneda', 'Todas las órdenes completadas del ciclo tienen moneda.');

  // 3. Duplicados: mismo n° de orden (Binance/Bybit) o misma referencia de OKX
  var vistos = {}, dup = [];
  ords.forEach(function (o) {
    var k = o.orden ? o.ex + '|' + o.orden : (o.ex === 'OKX' && o.refApi ? 'OKX|' + o.refApi : '');
    if (!k) return;
    if (vistos[k]) dup.push(o); else vistos[k] = o;
  });
  if (dup.length) add('mal', 'Órdenes repetidas', dup.length + ' filas con el mismo n° de orden que otra (filas ' + filas(dup) + ').');
  else add('ok', 'Órdenes repetidas', 'Ningún n° de orden repetido.');

  // 4. OKX: misma compra/venta leída de la API y de la app sin unir (lo que pasó con la compra de 21 USDT del 16/11)
  var okx = ok.filter(function (o) { return o.ex === 'OKX' && o.f >= desde; });
  var pares = [];
  okx.filter(function (o) { return o.fuente === 'api'; }).forEach(function (a) {
    okx.forEach(function (b) {
      if (b.fuente === 'app' && b.tipo === a.tipo && b.cripto === a.cripto && Math.abs(b.cant - a.cant) < 0.005 &&
          Math.abs(a.f - b.f) <= 8 * 36e5) pares.push(a);
    });
  });
  if (pares.length) add('mal', 'OKX sin unir', pares.length + ' órdenes OKX que parecen estar dos veces, una de la API y otra de la app (filas ' + filas(pares) + ').');
  else add('ok', 'OKX sin unir', 'No hay órdenes OKX repetidas entre API y app.');

  // 5. Monto = cantidad × precio (si no, una columna se leyó mal)
  var raras = ciclo.filter(function (o) { return o.mon && o.precio && o.monto && Math.abs(o.cant * o.precio - o.monto) / o.monto > 0.02; });
  if (raras.length) add('mal', 'Monto = cantidad × precio', raras.length + ' órdenes donde no cierra (filas ' + filas(raras) + ').');
  else add('ok', 'Monto = cantidad × precio', 'Cierra en todas las órdenes del ciclo.');

  // 6. Fechas imposibles
  var futuras = ords.filter(function (o) { return o.f > new Date(ahora.getTime() + 36e5); });
  if (futuras.length) add('mal', 'Fechas', futuras.length + ' órdenes con fecha futura (filas ' + filas(futuras) + ').');

  // 7. Binance: mis órdenes como anunciante tienen n° de anuncio (si no, no se puede saber de qué anuncio son)
  var sinAd = ciclo.filter(function (o) { return o.ex === 'Binance' && o.rol === 'Anunciante' && !o.ad; });
  if (sinAd.length) add('ojo', 'Binance sin n° de anuncio', sinAd.length + ' órdenes (filas ' + filas(sinAd) + ').');

  // 8. Lo que debés, recalculado por otro camino (fila por fila, sin las funciones del tablero)
  var neto = 0;
  ciclo.forEach(function (o) { if (o.mon === 'UYU') neto += o.tipo === 'Venta' ? o.cant : -o.cant; });
  var dif = Math.abs(neto - salida.ciclo.pendiente);
  add(dif < 0.05 ? 'ok' : 'mal', 'Lo que debés (recálculo)', 'Tablero ' + salida.ciclo.pendiente + ' USDT, recálculo ' + Math.round(neto * 100) / 100 + ' USDT.');

  // 9. Precios en vivo de Binance: qué dijo el VPS (lo completa el VPS en data.json, acá solo si vino)
  var vivas = salida.anuncios.filter(function (a) { return a.ex === 'Binance'; });
  var enVivo = vivas.filter(function (a) { return a.fuente === 'vivo'; }).length;
  add(enVivo ? 'ok' : 'ojo', 'Binance en vivo', enVivo + ' de ' + vivas.length + ' filas de Binance con precio del listado; el resto es precio de la última orden.');

  // 10. Última orden por exchange (para comparar con lo que john sabe que hizo)
  ['Binance', 'Bybit', 'OKX'].forEach(function (ex) {
    var u = ords.filter(function (o) { return o.ex === ex; }).sort(function (a, b) { return b.f - a.f; })[0];
    if (u) add('ok', 'Última orden ' + ex, f(u.f) + ' · ' + u.tipo + ' ' + u.cant + ' ' + u.cripto + (u.mon ? ' · ' + u.monto + ' ' + u.mon : ' · sin moneda') + ' · ' + u.estado + ' (fila ' + u.fila + ')');
  });

  guardarRevisionBrujula_(r, ahora, zona);
  return r;
}

/** Deja la revisión en la hoja Revision_Brujula (se pisa cada vez). Si no puede escribir, no frena el tablero. */
function guardarRevisionBrujula_(r, ahora, zona) {
  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sh = ss.getSheetByName(HOJA_REVISION_BRUJULA) || ss.insertSheet(HOJA_REVISION_BRUJULA);
    var datos = [['Revisada ' + Utilities.formatDate(ahora, zona, 'dd/MM/yyyy HH:mm'), '', '']].concat(
      [['Estado', 'Prueba', 'Detalle']], r.map(function (x) { return [x.estado, x.prueba, x.detalle]; }));
    sh.clearContents();
    sh.getRange(1, 1, datos.length, 3).setValues(datos);
  } catch (e) {
    logError_('guardarRevisionBrujula_', e.message || e);
  }
}
