/**
 * 24_RemesasBrujula.gs — Separa las órdenes de la Brújula en ARBITRAJE (por moneda) y REMESAS (clientes BEXO).
 *
 * Remesa = el cliente te manda pesos (Movimientos, CONTADO, ARS) y le pagás los Bs con una VENTA de USDT en VES:
 * el comprador le deposita directo al cliente. Esa venta da casi exacto pesos × tasa neta (hoja Tasas) unas horas
 * después del comprobante (26/11: Aniusca 23.800 × 0,575 = 13.685 → venta de 13.800 Bs). Se une si da ±3%, desde
 * 1 h antes hasta 48 h después; si no da con una venta, se prueba con dos (el pago partido en dos órdenes).
 *
 *   VES  venta unida a un cliente → remesa · compra → arbitraje VES · venta sin cliente después de una compra en VES
 *        → arbitraje VES (hasta lo comprado) · el resto de las ventas sin cliente → remesa, listadas en "sinUnir"
 *        (a veces pagás desde tus cuentas MR/MJ con Bs de remesas al revés, y ese cliente no tiene venta).
 *   ARS  compra → repone remesas, salvo lo que hace falta para tus ventas en ARS (arbitraje ARS).
 *   UYU  todo arbitraje.
 *   COP, PEN, USD y otras: venta → remesa (no hay tasa para unirlas) · compra → arbitraje de esa moneda.
 * Si no puedo leer Movimientos o Tasas, todas las ventas VES cuentan como remesa (como antes) y se avisa.
 */
var REM_TOLERANCIA = 0.03;
var REM_ANTES_MS = 36e5, REM_DESPUES_MS = 48 * 36e5;

/** Clientes BEXO que mandaron pesos: [{f, ars, nombre, fila}] de Movimientos (CONTADO, ARS). null si no se puede leer. */
function dashLeerClientesRemesa_(desde, ahora) {
  try {
    var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Movimientos');
    if (!sh || sh.getLastRow() < 2) return null;
    var v = sh.getDataRange().getValues();
    var h = {};
    v[0].forEach(function (n, i) { h[String(n).trim()] = i; });
    if (h['Estado'] === undefined || h['Monto'] === undefined || h['Moneda'] === undefined) return null;
    var meses = { ene: 0, feb: 1, mar: 2, abr: 3, may: 4, jun: 5, jul: 6, ago: 7, sep: 8, oct: 9, nov: 10, dic: 11 };
    var conAnio = function (mes, dia, hh, mm) {   // "27/11 19:36" sin año: el más cercano hacia atrás
      var d = new Date(ahora.getFullYear(), mes, dia, hh || 0, mm || 0);
      if (d - ahora > 7 * 864e5) d.setFullYear(d.getFullYear() - 1);
      return d;
    };
    var lista = [];
    v.slice(1).forEach(function (r, i) {
      if (String(r[h['Estado']]).trim() !== 'CONTADO' || String(r[h['Moneda']]).trim() !== 'ARS') return;
      var ars = dashNum_(r[h['Monto']]);
      if (!(ars > 0)) return;
      // La hora más precisa: cuándo se mandó la orden ("ENVIADA 27/11 19:36"); si no, el día que llegó.
      var f = null;
      var m = String(h['Orden P2P'] !== undefined ? r[h['Orden P2P']] : '').match(/(\d{1,2})\/(\d{1,2})\s+(\d{1,2}):(\d{2})/);
      if (m) f = conAnio(+m[2] - 1, +m[1], +m[3], +m[4]);
      var rec = r[h['Recibido']];
      if (!f && rec instanceof Date) f = rec;
      if (!f) {
        var t = String(rec || '').toLowerCase().match(/(\d{1,2})\s+([a-z]{3})/);
        if (t && meses[t[2]] !== undefined) f = conAnio(meses[t[2]], +t[1], 12, 0);
      }
      if (!f || f < new Date(desde.getTime() - 2 * 864e5)) return;
      lista.push({ f: f, ars: ars, nombre: String(r[h['Nombre']] || ''), fila: i + 2 });
    });
    return lista;
  } catch (e) {
    logError_('dashLeerClientesRemesa_', e.message || e);
    return null;
  }
}

/** Tasa neta (Bs por peso que le das al cliente) de cada lectura de la hoja Tasas: [{f, neta}] de la más vieja a la más nueva. */
function dashLeerTasasNeta_() {
  try {
    var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Tasas');
    if (!sh || sh.getLastRow() < 2) return null;
    var v = sh.getDataRange().getValues();
    var iF = v[0].indexOf('Fecha'), iN = v[0].indexOf('Tasa neta');
    if (iF < 0 || iN < 0) return null;
    return v.slice(1).map(function (r) { return { f: dashFecha_(r[iF]), neta: +r[iN] || 0 }; })
      .filter(function (x) { return x.f && x.neta > 0 && x.neta < 5; })
      .sort(function (a, b) { return a.f - b.f; });
  } catch (e) {
    logError_('dashLeerTasasNeta_', e.message || e);
    return null;
  }
}

function dashNetaEn_(tasas, f) {
  var neta = 0;
  for (var i = 0; i < tasas.length; i++) { if (tasas[i].f <= f) neta = tasas[i].neta; else break; }
  return neta || (tasas.length ? tasas[0].neta : 0);
}

/** ok = órdenes completadas. Devuelve {vueltas: [...], sinUnir: {n, usdt, filas}, unidos, clientes, aviso}. */
function dashClasificarRemesas_(ok, desde, clientes, tasas) {
  var ciclo = ok.filter(function (o) { return o.f >= desde && o.mon; });
  var vesVentas = ciclo.filter(function (o) { return o.mon === 'VES' && o.tipo === 'Venta'; })
    .sort(function (a, b) { return a.f - b.f; });
  var unida = {}, unidos = 0, aviso = '';
  var puedeUnir = clientes && tasas && tasas.length;
  if (puedeUnir) {
    // Busca 1, 2 o 3 ventas libres que sumen lo esperado (±3%) en la ventana del pago. Devuelve las ventas o null.
    var buscar = function (esp, t, n) {   // n = cuántas ventas como máximo
      var cand = vesVentas.filter(function (o) { return !unida[o.fila] && o.f >= t - REM_ANTES_MS && o.f <= t.getTime() + REM_DESPUES_MS; });
      var mejor = null, dif = REM_TOLERANCIA, k = cand.length;
      var probar = function (lista) {
        var tot = lista.reduce(function (x, o) { return x + o.monto; }, 0), d = Math.abs(tot - esp) / esp;
        if (d <= dif) { dif = d; mejor = lista; }
      };
      for (var i = 0; i < k; i++) probar([cand[i]]);
      if (!mejor && n >= 2) for (var i2 = 0; i2 < k; i2++) for (var j = i2 + 1; j < k; j++) probar([cand[i2], cand[j]]);
      if (!mejor && n >= 3 && k <= 25) for (var x = 0; x < k; x++) for (var y = x + 1; y < k; y++) for (var z = y + 1; z < k; z++) probar([cand[x], cand[y], cand[z]]);
      return mejor;
    };
    var unir = function (lista, nombre) { lista.forEach(function (o) { unida[o.fila] = nombre; }); };
    // Por pasadas, de lo más seguro a lo menos, para que una combinación de varias ventas no le robe la venta
    // exacta a otro cliente: 1) una venta, 2) el mismo cliente con varios comprobantes en 24 h pagados juntos
    // (14/11: dos de 150.000 ARS → 50.300 + 126.700 Bs), 3) dos ventas, 4) tres ventas.
    var libres = clientes.slice().sort(function (a, b) { return a.f - b.f; });
    var pasada = function (n) {
      libres = libres.filter(function (c) {
        var neta = dashNetaEn_(tasas, c.f), v = neta ? buscar(c.ars * neta, c.f, n) : null;
        if (v) { unir(v, c.nombre); unidos++; return false; }
        return true;
      });
    };
    pasada(1);
    var hechos = [];
    libres.forEach(function (c, i) {
      if (hechos.indexOf(c) >= 0) return;
      var grupo = libres.filter(function (d, j) { return j >= i && hechos.indexOf(d) < 0 && d.nombre === c.nombre && d.f - c.f <= 864e5; });
      if (grupo.length < 2) return;
      var esp = grupo.reduce(function (x, g) { return x + g.ars * dashNetaEn_(tasas, g.f); }, 0);
      var v = buscar(esp, c.f, 2);
      if (v) { unir(v, c.nombre); unidos += grupo.length; hechos = hechos.concat(grupo); }
    });
    libres = libres.filter(function (c) { return hechos.indexOf(c) < 0; });
    pasada(2);
    pasada(3);
  } else {
    aviso = 'No pude leer Movimientos o Tasas: cuento todas las ventas en Bs como remesa.';
  }

  var arb = {}, rem = { entro: 0, salio: 0, n: 0, destinos: {} }, sueltas = [], arsCompras = [];
  var a0 = function (m) { return arb[m] || (arb[m] = { entro: 0, salio: 0, n: 0 }); };
  var dest = function (o) {
    rem.salio += o.cant; rem.n++;
    var d = rem.destinos[o.mon] || (rem.destinos[o.mon] = { moneda: o.mon, usdt: 0, ordenes: 0 });
    d.usdt += o.cant; d.ordenes++;
  };
  ciclo.forEach(function (o) {
    var compra = o.tipo === 'Compra';
    if (o.mon === 'UYU') { var u = a0('UYU'); if (compra) u.entro += o.cant; else u.salio += o.cant; u.n++; }
    else if (o.mon === 'VES') {
      if (compra) { a0('VES').entro += o.cant; arb.VES.n++; }
      else if (!puedeUnir || unida[o.fila]) dest(o);
      else sueltas.push(o);
    } else if (o.mon === 'ARS') {
      if (compra) arsCompras.push(o); else { a0('ARS').salio += o.cant; arb.ARS.n++; }
    } else if (compra) { a0(o.mon).entro += o.cant; arb[o.mon].n++; }
    else dest(o);
  });
  // Ventas en Bs sin cliente: las que vienen después de una compra en VES (hasta esa cantidad) son arbitraje VES;
  // el resto cuenta como remesa (casi todas lo son: hay clientes que no se encuentran porque les pagaste desde tus
  // cuentas MR/MJ o con otra tasa) y se listan en "sinUnir" para poder revisarlas.
  var comprasVes = ciclo.filter(function (o) { return o.mon === 'VES' && o.tipo === 'Compra'; }).sort(function (a, b) { return a.f - b.f; });
  var sinUnir = [], usadaArb = {};
  comprasVes.forEach(function (c) {
    var cupo = c.cant;
    sueltas.slice().sort(function (a, b) { return a.f - b.f; }).forEach(function (o) {
      if (cupo <= 0 || usadaArb[o.fila] || o.f < c.f) return;
      usadaArb[o.fila] = true; arb.VES.salio += o.cant; arb.VES.n++; cupo -= o.cant;
    });
  });
  sueltas.forEach(function (o) { if (!usadaArb[o.fila]) { dest(o); sinUnir.push(o); } });
  // Compras con ARS: primero cubren tus ventas en ARS (arbitraje ARS), el resto repone las remesas.
  var cupoA = arb.ARS ? arb.ARS.salio : 0;
  arsCompras.forEach(function (o) {
    if (cupoA > 0) { arb.ARS.entro += o.cant; arb.ARS.n++; cupoA -= o.cant; } else { rem.entro += o.cant; rem.n++; }
  });

  var vuelta = function (nombre, cuenta, x, como) {
    return { nombre: nombre, cuenta: cuenta, vendido: dashR_(x.salio), repuesto: dashR_(x.entro), falta: dashR_(x.salio - x.entro), ordenes: x.n, como: como };
  };
  var vueltas = Object.keys(arb).filter(function (m) { return arb[m].n; })
    .sort(function (a, b) { return (b === 'UYU') - (a === 'UYU') || (arb[b].entro + arb[b].salio) - (arb[a].entro + arb[a].salio); })
    .map(function (m) { return vuelta('Arbitraje ' + m, m, arb[m], 'recompraste|con ' + m); });
  if (rem.n) {
    var ds = Object.keys(rem.destinos).map(function (k) { return rem.destinos[k]; }).sort(function (a, b) { return b.usdt - a.usdt; });
    var v = vuelta('Remesas', 'ARS → ' + ds.map(function (d) { return d.moneda; }).join(', '), rem, 'repusiste|con ARS');
    v.destinos = ds.map(function (d) { return { moneda: d.moneda, usdt: dashR_(d.usdt), ordenes: d.ordenes }; });
    if (puedeUnir) v.clientes = { unidos: unidos, total: clientes.filter(function (c) { return c.f >= desde; }).length };
    vueltas.push(v);
  }
  return {
    vueltas: vueltas, aviso: aviso,
    sinUnir: { n: sinUnir.length, usdt: dashR_(sinUnir.reduce(function (s, o) { return s + o.cant; }, 0)),
               filas: sinUnir.slice(0, 8).map(function (o) { return o.fila; }) }
  };
}
