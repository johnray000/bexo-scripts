// ==========================================
// 13_CuentasVes.gs — COMPROBANTES EN BOLÍVARES A TUS CUENTAS DE VENEZUELA (la otra ruta: Bs → ARS)
//
// 1. completarVes_ (después de cada lectura y en refrescarTodo): si falta la Moneda y la cuenta es argentina, o dice
//    "Pesos" / "$", pone ARS.
//    A las filas de Movimientos en bolívares les
//    pone Moneda VES, reconoce la cuenta (MJ, MR, PMJ, PMR) desde lo que leyó DeepSeek (columna Raw_JSON) y,
//    si quedó en REVISAR por la cuenta, pasa a LEIDO. Completa dos columnas al final:
//      Tasa = tasa bruta del día (hoja Tasas, columna "Tasa", la última lectura antes de que llegara el comprobante)
//      ARS  = Bs ÷ Tasa × FACTOR_VES   (la cuenta que John hacía a mano para cargarlo como efectivo)
//    La Tasa queda fija; el ARS se recalcula si corregís el monto.
// 2. Pre-orden Bs (11_PreOrden.gs la manda): cuánto le transferís en ARS, simple. Página con Confirmar / Deshacer.
// 3. bloqueVes_ (refrescarTodo, después de construirDashboard): bloque "CUENTAS VES" a la derecha de los recientes
//    con los Bs por mes de cada cuenta (últimos 3 meses). Los pesos (ARS con el 10%) suman arriba, en la fila VES
//    de la tabla (5_Dashboard.gs), y así entran al TOTAL.
// No se carga como efectivo (E): una sola fila por comprobante.
// Usa de otros archivos: hojaMovimientos_, C, MAPA_CUENTAS, E_LEID, E_REVI, E_CONT (4), colEncabezado_, colOrden_, PRE_APROBADA,
// miniaturaComprobante_, escHtml_ (11), soloDigitos_ (10), fmtN_, fmtM_, HOJA_TASAS (9), MESES_PANEL, TZ, BG, HEAD,
// TXT, MUDO, esCliente_ (5), nombreMes_ (3), logError_ (2). No toca el prompt de DeepSeek (4).
// ==========================================
var FACTOR_VES = 1.10;   // ARS = Bs ÷ tasa bruta × 1,10
var COL_TASA_VES = 'Tasa';
var COL_ARS_VES = 'ARS';

// Tus cuentas en Venezuela. cuenta = últimos 4 del número de cuenta; tel = últimos 4 del teléfono de Pago Móvil;
// ci = cédula del titular (se usa solo si no aparece ni cuenta ni teléfono).
var CUENTAS_VE = {
  MJ:  { cuenta: '0698' },
  MR:  { cuenta: '1238' },
  PMJ: { tel: '2961', ci: '14650493' },
  PMR: { tel: '8341', ci: '16113797' }
};

function esMonedaVes_(m) {
  return /^(ves|vef|ved|bs\.?\s*s?\.?|bs\.?f?|bol[ií]vares?)$/i.test(String(m || '').trim());
}

/** Cuenta argentina: una de las de MAPA_CUENTAS (4_LeerComprobantes.gs). */
function esCuentaArs_(c) {
  c = String(c || '').trim();
  if (!c) return false;
  for (var k in MAPA_CUENTAS) if (MAPA_CUENTAS[k] === c) return true;
  return false;
}

function esCuentaVe_(c) {
  return CUENTAS_VE.hasOwnProperty(String(c || '').trim());
}

/**
 * Cuenta de Venezuela a partir de lo que leyó DeepSeek (p = el JSON de Raw_JSON). null si no es ninguna tuya.
 * El prompt de DeepSeek no se toca: el número puede venir en destino_identificador, titular_destino u otro campo,
 * así que se buscan teléfonos (04xx + 7) y cuentas (01xx + 16) en todos los campos menos los del que paga.
 * 1) número de cuenta: últimos 4 (también enmascarado, 0134****1238).  2) teléfono: últimos 4 (0416-470.2961,
 * +58 416..., 0416***2961).  3) cédula, solo si viene destino_cedula. La cédula va última porque las
 * transferencias a MJ/MR también traen tu cédula.
 */
function cuentaVe_(p) {
  if (!p) return null;
  var cods = Object.keys(CUENTAS_VE), i, v;
  var porCuenta = function (fin) {
    for (var j = 0; j < cods.length; j++) if (CUENTAS_VE[cods[j]].cuenta === fin) return cods[j];
    return null;
  };
  var porTel = function (fin) {
    for (var j = 0; j < cods.length; j++) if (CUENTAS_VE[cods[j]].tel === fin) return cods[j];
    return null;
  };
  var raw = String(p.destino_identificador || ''), dig = soloDigitos_(raw);
  // a) destino_identificador: cuenta (16+ dígitos, marcada CUENTA o enmascarada) o teléfono
  if (dig.length >= 16 || /cuenta/i.test(p.destino_tipo || '') || /^\s*01\d\d[\s-]*[*x]/i.test(raw)) {
    return porCuenta(dig.slice(-4));   // es un número de cuenta: tuya o de nadie
  }
  if (dig.length >= 7 && porTel(dig.slice(-4))) return porTel(dig.slice(-4));
  // b) el resto de los campos (menos los del que paga): cuentas y teléfonos con su forma completa
  var texto = Object.keys(p).filter(function (k) { return !/origen|referencia|monto|fecha|confianza/i.test(k); })
    .map(function (k) { return typeof p[k] === 'string' ? p[k] : ''; }).join(' | ');
  var cta = texto.match(/\b01\d\d(?:[-\s.]?\d){16}\b/);
  if (cta) return porCuenta(soloDigitos_(cta[0]).slice(-4));
  var re = /(?:\+?58|0)?\s*\(?4(?:12|14|16|22|24|26)\)?[-\s.*x]*(?:\d|[*x]){3}[-\s.*x]*(\d{4})\b/gi, m;
  while ((m = re.exec(texto))) if (porTel(m[1])) return porTel(m[1]);
  // c) cédula de quien recibe (solo si DeepSeek la trae aparte)
  var ciTxt = String(p.destino_cedula || ''), ci = soloDigitos_(ciTxt);
  var mask = /[*x]/i.test(ciTxt);
  for (i = 0; ci.length >= 3 && i < cods.length; i++) {
    v = CUENTAS_VE[cods[i]];
    if (v.ci && (ci === v.ci || (mask && v.ci.slice(-3) === ci.slice(-3)))) return cods[i];
  }
  return null;
}

/** Tasas: [{fecha, tasa}] de la hoja Tasas (la más nueva primero), columna "Tasa" (bruta). */
function leerTasasBrutas_() {
  var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(HOJA_TASAS);
  if (!sh || sh.getLastRow() < 2) return [];
  var datos = sh.getDataRange().getValues();
  var head = datos[0].map(function (h) { return String(h).trim(); });
  var cF = head.indexOf('Fecha'), cT = head.indexOf('Tasa');
  if (cF === -1 || cT === -1) return [];
  return datos.slice(1).filter(function (f) { return f[cF] instanceof Date && Number(f[cT]) > 0; })
    .map(function (f) { return { fecha: f[cF], tasa: Number(f[cT]) }; })
    .sort(function (a, b) { return b.fecha - a.fecha; });
}

/** Tasa bruta vigente cuando llegó el comprobante: la última lectura anterior (o la más vieja que haya). */
function tasaBrutaPara_(fecha, tasas) {
  if (!tasas.length) return 0;
  var t = fecha instanceof Date ? fecha.getTime() : Date.now();
  for (var i = 0; i < tasas.length; i++) if (tasas[i].fecha.getTime() <= t) return tasas[i].tasa;
  return tasas[tasas.length - 1].tasa;
}

/** Lo que le transferís al cliente: Bs ÷ tasa, sin el 10%. */
function arsTransferir_(bs, tasa) {
  return tasa > 0 ? Math.round(bs / tasa) : 0;
}

/** Lo que se anota en la columna ARS (y suma en el Dashboard): Bs ÷ tasa × 1,10. */
function arsDeBs_(bs, tasa) {
  return tasa > 0 ? Math.round(bs / tasa * FACTOR_VES) : 0;
}

/** Completa las filas en bolívares (ver arriba). Solo escribe lo que cambia. Si una fila falla, sigue con las demás. */
function completarVes_() {
  var sh = hojaMovimientos_();
  if (sh.getLastRow() < 2) return;
  var colT = colEncabezado_(sh, COL_TASA_VES), colA = colEncabezado_(sh, COL_ARS_VES);
  var datos = sh.getRange(2, 1, sh.getLastRow() - 1, Math.max(sh.getLastColumn(), colA)).getValues();
  var cache = { tasas: null };
  for (var i = 0; i < datos.length; i++) {
    // DeepSeek a veces no trae la moneda: si la cuenta es argentina (MAPA_CUENTAS), es ARS. Sin esto no sale la
    // pre-orden ni suma en el Dashboard (los dos piden Moneda = ARS).
    // "Pesos", "$", "ars"…: se deja como ARS, que es lo que miran la pre-orden y el Dashboard
    var mon = String(datos[i][C.MONEDA - 1]).trim();
    if (mon !== 'ARS' && /^(\$|ars|pesos?( argentinos?)?)$/i.test(mon)) {
      try { sh.getRange(i + 2, C.MONEDA).setValue('ARS'); }
      catch (e) { logError_('VES', 'fila ' + (i + 2) + ' | ' + (e.message || e)); }
      continue;
    }
    if (!mon && esCuentaArs_(datos[i][C.CUENTA - 1])) {
      try { sh.getRange(i + 2, C.MONEDA).setValue('ARS'); }
      catch (e) { logError_('VES', 'fila ' + (i + 2) + ' | ' + (e.message || e)); }
      continue;
    }
    if (!esMonedaVes_(datos[i][C.MONEDA - 1])) continue;
    try { completarFilaVes_(sh, datos[i], i + 2, colT, colA, cache); }
    catch (e) { logError_('VES', 'fila ' + (i + 2) + ' | ' + (e.message || e)); }
  }
}

function completarFilaVes_(sh, d, fila, colT, colA, cache) {
  if (d[C.MONEDA - 1] !== 'VES') sh.getRange(fila, C.MONEDA).setValue('VES');
  // Sin cuenta, o con una argentina que 4_LeerComprobantes adivinó por los últimos 4: se busca entre las de Venezuela
  if (!esCuentaVe_(d[C.CUENTA - 1])) {
    var p = null;
    try { p = JSON.parse(d[C.RAW - 1] || 'null'); } catch (e) { p = null; }
    var cod = cuentaVe_(p);
    if (cod) {
      sh.getRange(fila, C.CUENTA).setValue(cod);
      // Quedó en REVISAR solo porque no se reconoció la cuenta: ahora sí es LEIDO
      if (d[C.ESTADO - 1] === E_REVI && Number(d[C.CONFIANZA - 1]) >= 0.8 && Number(d[C.MONTO - 1]) > 0) {
        sh.getRange(fila, C.ESTADO).setValue(E_LEID);
      }
    }
  }
  var bs = Number(d[C.MONTO - 1]) || 0;
  if (!(bs > 0)) return;
  var tasa = Number(d[colT - 1]) || 0;
  if (!tasa) {
    cache.tasas = cache.tasas || leerTasasBrutas_();
    tasa = tasaBrutaPara_(d[C.RECIBIDO - 1], cache.tasas);
    if (!tasa) { logError_('VES', 'Sin tasa en la hoja Tasas para la fila ' + fila); return; }
    sh.getRange(fila, colT).setValue(tasa);
  }
  var ars = arsDeBs_(bs, tasa);
  if (Number(d[colA - 1]) !== ars) sh.getRange(fila, colA).setValue(ars);
}

/** ARS de una fila en Bs con un monto nuevo (lo usa Confirmar cuando corregís el monto). */
function recalcularArsFila_(sh, fila, bs) {
  var colT = colEncabezado_(sh, COL_TASA_VES), colA = colEncabezado_(sh, COL_ARS_VES);
  var tasa = Number(sh.getRange(fila, colT).getValue()) || 0;
  if (tasa) sh.getRange(fila, colA).setValue(arsDeBs_(bs, tasa));
}

// ---------- Pre-orden Bs ----------

/** Mensaje de la pre-orden Bs: cuánto transferir en ARS (sin el 10%) y cuánto se anota (con el 10%). n = {id, nombre, monto (Bs), cuentaMov, tasa, ars}. */
function mensajePreOrdenVes_(n) {
  return [
    '*' + n.nombre + '* · Transferir *' + fmtM_(arsTransferir_(n.monto, n.tasa), 0, true) + ' ARS*',
    'recibido ' + fmtM_(n.monto, 0) + ' Bs en ' + n.cuentaMov + ' ÷ ' + fmtM_(n.tasa, 3),
    'se anota ' + fmtM_(n.ars, 0) + ' ARS (+10%)',
    '',
    'Confirmar:',
    linkPreOrden_(n.id)
  ].join('\n');
}

/** Página simple de la pre-orden Bs: TRANSFERIR EN ARS grande, lo recibido en Bs chico, Confirmar / Deshacer. */
function paginaPreOrdenVes_(p, sh, r, col) {
  var esc = escHtml_;
  var d = r.datos, orden = String(d[col - 1] || '');
  var aprobada = orden.indexOf(PRE_APROBADA) === 0;
  var bs = Number(d[C.MONTO - 1]) || 0;
  var tasa = Number(d[colEncabezado_(sh, COL_TASA_VES) - 1]) || tasaBrutaPara_(d[C.RECIBIDO - 1], leerTasasBrutas_());
  var foto = miniaturaComprobante_(d[C.DRIVE_ID - 1]);
  var css =
    '<style>body{margin:0;background:#f2f4f7;font-family:-apple-system,Roboto,sans-serif;color:#1d2433}' +
    '.w{max-width:520px;margin:0 auto;padding:10px}' +
    '.c{background:#fff;border-radius:14px;padding:10px 14px;margin-bottom:10px;box-shadow:0 1px 3px rgba(0,0,0,.08)}' +
    'h1{font-size:18px;margin:0}.s{color:#6b7280;font-size:12px}.t{font-size:12px;font-weight:700;letter-spacing:.05em;margin:0}' +
    '.out{border-left:6px solid #2563eb;padding:14px}.out .t{color:#2563eb}' +
    '.big{font-size:40px;font-weight:800;color:#1e3a8a;margin:2px 0 0;line-height:1.1}.big small{font-size:22px;font-weight:700}' +
    '.calc{color:#6b7280;font-size:13px;margin:2px 0 0}' +
    '.in{background:#f8fafc;box-shadow:none;border:1px solid #e5e7eb}.in .t{color:#9ca3af}' +
    '.sm{font-size:17px;font-weight:600;color:#6b7280;margin:2px 0 0}' +
    '.cta{font-size:12px;font-weight:600;color:#6b7280;background:#e5e7eb;border-radius:6px;padding:1px 7px;margin-left:6px}' +
    '.rc{display:flex;justify-content:space-between;align-items:flex-start;gap:10px}' +
    '.th{width:60px;height:80px;object-fit:cover;object-position:top;border-radius:6px;border:1px solid #d0d5dd;flex:none}' +
    '#zz{display:none;position:fixed;inset:0;background:rgba(0,0,0,.88);z-index:9;padding:10px;box-sizing:border-box}' +
    '#zz img{width:100%;height:100%;object-fit:contain}.row{display:flex;gap:8px;align-items:center;margin-top:8px}' +
    'input{flex:1;min-width:0;font-size:16px;color:#4b5563;padding:7px 9px;border:1px solid #d0d5dd;border-radius:10px}' +
    '.b{width:100%;font-size:18px;padding:12px;border:0;border-radius:12px;background:#1f7a4d;color:#fff;margin-top:8px}' +
    '.b3{background:#fff;color:#b42318;border:2px solid #f3b5ae;font-size:15px}.b:disabled{opacity:.5}' +
    '.ok{font-size:15px;color:#1f7a4d;margin:6px 0 0}.err{color:#b42318}</style>';
  var html = '<meta name="viewport" content="width=device-width,initial-scale=1">' + css + '<div class="w">' +
    '<div class="c"><h1>' + esc(d[C.NOMBRE - 1] || d[C.TELEFONO - 1]) + '</h1>' +
    '<div class="s" id="est">' + esc(d[C.ESTADO - 1]) + (orden ? ' · ' + esc(orden) : '') + '</div></div>' +
    '<div class="c out"><p class="t">TRANSFERIR EN ARS</p>' +
    '<div class="big"><span id="ars">' + fmtN_(arsTransferir_(bs, tasa), 0) + '</span> <small>ARS</small></div>' +
    '<p class="calc" id="calc">= ' + fmtN_(bs, 0) + ' Bs ÷ ' + fmtN_(tasa, 3) + '</p>' +
    '<p class="calc">Se anota en la hoja: <b id="ano">' + fmtN_(arsDeBs_(bs, tasa), 0) + '</b> ARS (+10%)</p></div>' +
    '<div class="c in rc"><div style="flex:1;min-width:0"><p class="t">RECIBIDO EN BS</p>' +
    '<div class="sm"><span id="mv">' + fmtN_(bs, 0) + '</span> Bs<span class="cta">' + esc(d[C.CUENTA - 1]) + '</span></div>' +
    '<div class="row"><span class="s">¿Mal leído?</span><input id="m" type="number" inputmode="decimal" value="' + esc(bs || '') + '"' +
    (aprobada ? ' disabled' : '') + '></div></div>' +
    (foto ? '<img class="th" src="' + foto + '" alt="comprobante" onclick="zz.style.display=\'block\'">' : '') + '</div>' +
    (foto ? '<div id="zz" onclick="this.style.display=\'none\'"><img src="' + foto + '" alt="comprobante"></div>' : '') +
    '<button type="button" class="b" id="ok"' + (aprobada ? ' style="display:none"' : '') + '>✅ Confirmar (pasa a CONTADO)</button>' +
    '<button type="button" class="b b3" id="un"' + (aprobada ? '' : ' style="display:none"') + '>↩️ Deshacer y corregir</button>' +
    '<p id="r" class="ok"></p></div>' +
    '<script>var T=' + tasa + ',F=' + FACTOR_VES + ',TT=' + JSON.stringify(fmtN_(tasa, 3)) + ',K=' + JSON.stringify(p.k) +
    ',MOV=' + JSON.stringify(p.mov || p.id) + ';function $(i){return document.getElementById(i);}var m=$("m");' +
    'function f(n){return Math.round(n).toLocaleString("es-AR");}' +
    'm.oninput=function(){var v=Number(m.value)||0;$("mv").textContent=f(v);$("calc").textContent="= "+f(v)+" Bs ÷ "+TT;$("ars").textContent=f(v/T);$("ano").textContent=f(v/T*F);};' +
    'function msg(x,e){$("r").className=e?"ok err":"ok";$("r").textContent=x;}' +
    'function run(b,fn,args,ok){b.disabled=true;msg("...");var g=google.script.run.withSuccessHandler(function(x){b.disabled=false;ok(x);})' +
    '.withFailureHandler(function(e){b.disabled=false;msg("Error: "+e.message,true);});g[fn].apply(g,args);}' +
    'function modo(a){$("ok").style.display=a?"none":"";$("un").style.display=a?"":"none";m.disabled=a;}' +
    '$("ok").onclick=function(){run(this,"confirmarPreOrdenWeb",[K,MOV,Number(m.value),"",""],function(x){$("est").textContent=x.estado;modo(true);msg(x.msg);});};' +
    '$("un").onclick=function(){run(this,"deshacerPreOrdenWeb",[K,MOV],function(x){$("est").textContent=x.estado;modo(false);msg(x.msg);});};' +
    '</script>';
  return HtmlService.createHtmlOutput(html).setTitle('Pre-orden Bs');
}

// ---------- Dashboard ----------

/**
 * Bloque CUENTAS VES a la derecha de MOVIMIENTOS RECIENTES: solo Bs, para seguir lo que entra a tus 4 cuentas.
 * Columnas: J cuenta, K-M los últimos MESES_VES meses (el actual primero, como la tabla). Sin total por cuenta.
 * Los pesos (columna ARS, con el 10%) van arriba, en la fila VES de la tabla de 5_Dashboard.gs.
 * Si no encuentra los recientes, lo pone debajo de todo. construirDashboard borra la hoja antes, así que no se acumula.
 */
var MESES_VES = 3;
function bloqueVes_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var dash = ss.getSheetByName('Dashboard');
  var sh = hojaMovimientos_();
  if (!dash || sh.getLastRow() < 2) return;
  var nm = Math.min(MESES_VES, MESES_PANEL);
  var hoy = new Date(), meses = [], claves = [];
  for (var k = 0; k < nm; k++) {
    meses.push(new Date(hoy.getFullYear(), hoy.getMonth() - k, 1));
    claves.push(Utilities.formatDate(meses[k], TZ, 'yyyy-MM'));
  }
  var cods = Object.keys(CUENTAS_VE), bs = {};
  cods.forEach(function (c) { bs[c] = claves.map(function () { return 0; }); });
  var datos = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();
  datos.forEach(function (d) {
    var c = String(d[C.CUENTA - 1]).trim(), f = d[C.RECIBIDO - 1];
    if (d[C.ESTADO - 1] !== E_CONT || d[C.MONEDA - 1] !== 'VES' || !bs[c] || !(f instanceof Date)) return;
    if (!esCliente_(String(d[C.NOMBRE - 1] || '').trim())) return;   // como el resto del Dashboard: solo Bexo
    var j = claves.indexOf(Utilities.formatDate(f, TZ, 'yyyy-MM'));
    if (j !== -1) bs[c][j] += Number(d[C.MONTO - 1]) || 0;
  });

  var colB = dash.getRange(1, 2, Math.max(dash.getLastRow(), 1), 1).getValues();
  var fRec = -1;
  for (var i = 0; i < colB.length; i++) if (colB[i][0] === 'MOVIMIENTOS RECIENTES') { fRec = i + 1; break; }

  var fila = function (nombre, vals) { return [nombre].concat(vals); };
  var filas = [['Cuenta'].concat(meses.map(function (m) { return nombreMes_(m); }))];
  cods.forEach(function (c) { filas.push(fila(c, bs[c])); });
  filas.push(fila('Total Bs', claves.map(function (x, j) { return cods.reduce(function (s, c) { return s + bs[c][j]; }, 0); })));

  var c0 = 10, ancho = filas[0].length, n = filas.length;   // J
  var f0 = fRec > 0 ? fRec : dash.getLastRow() + 2;
  dash.getRange(f0, c0).setValue('CUENTAS VES (Bs)').setFontSize(9).setFontWeight('bold').setFontColor('#ffffff');
  var t = f0 + 1;   // encabezados, a la altura de los de recientes
  var rg = dash.getRange(t, c0, n, ancho);
  rg.setBackground(BG).setFontColor(TXT).setFontFamily('Roboto').setFontSize(8);
  dash.getRange(t, c0, 1, ancho).setNumberFormat('@');   // "Oct 26" queda como texto, no como fecha
  rg.setValues(filas);
  dash.getRange(t + 1, c0 + 1, n - 1, ancho - 1).setNumberFormat('#,##0');
  dash.getRange(t, c0 + 1, n, ancho - 1).setHorizontalAlignment('right');
  dash.getRange(t, c0, 1, ancho).setBackground(HEAD).setFontColor(MUDO).setFontWeight('bold');
  dash.getRange(t + 1, c0, cods.length, 1).setFontWeight('bold').setFontColor('#ffffff');
  dash.getRange(t + n - 1, c0, 1, ancho).setFontWeight('bold').setBackground(HEAD);
}
