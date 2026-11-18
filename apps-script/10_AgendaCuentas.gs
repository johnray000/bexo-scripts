// ==========================================
// 10_AgendaCuentas.gs — AGENDA DE CUENTAS DE PAGO EN VENEZUELA (Pago Móvil y transferencias)
//
// Hoja OCULTA "Agenda" (se crea sola): una fila por cuenta, no por cliente. Si dos clientes le mandan a la
// misma persona (la mamá, la abuela), es una sola fila con los dos en "Clientes".
//
// 1. Cuando un cliente del Directorio manda un mensaje con datos de pago, doPost llama a registrarDatosPago_:
//    si la cuenta ya está, anota que la mandó ahora; si no, la agrega como NUEVA.
// 2. La pre-orden (11_PreOrden.gs) muestra la cuenta que el cliente mandó en las últimas HORAS_DATOS_RECIENTES
//    (✅ agendada / 🆕 nueva) o, si no mandó, sus cuentas de antes para elegir. También se pueden pegar los datos.
// Formato estándar (lo que se guarda, se muestra y se copia): cuenta 20 dígitos corridos, teléfono 04121234567,
// cédula V12345678, banco "0102 Venezuela", titular con mayúscula inicial. Lo desordenado se ordena al leer,
// y la cuenta se reconoce por el número limpio, así que la próxima vez coincide aunque venga escrito distinto.
// 3. Al aprobar, usarCuentaAgenda_ la deja AGENDADA, suma una vez y la fecha.
// No se edita a mano (se puede mirar con clic derecho en las pestañas → Mostrar hoja).
// Usa de otros archivos: logError_ (2).
// ==========================================
var HOJA_AGENDA = 'Agenda';
var ENC_AGENDA = ['Clave', 'Tipo', 'Banco', 'Número', 'Cédula', 'Titular', 'Clientes',
                  'Estado', 'Veces', 'Último uso', 'Último mensaje', 'Mensaje de'];
var AG = { CLAVE: 0, TIPO: 1, BANCO: 2, NUM: 3, CI: 4, TIT: 5, CLI: 6, EST: 7, VECES: 8, USO: 9, MSJ: 10, DE: 11 };
var AG_NUEVA = 'NUEVA';
var AG_AGENDADA = 'AGENDADA';
var HORAS_DATOS_RECIENTES = 48;   // datos mandados hace menos que esto se proponen solos en la pre-orden

var BANCOS_VE = {
  '0102': 'Venezuela', '0104': 'Venezolano de Crédito', '0105': 'Mercantil', '0108': 'Provincial',
  '0114': 'Bancaribe', '0115': 'Exterior', '0128': 'Caroní', '0134': 'Banesco', '0137': 'Sofitasa',
  '0138': 'Plaza', '0151': 'BFC', '0156': '100% Banco', '0157': 'Delsur', '0163': 'Tesoro',
  '0166': 'Agrícola', '0168': 'Bancrecer', '0169': 'Mi Banco', '0171': 'Activo', '0172': 'Bancamiga',
  '0174': 'Banplus', '0175': 'Bicentenario', '0177': 'Banfanb', '0191': 'BNC'
};
// Nombres que la gente escribe → código. Lo más específico primero.
var NOMBRES_BANCO = [
  ['venezolano de credito', '0104'], ['banco de venezuela', '0102'], ['bicentenario', '0175'],
  ['mercantil', '0105'], ['provincial', '0108'], ['banesco', '0134'], ['bancaribe', '0114'],
  ['exterior', '0115'], ['tesoro', '0163'], ['bancamiga', '0172'], ['banplus', '0174'],
  ['plaza', '0138'], ['bnc', '0191'], ['nacional de credito', '0191'], ['venezuela', '0102']
];
// Palabras que no son el nombre del titular
var NO_TITULAR = ['cuenta', 'corriente', 'ahorro', 'pago', 'movil', 'cedula', 'telefono', 'banco', 'tipo',
                  'venezuela', 'datos', 'transferencia', 'hola', 'gracias'];

function soloDigitos_(s) {
  return String(s).replace(/\D/g, '');
}

function conCeros_(v, largo) {
  var d = soloDigitos_(v);
  while (d.length < largo) d = '0' + d;
  return d;
}

function mayusculaInicial_(s) {
  return String(s || '').toLowerCase().replace(/(^|\s)(\S)/g, function (m, a, b) { return a + b.toUpperCase(); }).trim();
}

function sinTildes_(s) {
  return String(s).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
}

/**
 * Lee un mensaje y devuelve los datos de pago, o null si no los tiene:
 * { tipo: 'PM'|'TRANSF', numero, banco, cedula, titular, clave }
 * PM = teléfono 04xx + cédula + banco. TRANSF = cuenta de 20 dígitos + cédula.
 * Acepta guiones, puntos, espacios y paréntesis en cualquier lugar, y teléfonos con +58.
 */
function leerDatosPago_(texto) {
  var t = String(texto || ''), r = {};
  var cta = t.match(/\b0\d{3}(?:[-\s.]?\d){16}\b/);
  if (cta) {
    r.tipo = 'TRANSF'; r.numero = soloDigitos_(cta[0]); r.banco = r.numero.slice(0, 4);
    t = t.replace(cta[0], ' ');
  } else {
    var tel = t.match(/(?:\+\s?58|\b58|\b0|\(0)[-\s.(]*(4(?:12|14|16|22|24|26))\)?((?:[-\s.]?\d){7})\b/);
    if (!tel) return null;
    r.tipo = 'PM'; r.numero = '0' + tel[1] + soloDigitos_(tel[2]);
    t = t.replace(tel[0], ' ');
  }
  if (!r.banco) {
    var b = t.match(/\(?\b(01\d{2})\b\)?/);
    if (b) { r.banco = b[1]; t = t.replace(b[0], ' '); }
  }
  if (!r.banco) {
    var n = sinTildes_(t);
    for (var i = 0; i < NOMBRES_BANCO.length; i++) {
      if (n.indexOf(NOMBRES_BANCO[i][0]) !== -1) { r.banco = NOMBRES_BANCO[i][1]; break; }
    }
  }
  var ci = t.match(/\b([VEve])?[-.\s]{0,2}(\d{1,2}[.\s]?\d{3}[.\s]?\d{3})\b/);
  if (ci) r.cedula = (ci[1] || 'V').toUpperCase() + soloDigitos_(ci[2]);
  if (!r.banco || !r.cedula) return null;
  r.titular = mayusculaInicial_(titularDe_(t));
  r.clave = (r.tipo === 'PM' ? 'PM:' : 'TR:') + r.numero;
  return r;
}

/** Nombre del titular: "cuenta de X" / "a nombre de X", o una línea de solo letras con 2 o más palabras. */
function titularDe_(t) {
  var de = t.match(/(?:cuenta de|a nombre de|titular:?)\s+([A-Za-zÁÉÍÓÚáéíóúÑñ ]{3,40})/i);
  if (de) return de[1].trim();
  var lineas = t.split(/\n/);
  for (var i = 0; i < lineas.length; i++) {
    var l = lineas[i].trim();
    if (!/^[A-Za-zÁÉÍÓÚáéíóúÑñ ]+$/.test(l) || l.split(/\s+/).length < 2) continue;
    var palabras = sinTildes_(l).split(/\s+/);
    if (palabras.some(function (p) { return NO_TITULAR.indexOf(p) !== -1; })) continue;
    if (esNombreBanco_(l)) continue;   // "Venezolano de crédito" no es una persona
    return l;
  }
  return '';
}

function esNombreBanco_(s) {
  var n = sinTildes_(s);
  return NOMBRES_BANCO.some(function (b) { return n.indexOf(b[0]) !== -1; });
}

function hojaAgenda_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(HOJA_AGENDA);
  if (!sh) {
    sh = ss.insertSheet(HOJA_AGENDA);
    sh.appendRow(ENC_AGENDA);
    sh.getRange(1, 1, 1, ENC_AGENDA.length).setFontWeight('bold');
    sh.hideSheet();
  }
  return sh;
}

/** Todas las cuentas como objetos (con su número de fila). */
function leerAgenda_() {
  var sh = hojaAgenda_();
  if (sh.getLastRow() < 2) return [];
  return sh.getRange(2, 1, sh.getLastRow() - 1, ENC_AGENDA.length).getValues().map(function (f, i) {
    return {
      // Si Sheets ya convirtió a número (0102 → 102), se reponen los ceros de adelante
      fila: i + 2, clave: String(f[AG.CLAVE]), tipo: f[AG.TIPO], banco: conCeros_(f[AG.BANCO], 4),
      numero: conCeros_(f[AG.NUM], f[AG.TIPO] === 'PM' ? 11 : 20), cedula: String(f[AG.CI]), titular: String(f[AG.TIT]),
      clientes: String(f[AG.CLI]).split(' | ').filter(String), estado: f[AG.EST],
      veces: Number(f[AG.VECES]) || 0, uso: f[AG.USO], msj: f[AG.MSJ], de: String(f[AG.DE])
    };
  });
}

/**
 * Agrega o actualiza una cuenta. cuando = 'mensaje' (la mandó el cliente) o 'uso' (aprobaste un pago a esa cuenta).
 * Devuelve la cuenta como objeto, con aviso si la cédula no coincide con la agendada.
 */
function guardarCuenta_(cliente, p, cuando) {
  var sh = hojaAgenda_();
  var c = leerAgenda_().filter(function (x) { return x.clave === p.clave; })[0];
  var ahora = new Date();
  if (!c) {
    var f = ['', '', '', '', '', '', '', '', 0, '', '', ''];
    f[AG.CLAVE] = p.clave; f[AG.TIPO] = p.tipo; f[AG.BANCO] = "'" + p.banco; f[AG.NUM] = "'" + p.numero;
    f[AG.CI] = p.cedula; f[AG.TIT] = p.titular || ''; f[AG.CLI] = cliente; f[AG.EST] = AG_NUEVA;
    if (cuando === 'uso') { f[AG.EST] = AG_AGENDADA; f[AG.VECES] = 1; f[AG.USO] = ahora; }
    else { f[AG.MSJ] = ahora; f[AG.DE] = cliente; }
    sh.appendRow(f);
    return leerAgenda_().filter(function (x) { return x.clave === p.clave; })[0];
  }
  if (p.cedula && c.cedula && p.cedula !== c.cedula) c.avisoCedula = 'cédula distinta a la agendada (' + c.cedula + ')';
  if (c.clientes.indexOf(cliente) === -1) c.clientes.push(cliente);
  if (!c.titular && p.titular) c.titular = p.titular;
  var fila = sh.getRange(c.fila, 1, 1, ENC_AGENDA.length).getValues()[0];
  fila[AG.BANCO] = "'" + c.banco;    // el apóstrofo lo guarda como texto: Sheets no se come el 0 (no se ve en la celda)
  fila[AG.NUM] = "'" + c.numero;
  fila[AG.CLI] = c.clientes.join(' | ');
  fila[AG.TIT] = c.titular;
  if (cuando === 'uso') {
    fila[AG.EST] = AG_AGENDADA; fila[AG.VECES] = c.veces + 1; fila[AG.USO] = ahora;
    c.estado = AG_AGENDADA; c.veces++;
  } else {
    fila[AG.MSJ] = ahora; fila[AG.DE] = cliente;
  }
  sh.getRange(c.fila, 1, 1, ENC_AGENDA.length).setValues([fila]);
  return c;
}

/** La llama doPost (2_Recepcion.gs) con cada mensaje de un cliente. Si no trae datos de pago, no hace nada. */
function registrarDatosPago_(cliente, texto) {
  try {
    var p = leerDatosPago_(texto);
    if (!p) return;
    var lock = LockService.getScriptLock();
    if (!lock.tryLock(5000)) { logError_('AGENDA', 'Ocupado, no se guardó: ' + p.clave + ' de ' + cliente); return; }
    try { guardarCuenta_(cliente, p, 'mensaje'); } finally { lock.releaseLock(); }
  } catch (e) {
    logError_('AGENDA', e.message || e);
  }
}

/**
 * Para la pre-orden: { reciente: la que mandó este cliente hace menos de HORAS_DATOS_RECIENTES (o null),
 *                      otras: sus demás cuentas, las más usadas primero }
 */
function cuentasDelCliente_(cliente, agenda) {
  var limite = Date.now() - HORAS_DATOS_RECIENTES * 3600000;
  var suyas = (agenda || leerAgenda_()).filter(function (c) { return c.clientes.indexOf(cliente) !== -1; });
  var recientes = suyas.filter(function (c) { return c.de === cliente && c.msj instanceof Date && c.msj.getTime() > limite; })
    .sort(function (a, b) { return b.msj - a.msj; });
  var reciente = recientes[0] || null;
  var otras = suyas.filter(function (c) { return c !== reciente; }).sort(function (a, b) { return b.veces - a.veces; });
  return { reciente: reciente, otras: otras };
}

/** Al aprobar: deja la cuenta AGENDADA y suma un uso. texto = datos pegados en la página (opcional). */
function usarCuentaAgenda_(cliente, clave, texto) {
  var p = null;
  if (texto && String(texto).trim()) {
    p = leerDatosPago_(texto);
    if (!p) throw new Error('No reconocí los datos pegados (falta teléfono o cuenta, cédula o banco)');
  } else if (clave) {
    p = leerAgenda_().filter(function (x) { return x.clave === clave; })[0];
    if (!p) throw new Error('Esa cuenta ya no está en la Agenda');
  }
  return p ? guardarCuenta_(cliente, p, 'uso') : null;
}

/**
 * La cuenta en formato estándar, campo por campo (para mostrar, copiar y la columna Destino):
 * [tipo corto, banco, número, cédula, titular]. Sin espacios ni puntos dentro de los números.
 */
function camposCuenta_(c) {
  return [
    c.tipo === 'PM' ? 'PM' : 'Transf',
    c.banco + ' ' + (BANCOS_VE[c.banco] || ''),
    soloDigitos_(c.numero),
    String(c.cedula).replace(/[^VE0-9]/gi, '').toUpperCase(),
    esNombreBanco_(c.titular) ? '' : mayusculaInicial_(c.titular)   // las viejas pudieron guardar el banco como titular
  ].map(function (x) { return String(x).trim(); });
}

/**
 * Datos en líneas, listos para copiar al chat de Binance (formato de John):
 *   número (teléfono o cuenta) / titular / cédula sin V / banco / Pago Movil o Transfer
 * f = camposCuenta_ (o la columna Destino partida por ' · ').
 */
function lineasDeCampos_(f) {
  return [f[2], f[4], String(f[3] || '').replace(/^V/i, ''), f[1], f[0] === 'PM' ? 'Pago Movil' : 'Transfer']
    .filter(function (x) { return x && String(x).trim(); });
}

function lineasCuenta_(c) {
  return lineasDeCampos_(camposCuenta_(c));
}

/** Una línea para la columna Destino de Movimientos: PM · 0102 Venezuela · 04121234567 · V12345678 · Ana Pérez */
function textoCuenta_(c) {
  return camposCuenta_(c).join(' · ');   // siempre 5 campos (titular puede ir vacío) para poder partirla de vuelta
}

/** Deshacer una confirmación: a la cuenta de esa columna Destino le resta un uso. */
function desusarCuentaAgenda_(destino) {
  var f = String(destino || '').split(' · ');
  if (f.length < 4) return;
  var clave = (f[0] === 'PM' ? 'PM:' : 'TR:') + soloDigitos_(f[2]);
  var c = leerAgenda_().filter(function (x) { return x.clave === clave; })[0];
  if (!c) return;
  var veces = Math.max(0, c.veces - 1);
  var sh = hojaAgenda_();
  sh.getRange(c.fila, AG.VECES + 1).setValue(veces);
  if (!veces) sh.getRange(c.fila, AG.EST + 1).setValue(AG_NUEVA);
}

// Corré esto UNA vez: reescribe Banco y Número de toda la Agenda con sus ceros (0102, 0426...), como texto.
function repararAgenda() {
  var sh = hojaAgenda_();
  var agenda = leerAgenda_();
  if (!agenda.length) return;
  sh.getRange(2, AG.BANCO + 1, agenda.length, 2).setValues(agenda.map(function (c) {
    return ["'" + c.banco, "'" + c.numero];
  }));
  Logger.log('Agenda reparada: ' + agenda.length + ' cuentas');
}

// Prueba desde el editor: muestra qué entiende de cada mensaje. No escribe nada.
function probarReglasAgenda() {
  ['0102 04261112233\n12345678', 'Cuenta de María\n0102 04241234567\nCédula:17000111',
   '(0175)\n27000222\n04141239876\n\nPago móvil', '0104 venezolano de crédito cédula 19000333 teléfono 04161234567',
   '0102-0453-4100-0001-2345\nCorriente\nVenezuela\nAna perez\n11000444',
   'Tipo de cuenta: VES\n01020339270000123456\nV24000555\nLaura Maria Gomez Rojas',
   'Pago movil banesco +58 414-123.98.76 CI V-27.000.222', '0102.0339.27.0000123456 C.I. 24 000 555',
   'Hola, te mando 50.000 ahora'].forEach(function (m) {
    var p = leerDatosPago_(m);
    Logger.log(m.replace(/\n/g, ' / ') + '\n   → ' + (p ? lineasCuenta_(p).join(' · ') : 'no son datos de pago'));
  });
}
