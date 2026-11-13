// ==========================================
// MÓDULO 5: DASHBOARD ESTÁTICO (solo ARS)
// Reemplaza por completo al anterior.
//
// No escribe NINGUNA fórmula: el script calcula y
// escribe números. Abre instantáneo en el teléfono.
//
// Se refresca de tres formas:
//   - checkbox en B3 del Dashboard (funciona en el móvil)
//   - trigger horario -> refrescarTodo()
//   - menú de la compu
// ==========================================

var CUENTAS_DASH = ['LJ','CDJ','E','VES','RBJ','APJ','BLJ','PPJ','NJ','PXJ','BBD','UJ','BBJ','UD','APB','BTJ','G66J','ARQJ'];
var MONEDA_DASH  = 'ARS';
var MESES_PANEL  = 6;
var TZ           = 'GMT-3';

// Columnas de Movimientos (1-indexadas)
// Columnas de Movimientos: se toman de C (4_LeerComprobantes.gs), así este archivo
// no cambia si algún día movés Cuenta y Moneda.

// Paleta
var BG    = '#0f1c2e';
var HEAD  = '#1b3049';
var TXT   = '#e8eef5';
var MUDO  = '#8da2b8';
var VERDE = '#2ee6a8';
var AMBAR = '#f5a524';
var ROJO  = '#ff5c5c';
var GRIS  = '#2b3f57';
var ORO   = '#f5c542';   // fila VES (Bs en pesos)
var ORO_BG = '#2a2614';
// Filas sin límite: cada una con su color, para distinguirlas de un vistazo
var SIN_LIMITE_COLOR = {
  E:   { txt: '#c4a7ff', bg: '#211a38', est: '#3a2c63' },   // efectivo: violeta
  VES: { txt: ORO,       bg: ORO_BG,    est: '#4a3d12' }    // Bs → ARS: dorado
};
function colorSinLimite_(c) { return SIN_LIMITE_COLOR[c] || SIN_LIMITE_COLOR.E; }

// ==========================================
// LÍMITES MENSUALES POR CUENTA (en ARS)
// Reemplaza a la pestaña Config: se editan acá.
//
//  - Un número  = límite mensual. La cuenta entra al
//                 semáforo (CÓMODA / ATENCIÓN / EN RIESGO)
//                 y puede salir como RECOMENDADA.
//  - null       = sin límite. La cuenta NO entra al semáforo
//                 ni a la recomendación, pero se siguen
//                 mostrando sus montos de cada mes.
//
// Después de cambiar un valor: guardar y tocar la casilla B3.
// ==========================================
var LIMITES = {
  LJ:  2000000,
  CDJ: 2000000,
  E:   null,      // Efectivo: sin límite, solo interesa cuánto entró por mes
  VES: null,      // Bs a tus cuentas de Venezuela, en pesos (columna ARS, con el 10%). 13_CuentasVes.gs
  RBJ: 2000000,
  APJ: 2000000,
  BLJ: 2000000,
  PPJ: 2000000,
  NJ:  2000000,
  PXJ: 2000000,
  BBD: 2000000,
  UJ:  2000000,
  BBJ: 2000000,
  UD:  2000000,
  APB: 2000000,
  BTJ:  2000000,
  G66J:  2000000,
  ARQJ:  2000000
};

// Solo se muestran en el dashboard los clientes cuyo nombre
// (columna Nombre de Movimientos) empieza con este prefijo,
// es decir los que vienen del Directorio.
var PREFIJO_CLIENTE = 'bexo';

function limites_() {
  var m = {};
  CUENTAS_DASH.forEach(function (c) {
    m[c] = (LIMITES[c] === undefined) ? null : LIMITES[c];
  });
  return m;
}

function esCliente_(nombre) {
  return String(nombre || '').trim().toLowerCase().indexOf(PREFIJO_CLIENTE) === 0;
}

// ==========================================
// LECTURA Y AGREGACIÓN — una sola pasada
// ==========================================
function agregar_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName('Movimientos');
  var hoy = new Date();

  var meses = [];                       // el actual primero
  for (var k = 0; k < MESES_PANEL; k++) {
    meses.push(new Date(hoy.getFullYear(), hoy.getMonth() - k, 1));
  }
  var claveMes = meses.map(function (m) {
    return Utilities.formatDate(m, TZ, 'yyyy-MM');
  });

  var r = { meses: meses, claveMes: claveMes, porCuenta: {}, recientes: [], ultimaOp: {} };
  CUENTAS_DASH.forEach(function (c) {
    r.porCuenta[c] = { mes: {}, usado: 0 };
    claveMes.forEach(function (k) { r.porCuenta[c].mes[k] = 0; });
  });

  if (!sh || sh.getLastRow() < 2) return r;

  var data = sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();
  // Comprobantes en Bs a tus cuentas de Venezuela: suman en la fila VES con su valor en pesos (columna ARS)
  var head = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0].map(function (h) { return String(h).trim(); });
  var colArs = head.indexOf('ARS');   // 0-indexado; -1 si todavía no existe

  for (var i = 0; i < data.length; i++) {
    var estado = String(data[i][C.ESTADO - 1] || '').trim();
    var fecha  = data[i][C.RECIBIDO - 1];
    var nombre = String(data[i][C.NOMBRE - 1] || '').trim();
    var monto  = Number(data[i][C.MONTO - 1]) || 0;
    var moneda = String(data[i][C.MONEDA - 1] || '').trim();
    var cuenta = String(data[i][C.CUENTA - 1] || '').trim();

    if (!(fecha instanceof Date)) continue;
    if (!esCliente_(nombre)) continue;   // solo clientes Bexo

    // Movimientos recientes: todo lo que tenga monto
    if (monto) {
      r.recientes.push({ f: fecha, n: nombre, c: cuenta, m: monto, e: estado, mon: moneda });
      if (nombre && (!r.ultimaOp[nombre] || fecha > r.ultimaOp[nombre])) r.ultimaOp[nombre] = fecha;
    }

    if (moneda === 'VES' && colArs !== -1 && typeof esCuentaVe_ === 'function' && esCuentaVe_(cuenta)) {
      cuenta = 'VES'; moneda = MONEDA_DASH; monto = Number(data[i][colArs]) || 0;
    }

    // Totales: solo CONTADO y solo la moneda del dashboard
    if (estado !== 'CONTADO' || moneda !== MONEDA_DASH || !r.porCuenta[cuenta]) continue;

    var k = Utilities.formatDate(fecha, TZ, 'yyyy-MM');
    if (k in r.porCuenta[cuenta].mes) r.porCuenta[cuenta].mes[k] += monto;
    if (k === claveMes[0]) r.porCuenta[cuenta].usado += monto;
  }

  r.recientes.sort(function (a, b) { return b.f - a.f; });
  r.recientes = r.recientes.slice(0, 10);

  return r;
}

// ==========================================
// DASHBOARD
// ==========================================
function construirDashboard() {
  var ss  = SpreadsheetApp.getActiveSpreadsheet();
  var lim = limites_();
  var ag  = agregar_();
  var n   = CUENTAS_DASH.length;
  var hoy = new Date();

  var sh = ss.getSheetByName('Dashboard') || ss.insertSheet('Dashboard');
  sh.clear();
  sh.clearConditionalFormatRules();
  sh.getRange(1, 1, sh.getMaxRows(), sh.getMaxColumns()).breakApart();   // combinaciones del dibujo anterior

  // Efectivo (sin límite) va al final de la tabla
  var orden = CUENTAS_DASH.filter(function (c) { return lim[c] !== null; })
    .concat(CUENTAS_DASH.filter(function (c) { return lim[c] === null; }));

  // --- lienzo ---
  sh.getRange(1, 1, 55, 16).setBackground(BG).setFontColor(TXT)
    .setFontFamily('Roboto').setFontSize(8);
  sh.setHiddenGridlines(true);

  var COL_MES = 8, COL_TOT = COL_MES + MESES_PANEL;
  sh.setColumnWidth(1, 14);
  sh.setColumnWidth(2, 50);   // cuenta
  sh.setColumnWidth(3, 92);   // disponible
  sh.setColumnWidth(4, 78);   // barra
  sh.setColumnWidth(5, 36);   // %
  sh.setColumnWidth(6, 66);   // estado
  sh.setColumnWidth(7, 10);
  for (var c = COL_MES; c < COL_TOT; c++) sh.setColumnWidth(c, 66);
  sh.setColumnWidth(COL_TOT, 66);   // sin columna de total por cuenta

  // --- título ---
  sh.getRange('B1').setValue('DASHBOARD OPERATIVO')
    .setFontSize(15).setFontWeight('bold').setFontColor('#ffffff');
  sh.getRange('B2').setValue('ARS · ' + nombreMes_(ag.meses[0]) + '  ·  actualizado ' +
    Utilities.formatDate(hoy, TZ, 'dd/MM HH:mm'))
    .setFontSize(8).setFontColor(MUDO);
  sh.setRowHeight(1, 24); sh.setRowHeight(2, 14);

  // --- checkbox de refresco (funciona desde el teléfono) ---
  sh.getRange('B3').insertCheckboxes().setValue(false);
  sh.getRange('C3').setValue('← tocá la casilla para actualizar')
    .setFontSize(8).setFontColor(AMBAR);
  sh.setRowHeight(3, 18);

  // --- interruptor de lectura automática (DeepSeek). 7_CargaManual.gs ---
  var lectura = ocrActivo_();
  sh.getRange('H3').insertCheckboxes().setValue(lectura);
  etiquetaLectura_(sh, lectura);

  // --- interruptor de pre-órdenes P2P. 11_PreOrden.gs ---
  sh.getRange('K3').insertCheckboxes().setValue(preOrdenActiva_());
  etiquetaPreOrden_(sh, preOrdenActiva_());

  // --- margen disponible por cuenta ---
  var disp = {}, pct = {};
  CUENTAS_DASH.forEach(function (c) {
    var L = lim[c];                       // null = sin límite (ej. E)
    disp[c] = L ? L - ag.porCuenta[c].usado : null;
    pct[c]  = L ? ag.porCuenta[c].usado / L : null;
  });

  // --- hero: la cuenta con más margen ---
  var mejor = null;
  CUENTAS_DASH.forEach(function (c) {
    if (disp[c] === null) return;
    if (!mejor || disp[c] > disp[mejor]) mejor = c;
  });

  // Una sola celda combinada a todo lo ancho: la etiqueta y el dato no se pisan
  sh.setRowHeight(4, 26);
  var etiqueta = '★ RECOMENDADA     ';
  var dato = mejor ? mejor + '  ·  ' + miles_(disp[mejor]) + ' disponible'
                   : 'cargá los límites en LIMITES (5_Dashboard.gs)';
  var hero = SpreadsheetApp.newRichTextValue().setText(etiqueta + dato)
    .setTextStyle(0, etiqueta.length, SpreadsheetApp.newTextStyle()
      .setForegroundColor(VERDE).setBold(true).setFontSize(8).build())
    .setTextStyle(etiqueta.length, etiqueta.length + dato.length, SpreadsheetApp.newTextStyle()
      .setForegroundColor('#ffffff').setBold(true).setFontSize(11).build())
    .build();
  sh.getRange(4, 2, 1, COL_TOT - 2).merge()
    .setRichTextValue(hero)
    .setBackground('#143d33').setVerticalAlignment('middle').setHorizontalAlignment('left')
    .setBorder(true, true, true, true, false, false, VERDE, SpreadsheetApp.BorderStyle.SOLID);
  sh.setRowHeight(5, 6);

  // --- tabla: estado + 6 meses ---
  var head = ['Cuenta', 'Disponible', 'Uso', '%', 'Estado', '']
    .concat(ag.meses.map(function (m) { return nombreMes_(m); }));   // sin columna de total por cuenta
  sh.getRange(6, 2, 1, head.length).setValues([head])
    .setBackground(HEAD).setFontColor(MUDO).setFontWeight('bold');
  sh.getRange(6, COL_MES, 1, MESES_PANEL).setHorizontalAlignment('right');
  sh.setRowHeight(6, 18);

  var f0 = 7;
  var cuerpo = [], barras = [], colEstado = [], bgEstado = [];
  var totMes = [], totDisp = 0;
  for (var j = 0; j < MESES_PANEL; j++) totMes.push(0);

  for (var i = 0; i < n; i++) {
    var c = orden[i];
    var fila = [c, disp[c] === null ? '' : disp[c], '', pct[c] === null ? '' : pct[c], '', ''];
    for (var j = 0; j < MESES_PANEL; j++) {
      var v = ag.porCuenta[c].mes[ag.claveMes[j]] || 0;
      fila.push(v);
      totMes[j] += v;
    }
    cuerpo.push(fila);
    if (disp[c] !== null) totDisp += disp[c];

    // barra y estado
    var p = pct[c];
    if (p === null) {                     // sin límite: no hay semáforo
      var cs = colorSinLimite_(c);
      barras.push(null); colEstado.push(cs.txt); bgEstado.push(cs.est);
      fila[4] = 'SIN LÍMITE';
    }
    else {
      var col = p > 0.85 ? ROJO : (p > 0.6 ? AMBAR : VERDE);
      barras.push({ p: p, color: col });
      fila[4] = p > 0.85 ? 'EN RIESGO' : (p > 0.6 ? 'ATENCIÓN' : 'CÓMODA');
      colEstado.push(col);
      bgEstado.push(p > 0.85 ? '#5c1f1f' : (p > 0.6 ? '#5c4418' : '#1a5c45'));
    }
  }

  sh.getRange(f0, 2, n, head.length).setValues(cuerpo);

  // barras como texto con color (sin fórmulas)
  var rich = [];
  for (var i = 0; i < n; i++) {
    rich.push([barras[i] ? barraRich_(barras[i].p, barras[i].color)
                         : SpreadsheetApp.newRichTextValue().setText(orden[i] === 'VES' ? 'Bs → ARS' : 'efectivo').build()]);
  }
  sh.getRange(f0, 4, n, 1).setRichTextValues(rich);

  sh.getRange(f0, 2, n, 1).setFontWeight('bold').setFontColor('#ffffff');
  sh.getRange(f0, 3, n, 1).setNumberFormat('#,##0').setFontWeight('bold');
  sh.getRange(f0, 5, n, 1).setNumberFormat('0%').setHorizontalAlignment('right');
  sh.getRange(f0, 6, n, 1).setHorizontalAlignment('center').setFontWeight('bold')
    .setFontColors(colEstado.map(function (x) { return [x]; }))
    .setBackgrounds(bgEstado.map(function (x) { return [x]; }));
  sh.getRange(f0, COL_MES, n, MESES_PANEL).setNumberFormat('#,##0');
  for (var i = 0; i < n; i++) sh.setRowHeight(f0 + i, 17);

  // sombreado de los meses según el monto (sin regla condicional)
  var maxMes = 0;
  for (var i = 0; i < n; i++)
    if (pct[orden[i]] !== null)          // el efectivo no entra en la escala de verdes
    for (var j = 0; j < MESES_PANEL; j++)
      maxMes = Math.max(maxMes, cuerpo[i][6 + j]);
  var bgMes = [];
  for (var i = 0; i < n; i++) {
    var fila = [];
    for (var j = 0; j < MESES_PANEL; j++) fila.push(tono_(cuerpo[i][6 + j], maxMes));
    bgMes.push(fila);
  }
  sh.getRange(f0, COL_MES, n, MESES_PANEL).setBackgrounds(bgMes);

  // filas sin límite (E violeta, VES dorado), separadas del resto con una línea
  for (var i = 0; i < n; i++) {
    if (pct[orden[i]] !== null) continue;
    var cs = colorSinLimite_(orden[i]);
    var fila = sh.getRange(f0 + i, 2, 1, COL_TOT - 2);
    fila.setBackground(cs.bg).setFontColor(cs.txt)
      .setBorder(true, null, null, null, null, null, cs.txt, SpreadsheetApp.BorderStyle.DASHED);
    sh.getRange(f0 + i, 4).setFontStyle('italic').setHorizontalAlignment('center');
    sh.getRange(f0 + i, 6).setBackground(cs.est);
  }

  // TOTAL
  var fT = f0 + n;
  var tot = ['TOTAL', totDisp, '', '', '', ''].concat(totMes);
  sh.getRange(fT, 2, 1, tot.length).setValues([tot])
    .setFontWeight('bold').setBackground(HEAD);
  sh.getRange(fT, 3).setNumberFormat('#,##0');
  sh.getRange(fT, COL_MES, 1, MESES_PANEL).setNumberFormat('#,##0');
  sh.setRowHeight(fT, 18);

  // --- movimientos recientes ---
  var fM = fT + 2;
  sh.setRowHeight(fT + 1, 8);
  sh.getRange(fM, 2).setValue('MOVIMIENTOS RECIENTES')
    .setFontSize(9).setFontWeight('bold').setFontColor('#ffffff');
  // Columnas: B fecha · C:D cliente (combinadas) · E cuenta · F importe · H:I estado
  // Así el importe queda en una columna ancha y no se corta por el ancho del %.
  sh.getRange(fM + 1, 2, 1, 8)
    .setValues([['Fecha', 'Cliente', '', 'Cuenta', 'Importe', '', 'Estado', '']])
    .setBackground(HEAD).setFontColor(MUDO).setFontWeight('bold');

  var recs = [];
  for (var i = 0; i < 10; i++) {
    var m = ag.recientes[i];
    recs.push(m ? [Utilities.formatDate(m.f, TZ, 'dd/MM HH:mm'), m.n, '', m.c, m.m, '',
                   m.e + (m.mon && m.mon !== MONEDA_DASH ? ' · ' + m.mon : ''), '']
                : ['', '', '', '', '', '', '', '']);
  }
  sh.getRange(fM + 2, 2, 10, 8).setValues(recs);
  sh.getRange(fM + 1, 3, 11, 2).mergeAcross();                  // cliente
  sh.getRange(fM + 1, 8, 11, 2).mergeAcross();                  // estado
  sh.getRange(fM + 2, 2, 10, 1).setFontSize(6).setFontColor(MUDO);
  sh.getRange(fM + 1, 5, 11, 1).setHorizontalAlignment('center');
  sh.getRange(fM + 1, 6, 11, 1).setHorizontalAlignment('right');
  sh.getRange(fM + 2, 6, 10, 1).setNumberFormat('#,##0').setFontWeight('bold');
  for (var i = 0; i < 10; i++) sh.setRowHeight(fM + 2 + i, 16);

  sh.setFrozenRows(3);
}

// Barra de 10 bloques, la parte usada en color
function barraRich_(p, color) {
  var k = Math.max(0, Math.min(10, Math.round(p * 10)));
  var txt = '';
  for (var i = 0; i < 10; i++) txt += (i < k ? '█' : '░');
  var b = SpreadsheetApp.newRichTextValue().setText(txt);
  if (k > 0) b.setTextStyle(0, k, SpreadsheetApp.newTextStyle().setForegroundColor(color).build());
  if (k < 10) b.setTextStyle(k, 10, SpreadsheetApp.newTextStyle().setForegroundColor(GRIS).build());
  return b.build();
}

// Verde más intenso cuanto mayor el monto
function tono_(v, max) {
  if (!v || !max) return BG;
  var t = Math.min(1, v / max);
  var r = Math.round(15 + (31 - 15) * t);
  var g = Math.round(28 + (95 - 28) * t);
  var b = Math.round(46 + (74 - 46) * t);
  return '#' + [r, g, b].map(function (x) {
    var h = x.toString(16); return h.length < 2 ? '0' + h : h;
  }).join('');
}

function miles_(n) {
  return Math.round(Number(n) || 0).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
}

// ==========================================
// DISPARADORES
// ==========================================

// Para el trigger horario: procesa lo pendiente y refresca
function refrescarTodo() {
  try { procesarPendientes(); } catch (e) { logError_('REFRESCO', e.message); }
  try { limpiarDescartados_(); } catch (e) { logError_('LIMPIEZA', e.message); }   // 6_Mantenimiento.gs
  try { if (typeof formatearFechasMov_ === 'function') formatearFechasMov_(); } catch (e) { logError_('FORMATO_FECHA', e.message); }   // 7_CargaManual.gs
  try { completarVes_(); } catch (e) { logError_('VES', e.message); }   // 13_CuentasVes.gs: antes de las pre-órdenes
  try { enviarPreOrdenes(); } catch (e) { logError_('PREORDEN', e.message); }   // 11_PreOrden.gs
  construirDashboard();
  try { bloqueVes_(); } catch (e) { logError_('DASH_VES', e.message); }
}

// Trigger INSTALABLE "al editar". Lo crea instalarTriggers().
function alEditar(e) {
  try {
    if (!e || !e.range) return;
    var sh = e.range.getSheet();

    // Carga manual en Movimientos: autocompleta la fila (7_CargaManual.gs)
    if (sh.getName() === MOV_SHEET) { completarFilasManuales_(e.range); return; }

    if (sh.getName() !== 'Dashboard') return;
    var celda = e.range.getA1Notation();

    // H3: prender / apagar la lectura automática (7_CargaManual.gs)
    if (celda === 'H3') { fijarLectura_(e.range.getValue() === true);   
    return; }

    // K3: prender / apagar las pre-órdenes P2P (11_PreOrden.gs)
    if (celda === 'K3') { fijarPreOrden_(e.range.getValue() === true); return; }

    if (celda !== 'B3') return;
    if (e.range.getValue() !== true) return;

    e.range.setValue(false);
    refrescarTodo();
  } catch (err) {
    logError_('ON_EDIT', err.message);
  }
}

// Corré esto UNA vez, a mano, desde el editor
function instalarTriggers() {
  var id = SpreadsheetApp.getActiveSpreadsheet().getId();
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'alEditar' || t.getHandlerFunction() === 'refrescarTodo') {
      ScriptApp.deleteTrigger(t);
    }
  });
  ScriptApp.newTrigger('alEditar').forSpreadsheet(id).onEdit().create();
  ScriptApp.newTrigger('refrescarTodo').timeBased().everyHours(1).create();
  Logger.log('Triggers instalados: alEditar (al editar) + refrescarTodo (cada hora)');
}

// ==========================================
// UTILIDAD: achicar hojas con filas vacías de más
// ==========================================
function achicarHojas() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  ss.getSheets().forEach(function (sh) {
    var ultima = Math.max(sh.getLastRow(), 2);
    var sobran = sh.getMaxRows() - ultima - 50;        // deja 50 de colchón
    if (sobran > 0) sh.deleteRows(ultima + 51, sobran);
    var ultCol = Math.max(sh.getLastColumn(), 1);
    var sobranC = sh.getMaxColumns() - ultCol - 2;
    if (sobranC > 0) sh.deleteColumns(ultCol + 3, sobranC);
    Logger.log(sh.getName() + ' → ' + sh.getMaxRows() + ' filas × ' + sh.getMaxColumns() + ' col');
  });
}