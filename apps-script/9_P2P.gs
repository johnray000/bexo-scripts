// 9_P2P.gs — Lectura de anuncios de Binance P2P vía el relay del VPS.
// Binance bloquea las IPs de Google (403), por eso no se llama directo.
// Propiedad del script requerida: RELAY_TOKEN (la misma que /etc/relay-binance.env en el VPS).

var RELAY_URL = CONFIG.RELAY_URL;   // 0_Config.gs

// ---- Reglas de la tasa (cambiar acá) ----
var MARGEN = 0.08;            // tasa neta = tasa × (1 - MARGEN)
var MIN_USDT_MAX = 1000;      // se descartan anuncios cuyo mínimo supera esto en USDT (se ajusta solo con la inflación)
var DESVIO_MAX = 0.03;        // se descartan precios a más de 3% de la mediana del resto
// Métodos VES aceptados: se compara sin mayúsculas y por "contiene" contra el identificador de Binance.
var METODOS_VES = ['pagomovil', 'banesco', 'mercantil', 'bancodevenezuela', 'bank'];
// Métodos para buscar el anuncio de las órdenes, EN ORDEN DE PRIORIDAD. true = activo, false = apagado.
// Se prueba el primero activo; si no hay anuncio que sirva, el siguiente. La tasa sigue usando METODOS_VES.
// El nombre tiene que ser el identificador exacto de Binance: correr listarMetodosVES() para verlos.
var METODOS_ORDEN = [
  ['PagoMovil', true],
  ['Banesco', false],
  ['Mercantil', false],
  ['BancoDeVenezuela', false]
];

function metodosOrdenActivos_() {
  return METODOS_ORDEN.filter(function (m) { return m[1]; }).map(function (m) { return m[0]; });
}

// Si la pre-orden tiene la cuenta del cliente (10_AgendaCuentas.gs), el anuncio se busca por el método que sirve
// para pagarle a ESA cuenta: Pago Móvil → PagoMovil; transferencia → el banco de la cuenta (código → nombre en Binance).
// Un banco que no está acá: los bancos de esta lista (transferencia interbancaria). Nombres: listarMetodosVES().
var METODO_PM = 'PagoMovil';
var METODO_POR_BANCO = {
  '0102': 'BancoDeVenezuela',
  '0105': 'Mercantil',
  '0108': 'Provincial',
  '0134': 'Banesco'
};

/** Métodos para buscar el anuncio según la cuenta del cliente (null = los de METODOS_ORDEN). */
function metodosParaCuenta_(cuenta) {
  if (!cuenta) return null;
  if (cuenta.tipo === 'PM') return [METODO_PM];
  if (METODO_POR_BANCO[cuenta.banco]) return [METODO_POR_BANCO[cuenta.banco]];
  return Object.keys(METODO_POR_BANCO).map(function (k) { return METODO_POR_BANCO[k]; });   // nunca Pago Móvil a una cuenta
}

/**
 * Corré esto a mano: trae anuncios VES de Binance sin filtrar y muestra en el registro cada método
 * con su nombre exacto y en cuántos anuncios aparece. Marca cuáles de METODOS_ORDEN no aparecieron.
 */
function listarMetodosVES() {
  var veces = {};
  ['', 20000, 100000].forEach(function (monto) {
    leerAnunciosP2P_('VES', 'SELL', '', monto).forEach(function (a) {
      a.pagos.forEach(function (p) { veces[p] = (veces[p] || 0) + 1; });
    });
  });
  Object.keys(veces).sort(function (a, b) { return veces[b] - veces[a]; }).forEach(function (p) {
    Logger.log(p + '  (' + veces[p] + ' anuncios)');
  });
  METODOS_ORDEN.forEach(function (m) {
    Logger.log((veces[m[0]] ? '✓ ' : '✗ NO APARECIÓ: ') + m[0] + (m[1] ? ' [activo]' : ' [apagado]'));
  });
  Object.keys(METODO_POR_BANCO).forEach(function (k) {
    var m = METODO_POR_BANCO[k];
    Logger.log((veces[m] ? '✓ ' : '✗ NO APARECIÓ: ') + m + ' [banco ' + k + ']');
  });
}

/** Trae hasta 20 anuncios USDT/<fiat>. tipo 'SELL' = vos vendés USDT (te pagan en fiat). */
function leerAnunciosP2P_(fiat, tipo, pago, monto) {
  var token = PropertiesService.getScriptProperties().getProperty('RELAY_TOKEN');
  var url = RELAY_URL + '/anuncios?token=' + encodeURIComponent(token) +
            '&fiat=' + fiat + '&tipo=' + tipo + '&filas=20' +
            (pago ? '&pago=' + encodeURIComponent(pago) : '') +
            (monto ? '&monto=' + monto : '');
  var res = UrlFetchApp.fetch(url, { muteHttpExceptions: true });
  if (res.getResponseCode() !== 200) {
    throw new Error('Relay P2P ' + res.getResponseCode() + ': ' + res.getContentText().slice(0, 200));
  }
  return JSON.parse(res.getContentText()).anuncios;
}

function mediana_(nums) {
  var s = nums.slice().sort(function (a, b) { return a - b; });
  var m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

/**
 * Deja solo los anuncios "normales", en el orden de Binance (el primero es el mejor precio):
 * 1) si se pasan métodos, que acepte al menos uno;
 * 2) que su mínimo, pasado a USDT con su propio precio, no supere MIN_USDT_MAX;
 * 3) que su precio no se aleje más de DESVIO_MAX de la mediana de los que quedan.
 */
function anunciosValidos_(anuncios, metodos, sinMinimo) {
  var r = anuncios.filter(function (a) {
    if (!metodos) return true;
    return a.pagos.some(function (p) {
      var id = String(p || '').toLowerCase();
      return metodos.some(function (m) { return id.indexOf(m) !== -1; });
    });
  }).filter(function (a) {
    return sinMinimo || a.min / a.precio <= MIN_USDT_MAX;
  });
  if (!r.length) return r;
  var med = mediana_(r.map(function (a) { return a.precio; }));
  return r.filter(function (a) { return Math.abs(a.precio - med) / med <= DESVIO_MAX; });
}

/** Prueba manual: muestra cada anuncio con ✓ (válido) o ✗ y la tasa resultante. */
function probarRelayP2P() {
  try {
    var ves = leerAnunciosP2P_('VES', 'SELL', '', '');
    var validos = anunciosValidos_(ves, METODOS_VES);
    ves.forEach(function (a) {
      Logger.log((validos.indexOf(a) !== -1 ? '✓ ' : '✗ ') + a.precio + ' | ' + a.min + '-' + a.max +
                 ' (mín ' + Math.round(a.min / a.precio) + ' USDT) | ' + a.pagos.join(',') + ' | ' + a.apodo);
    });
    Logger.log('Válidos VES: ' + validos.length + ' de ' + ves.length);
  } catch (e) {
    logError_('probarRelayP2P', e.message || e);
    throw e;
  }
}

// ==========================================
// TASAS: una fila por lectura en la hoja 'Tasas' (la más nueva arriba)
// ==========================================
var HOJA_TASAS = 'Tasas';
var ENCABEZADOS_TASAS = ['Fecha', 'USDT VES', 'VES mediana', 'USDT ARS', 'ARS mediana',
                         'Tasa', 'Tasa neta', 'Anuncio VES', 'Válidos VES'];

/**
 * USDT VES = primer anuncio válido donde vos VENDÉS USDT por bolívares.
 * USDT ARS = primer anuncio válido donde vos COMPRÁS USDT con pesos.
 * Tasa = USDT VES / USDT ARS (bolívares por peso). Tasa neta = Tasa × (1 - MARGEN), redondeada a 0,005.
 * Devuelve los datos de la lectura (o null si falló) para poder avisar por WhatsApp.
 */
function registrarTasaP2P() {
  try {
    var ves = anunciosValidos_(leerAnunciosP2P_('VES', 'SELL', '', ''), METODOS_VES);
    var ars = anunciosValidos_(leerAnunciosP2P_('ARS', 'BUY', '', ''), null);
    if (!ves.length || !ars.length) throw new Error('Sin anuncios válidos: VES ' + ves.length + ', ARS ' + ars.length);

    var tasa = ves[0].precio / ars[0].precio;
    var neta = redondearTasa_(tasa * (1 - MARGEN));

    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sh = ss.getSheetByName(HOJA_TASAS) || ss.insertSheet(HOJA_TASAS);
    var colNeta = ENCABEZADOS_TASAS.indexOf('Tasa neta') + 1;
    var anterior = sh.getLastRow() >= 2 ? Number(sh.getRange(2, colNeta).getValue()) || 0 : 0;
    sh.getRange(1, 1, 1, ENCABEZADOS_TASAS.length).setValues([ENCABEZADOS_TASAS]).setFontWeight('bold');
    sh.setFrozenRows(1);
    sh.insertRowBefore(2);
    sh.getRange(2, 1, 1, ENCABEZADOS_TASAS.length).setValues([[
      new Date(),
      ves[0].precio, mediana_(ves.map(function (a) { return a.precio; })),
      ars[0].precio, mediana_(ars.map(function (a) { return a.precio; })),
      Math.round(tasa * 10000) / 10000,
      neta,
      ves[0].apodo + ' · ' + ves[0].pagos.join(','),
      ves.length
    ]]);
    return { ves: ves[0].precio, ars: ars[0].precio, tasa: tasa, neta: neta, anterior: anterior };
  } catch (e) {
    logError_('registrarTasaP2P', e.message || e);
    return null;
  }
}

/** Redondea a la 0,005 más cercana: 0,5739 → 0,575 · 0,579 → 0,580. */
function redondearTasa_(t) {
  return Math.round(t * 200) / 200;
}

/** 1234567.8 → "1.234.567,8" (formato argentino, con `dec` decimales). */
function fmtN_(n, dec) {
  var p = Number(n).toFixed(dec).split('.');
  return p[0].replace(/\B(?=(\d{3})+(?!\d))/g, '.') + (p[1] ? ',' + p[1] : '');
}

/**
 * Para WhatsApp: separador invisible después de cada punto y coma (el formato que sale limpio
 * en el mensaje de la tasa). WhatsApp igual subraya si hay varios números en el mismo renglón,
 * por eso los mensajes llevan un número por renglón.
 */
function fmtW_(n, dec) {
  return fmtN_(n, dec).replace(/([.,])/g, '$1\u2060');
}

/**
 * Números "dibujados" con los dígitos matemáticos de Unicode (𝟤𝟢.𝟢𝟢𝟢): se ven como números normales
 * pero WhatsApp no los reconoce como cifras, así que no los subraya. Solo para leer: no sirven para copiar.
 */
function fmtM_(n, dec, negrita) {
  var base = negrita ? 0x1D7EC : 0x1D7E2;
  return fmtN_(n, dec).replace(/[0-9]/g, function (d) { return String.fromCodePoint(base + Number(d)); });
}

/** "15 oct · 18:39" (sin barras, para que WhatsApp no lo tome como fecha). */
function horaLinda_() {
  var tz = Session.getScriptTimeZone(), d = new Date();
  var meses = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
  return Utilities.formatDate(d, tz, 'd') + ' ' + meses[Number(Utilities.formatDate(d, tz, 'M')) - 1] +
         ' · ' + Utilities.formatDate(d, tz, 'HH:mm');
}

/** Lo que corre a las 9 y a las 18: registra la tasa y te la manda por WhatsApp. */
function tasaProgramadaP2P() {
  var r = registrarTasaP2P();
  if (!r) {
    sendWhatsAppMessage_(MI_TELEFONO, '⚠️ No pude calcular la tasa P2P. Mirá la hoja Debug_Errores.');
    return;
  }
  var flecha = !r.anterior ? '' :
               r.neta > r.anterior ? '  ▲ antes ' + fmtW_(r.anterior, 3) :
               r.neta < r.anterior ? '  ▼ antes ' + fmtW_(r.anterior, 3) : '  = sin cambios';
  var texto = [
    '*TASA BEXO* · ' + horaLinda_(),
    '━━━━━━━━━━━━━━',
    '✅ *TASA NETA*',
    '🟢 *' + fmtW_(r.neta, 3) + '* 🟢' + flecha,
    '━━━━━━━━━━━━━━',
    '🇻🇪 USDT → Bs   ' + fmtW_(r.ves, 2),
    '🇦🇷 USDT → ARS  ' + fmtW_(r.ars, 2),
    '📊 Tasa bruta   ' + fmtW_(r.tasa, 4),
    '━━━━━━━━━━━━━━',
    fmtW_(100000, 0) + ' ARS → *' + fmtW_(100000 * r.neta, 0) + ' Bs*'
  ].join('\n');
  sendWhatsAppMessage_(MI_TELEFONO, texto);
}

// Corré esto UNA vez, a mano, desde el editor: tasa + WhatsApp todos los días a las 9 y a las 18
// (Google lo corre dentro de ±15 minutos de esa hora; usa la zona horaria del proyecto).
function instalarTriggerTasa() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    var f = t.getHandlerFunction();
    if (f === 'registrarTasaP2P' || f === 'tasaProgramadaP2P') ScriptApp.deleteTrigger(t);
  });
  [9, 18].forEach(function (h) {
    ScriptApp.newTrigger('tasaProgramadaP2P').timeBased().atHour(h).nearMinute(0).everyDays(1).create();
  });
  Logger.log('Trigger instalado: tasaProgramadaP2P a las 9 y a las 18 (' + Session.getScriptTimeZone() + ')');
}

// ==========================================
// ORDEN ASISTIDA: para un monto en ARS, elige el anuncio VES donde vender y arma el mensaje.
// No abre nada en Binance: solo arma el link y el texto para que los uses vos.
// ==========================================
var HOJA_TRADERS_VES = 'traders_ves';
var TOLERANCIA_TRADER = 0.005;   // aceptás hasta 0,5% peor precio si el anuncio es de un trader conocido
var LINK_ANUNCIO = 'https://c2c.binance.com/es-LA/adv?code=';

/** Apodo → órdenes completadas, desde la hoja traders_ves. */
function leerTradersVes_() {
  var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(HOJA_TRADERS_VES);
  var mapa = {};
  if (!sh || sh.getLastRow() < 2) return mapa;
  sh.getRange(2, 1, sh.getLastRow() - 1, 2).getValues().forEach(function (f) {
    if (f[0] !== '') mapa[String(f[0]).trim()] = Number(f[1]) || 0;
  });
  return mapa;
}

/** Tasa neta de la última fila de la hoja Tasas. */
function tasaNetaActual_() {
  var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(HOJA_TASAS);
  var v = sh ? Number(sh.getRange(2, ENCABEZADOS_TASAS.indexOf('Tasa neta') + 1).getValue()) : 0;
  if (!(v > 0 && v < 5)) throw new Error('No hay tasa neta válida en la hoja Tasas (corré registrarTasaP2P)');
  return v;
}

// ==========================================
// FILTRO DE DESCRIPCIONES (solo traders nuevos)
//
// Decide si la descripción de un anuncio rechaza pagos de terceros. Tres capas:
//   1) Reglas fijas por concepto: "NO ... terceros" y "SOLO ... titular" bloquean;
//      "SÍ/acepto ... terceros" o "terceros ... autorizar/chat" permiten.
//   2) Tus frases de la hoja Filtro, columna Tipo: BLOQUEAR (o vacío) / PERMITIR.
//   3) PERMITIR siempre gana sobre BLOQUEAR.
// Tolera errores de tipeo (titilar, tiltular, tercros), acentos, mayúsculas, emojis y
// palabras en el medio ("no se hacen tratos con terceros").
// ==========================================
var HOJA_FRASES = 'Filtro';             // antes se llamaba frases_alerta: se renombra sola
var ENCABEZADOS_FRASES = ['Frase', 'Agregada', 'Trader donde la viste', 'Tipo'];
var MAX_DESCRIPCIONES = 12;   // cuántas descripciones pide como máximo por orden
var VENTANA = 5;              // cuántas palabras puede haber entre "no" y "terceros"

var CONCEPTOS = {
  TERCERO: { raices: ['tercer', '3ro', '3er'], palabras: ['tercero', 'terceros', 'tercera', 'terceras'] },
  TITULAR: { raices: ['titular'], palabras: ['titular', 'titulares', 'titularidad'] },
  NEG:     { raices: [], palabras: ['no', 'ni', 'sin', 'nunca', 'prohibido', 'prohibidos', 'abstenerse',
                                    'abstente', 'evitar', 'evite', 'rechazo', 'rechazamos', 'jamas'] },
  SOLO:    { raices: ['exclusiv'], palabras: ['solo', 'solamente', 'unicamente', 'unico', 'unica'] },
  SI:      { raices: ['acept', 'permit', 'bienvenid'], palabras: ['si', 'valido', 'validos', 'problema'] },
  AUTH:    { raices: ['autoriz'], palabras: ['chat', 'captura', 'permiso', 'verificar', 'verificacion'] }
};

/** Minúsculas, sin acentos ni emojis, solo letras/números separados por un espacio. */
function normalizar_(s) {
  return String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ').trim();
}

/** Distancia de edición (cuántas letras cambiar/agregar/sacar). */
function distancia_(a, b) {
  if (Math.abs(a.length - b.length) > 2) return 9;
  var prev = [], cur, i, j;
  for (j = 0; j <= b.length; j++) prev[j] = j;
  for (i = 1; i <= a.length; i++) {
    cur = [i];
    for (j = 1; j <= b.length; j++) {
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    }
    prev = cur;
  }
  return prev[b.length];
}

/** ¿La palabra del texto es "la misma" que la buscada, con errores de tipeo? */
function parecida_(texto, buscada) {
  if (texto === buscada) return true;
  if (buscada.length <= 3) return false;                 // no, ni, sin: exactas
  var tol = buscada.length >= 7 ? 2 : 1;
  return distancia_(texto, buscada) <= tol;
}

function esConcepto_(palabra, nombre) {
  var c = CONCEPTOS[nombre];
  if (c.raices.some(function (r) { return palabra.indexOf(r) === 0; })) return true;
  return c.palabras.some(function (p) { return parecida_(palabra, p); });
}

/** Busca la palabra A y después (a no más de `ventana` palabras) la B. Devuelve el tramo o null. */
function tramo_(pal, i, j) { return pal.slice(i, j + 1).join(' '); }

function reglasFijas_(pal) {
  var r = { permite: null, bloquea: null };
  for (var j = 0; j < pal.length; j++) {
    if (esConcepto_(pal[j], 'TERCERO')) {
      for (var i = Math.max(0, j - VENTANA); i <= Math.min(pal.length - 1, j + 3); i++) {
        if (i === j) continue;
        var negado = i > 0 && esConcepto_(pal[i - 1], 'NEG') || i > 1 && esConcepto_(pal[i - 2], 'NEG');
        if (esConcepto_(pal[i], 'SI') && (pal[i] === 'problema' || !negado)) {
          r.permite = r.permite || tramo_(pal, Math.min(i, j), Math.max(i, j));
        }
        if (esConcepto_(pal[i], 'AUTH') && i > j) {
          r.permite = r.permite || tramo_(pal, j, i);
        }
        if (esConcepto_(pal[i], 'NEG') && (i < j || i <= j + 2)) {   // "no ... terceros" o "terceros NO"
          r.bloquea = r.bloquea || tramo_(pal, Math.min(i, j), Math.max(i, j));
        }
      }
    }
    if (esConcepto_(pal[j], 'TITULAR')) {
      for (var k = Math.max(0, j - VENTANA); k < j; k++) {
        if (esConcepto_(pal[k], 'SOLO')) r.bloquea = r.bloquea || tramo_(pal, k, j);
      }
    }
  }
  return r;
}

/** ¿Las palabras de la frase aparecen en orden en el texto (con tipeo y hasta 2 palabras extra entre medio)? */
function fraseEn_(pal, frase) {
  var f = normalizar_(frase).split(' ').filter(String);
  if (!f.length) return null;
  for (var ini = 0; ini < pal.length; ini++) {
    if (!parecida_(pal[ini], f[0])) continue;
    var pos = ini, ok = true;
    for (var w = 1; w < f.length && ok; w++) {
      ok = false;
      for (var p = pos + 1; p <= pos + 3 && p < pal.length; p++) {
        if (parecida_(pal[p], f[w])) { pos = p; ok = true; break; }
      }
    }
    if (ok) return tramo_(pal, ini, pos);
  }
  return null;
}

/** Lee la hoja de frases → { bloquear: [...], permitir: [...] }. Crea la hoja o la columna Tipo si faltan. */
function leerFrasesAlerta_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = hojaFiltro_();
  var r = { bloquear: [], permitir: [] };
  if (sh.getLastRow() < 2) return r;
  sh.getRange(2, 1, sh.getLastRow() - 1, 4).getValues().forEach(function (f) {
    var frase = String(f[0] || '').trim();
    if (!frase) return;
    (String(f[3]).trim().toUpperCase() === 'PERMITIR' ? r.permitir : r.bloquear).push(frase);
  });
  return r;
}

/**
 * Revisa una descripción. Devuelve null si sirve, o el motivo si hay que descartarla:
 * "regla: no se hacen tratos con terceros" / "frase: solo titulares".
 */
function motivoDescarte_(descripcion, frases) {
  var pal = normalizar_(descripcion).split(' ').filter(String);
  if (!pal.length) return null;
  var r = reglasFijas_(pal);
  if (r.permite) return null;
  for (var i = 0; i < frases.permitir.length; i++) if (fraseEn_(pal, frases.permitir[i])) return null;
  if (r.bloquea) return r.bloquea;
  for (var k = 0; k < frases.bloquear.length; k++) {
    var t = fraseEn_(pal, frases.bloquear[k]);
    if (t) return t;
  }
  return null;
}

// ---- Hoja Filtro: a la izquierda (A:D) tus frases; a la derecha (F:J) el registro de lo que revisó,
// lo más nuevo arriba. Todo lo del filtro en una sola hoja.
var ENCABEZADOS_FILTRO_LOG = ['Fecha', 'Trader', 'Resultado', 'Por qué', 'Descripción', 'Anuncio'];

function hojaFiltro_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(HOJA_FRASES);
  if (!sh) {
    sh = ss.getSheetByName('frases_alerta');
    if (sh) sh.setName(HOJA_FRASES); else sh = ss.insertSheet(HOJA_FRASES);
  }
  if (sh.getRange('K1').getValue() !== 'Anuncio') {
    sh.getRange(1, 1, 1, ENCABEZADOS_FRASES.length).setValues([ENCABEZADOS_FRASES]).setFontWeight('bold');
    sh.getRange(1, 6, 1, ENCABEZADOS_FILTRO_LOG.length).setValues([ENCABEZADOS_FILTRO_LOG]).setFontWeight('bold');
    sh.setFrozenRows(1);
    sh.setColumnWidth(10, 450);
  }
  return sh;
}

function registrarFiltro_(a, motivo) {
  try {
    var sh = hojaFiltro_();
    sh.getRange('F2:K2').insertCells(SpreadsheetApp.Dimension.ROWS);   // corre solo el registro, no tus frases
    sh.getRange(2, 6, 1, 6).setValues([[new Date(), a.apodo, motivo ? '🚫 DESCARTADO' : '✅ PASÓ',
      motivo || '', String(a.descripcion || '(sin descripción)').slice(0, 1000), String(a.adNo)]]);
  } catch (e) {
    logError_('registrarFiltro_', e.message || e);
  }
}

/** Prueba el filtro con tus frases: escribí descripciones en la lista y mirá el registro. */
function probarFiltroFrases() {
  var frases = leerFrasesAlerta_();
  ['Sólo titilar', 'NO HAGO PAGO A TERCEROS', 'No se hacen tratos con terceros',
   'Si acepto terceros con autorización', 'Pagos de terceros deben enviar captura al chat',
   'No hay problema con terceros', 'Hola, atiendo rápido. Pago móvil y transferencias.',
   'solo pago al titular de la cuenta', 'Terceros NO', 'Abstenerse pagos de 3ros',
   'Únicamente cuentas a nombre del titular', 'Recibo de terceros sin problema'].forEach(function (d) {
    var m = motivoDescarte_(d, frases);
    Logger.log((m ? '🚫 ' : '✅ ') + d + (m ? '   ← ' + m : ''));
  });
}

/**
 * Entre los anuncios que aceptan exactamente montoVes, toma el de mejor precio;
 * si un trader conocido está a menos de TOLERANCIA_TRADER de ese precio, prefiere al de más órdenes con vos.
 * Los traders nuevos se descartan si su descripción rechaza terceros; los saltados con NEXT, siempre.
 * Devuelve { anuncio, descartados: [{apodo, motivo}] }.
 */
function elegirAnuncioVes_(montoVes, traders, frases, saltados, forzar, metodos) {
  var activos = metodos || metodosOrdenActivos_();
  var descartados = [];
  var i, r;
  if (forzar) {   // primero se busca el trader elegido en todos los métodos activos
    for (i = 0; i < activos.length; i++) {
      r = elegirAnuncioVesMetodo_(montoVes, activos[i], traders, frases, saltados, forzar, true);
      if (r.anuncio) return r;
    }
  }
  for (i = 0; i < activos.length; i++) {   // en orden de prioridad
    r = elegirAnuncioVesMetodo_(montoVes, activos[i], traders, frases, saltados);
    descartados = descartados.concat(r.descartados);
    if (r.anuncio) return { anuncio: r.anuncio, descartados: descartados };
  }
  return { anuncio: null, descartados: descartados };
}

/** Lo mismo para un solo método. soloForzar: si el trader elegido no está, no busca otro. */
function elegirAnuncioVesMetodo_(montoVes, metodo, traders, frases, saltados, forzar, soloForzar) {
  var descartados = [];
  var ads = anunciosValidos_(leerAnunciosP2P_('VES', 'SELL', metodo, Math.round(montoVes)), [metodo.toLowerCase()], true)
    .filter(function (a) { return saltados.indexOf(a.apodo) === -1; });
  if (!ads.length) return { anuncio: null, descartados: descartados };
  if (forzar) {   // elegiste vos este trader desde la página ("Este sirve")
    var f = ads.filter(function (a) { return a.apodo === forzar; })[0];
    if (f) {
      f.ordenesConVos = traders[f.apodo] || 0;
      f.descripcion = leerDescripcion_(f.adNo);
      return { anuncio: f, descartados: descartados };
    }
  }
  if (soloForzar) return { anuncio: null, descartados: descartados };
  var mejor = ads[0];
  var conocidos = ads.filter(function (a) {
    return traders[a.apodo] && a.precio >= mejor.precio * (1 - TOLERANCIA_TRADER);
  }).sort(function (x, y) { return traders[y.apodo] - traders[x.apodo]; });
  if (conocidos.length) {
    conocidos[0].ordenesConVos = traders[conocidos[0].apodo];
    return { anuncio: conocidos[0], descartados: descartados };
  }
  var memoria = leerMemoriaDescartes_();
  var revisados = 0;
  for (var i = 0; i < ads.length && revisados < MAX_DESCRIPCIONES; i++) {
    var a = ads[i];
    a.ordenesConVos = traders[a.apodo] || 0;
    if (a.ordenesConVos) return { anuncio: a, descartados: descartados };
    var m = memoria[a.adNo];
    if (m) {   // este mismo anuncio ya se descartó antes: se salta sin volver a leerlo
      m.veces++;
      m.fecha = Date.now();
      descartados.push({ apodo: a.apodo, motivo: m.motivo, recordado: true, veces: m.veces,
                         descripcion: '(ya descartado ' + m.veces + ' veces)' });
      continue;
    }
    revisados++;
    a.descripcion = leerDescripcion_(a.adNo);
    var motivo = motivoDescarte_(a.descripcion, frases);
    registrarFiltro_(a, motivo);
    if (!motivo) { guardarMemoriaDescartes_(memoria); return { anuncio: a, descartados: descartados }; }
    memoria[a.adNo] = { apodo: a.apodo, motivo: String(motivo).slice(0, 60), fecha: Date.now(), veces: 1 };
    descartados.push({ apodo: a.apodo, motivo: motivo, descripcion: String(a.descripcion).slice(0, 400) });
  }
  guardarMemoriaDescartes_(memoria);
  return { anuncio: null, descartados: descartados };
}

// ---- Memoria de anuncios descartados: cada anuncio tiene su número (adNo). Si un anuncio ya se descartó,
// durante DIAS_MEMORIA (desde la última vez que apareció) se salta directo, sin volver a leer su descripción. Otro anuncio del mismo trader
// se revisa igual. "Este sirve" en la página borra de la memoria los anuncios de ese trader.
var DIAS_MEMORIA = 30;
var MAX_MEMORIA = 60;   // la memoria vive en una propiedad del script (máx. ~9 KB)

function leerMemoriaDescartes_() {
  var m = JSON.parse(PropertiesService.getScriptProperties().getProperty('P2P_MEMORIA') || '{}');
  var limite = Date.now() - DIAS_MEMORIA * 86400000;
  Object.keys(m).forEach(function (k) { if (m[k].fecha < limite) delete m[k]; });
  return m;
}

function guardarMemoriaDescartes_(m) {
  var claves = Object.keys(m).sort(function (a, b) { return m[b].fecha - m[a].fecha; });
  var r = {};
  claves.slice(0, MAX_MEMORIA).forEach(function (k) { r[k] = m[k]; });
  PropertiesService.getScriptProperties().setProperty('P2P_MEMORIA', JSON.stringify(r));
}

function olvidarTrader_(apodo) {
  var m = leerMemoriaDescartes_();
  Object.keys(m).forEach(function (k) { if (m[k].apodo === apodo) delete m[k]; });
  guardarMemoriaDescartes_(m);
}

/** Borra toda la memoria (por ejemplo después de cambiar muchas frases). */
function borrarMemoriaDescartes() {
  PropertiesService.getScriptProperties().deleteProperty('P2P_MEMORIA');
  Logger.log('Memoria de anuncios descartados borrada');
}

/** Descripción (condiciones) de un anuncio, vía el relay. '' si no tiene. */
function leerDescripcion_(adNo) {
  var token = PropertiesService.getScriptProperties().getProperty('RELAY_TOKEN');
  var res = UrlFetchApp.fetch(RELAY_URL + '/descripcion?token=' + encodeURIComponent(token) +
                              '&adNo=' + encodeURIComponent(adNo), { muteHttpExceptions: true });
  if (res.getResponseCode() !== 200) {
    throw new Error('Relay descripción ' + res.getResponseCode() + ': ' + res.getContentText().slice(0, 200));
  }
  return JSON.parse(res.getContentText()).descripcion || '';
}

/**
 * Arma el mensaje para una remesa de montoArs pesos. Devuelve el texto (no lo envía).
 * Guarda la orden como "última" para que NEXT la pueda rehacer.
 */
function prepararOrdenP2P_(montoArs, nombre, saltados, forzar, metodos) {
  saltados = saltados || [];
  var tasa = tasaNetaActual_();
  var montoVes = Math.round(montoArs * tasa * 100) / 100;
  var r = elegirAnuncioVes_(montoVes, leerTradersVes_(), leerFrasesAlerta_(), saltados, forzar, metodos);
  var a = r.anuncio;
  PropertiesService.getScriptProperties().setProperty('P2P_DESCARTADOS', JSON.stringify(r.descartados).slice(0, 8500));
  PropertiesService.getScriptProperties().setProperty('P2P_ULTIMA', JSON.stringify({
    montoArs: montoArs, nombre: nombre || '', saltados: saltados, metodos: metodos || null, apodo: a ? a.apodo : '',
    precio: a ? a.precio : 0   // lo usa la pre-orden para mostrar la diferencia al saltar un trader
  }));
  var nuevos = r.descartados.filter(function (d) { return !d.recordado; });
  var conocidos = r.descartados.length - nuevos.length;
  var desc = [
    nuevos.length ? 'Descartados: ' + nuevos.map(function (d) { return d.apodo + ' ("' + d.motivo + '")'; }).join(' · ') : '',
    conocidos ? 'Ya conocidos, saltados: ' + conocidos : ''
  ].filter(String).join('\n');
  if (!a) {
    return ['Sin anuncios VES para ' + fmtW_(montoVes, 0) + ' Bs por ' + (metodos || metodosOrdenActivos_()).join(', ') +
            (saltados.length ? ' (saltados: ' + saltados.join(', ') + ')' : '') + '.', desc]
           .filter(String).join('\n');
  }
  var usdt = Math.ceil(montoVes / a.precio * 100) / 100;
  var lineas = [
    nombre ? '*' + nombre + '*' : '*Orden P2P*',
    fmtM_(montoArs, 0) + ' ARS × ' + fmtM_(tasa, 3) + ' = *' + fmtM_(montoVes, 0, true) + ' Bs*',
    'Vender *' + fmtM_(usdt, 2) + ' USDT* · precio ' + fmtW_(Math.round(a.precio), 0),
    '👤 ' + [a.apodo,
             a.ordenesConVos ? a.ordenesConVos + (a.ordenesConVos === 1 ? ' orden' : ' órdenes') + ' con vos' : 'nuevo',
             a.pagos.join(', ')].join(' · '),
    LINK_ANUNCIO + a.adNo
  ];
  if (!a.ordenesConVos) {
    lineas.push('', '📝 ' + (String(a.descripcion || '').trim().slice(0, 500) || 'sin descripción'));
  }
  if (desc) lineas.push('', desc);
  if (!a.ordenesConVos || desc) lineas.push('', '⏭️ Saltar o ajustar frases:', linkNext_());
  return lineas.join('\n');
}

/** Guarda una frase en la hoja. tipo: 'BLOQUEAR' o 'PERMITIR'. */
function guardarFrase_(frase, apodo, tipo) {
  var sh = hojaFiltro_();
  var fila = 2;
  while (sh.getRange(fila, 1).getValue() !== '') fila++;   // primera fila libre en A (appendRow usaría la del registro)
  sh.getRange(fila, 1, 1, 4).setValues([[frase, new Date(), apodo || '', tipo]]);
}

/**
 * Rehace la última orden.
 *   accion 'next'     → salta al trader actual (y guarda la frase como BLOQUEAR si hay).
 *   accion 'permitir' → guarda la frase como PERMITIR y rehace sin saltar a nadie nuevo.
 */
function manejarNextP2P_(texto, accion) {
  try {
    var u = JSON.parse(PropertiesService.getScriptProperties().getProperty('P2P_ULTIMA') || 'null');
    if (!u) { sendWhatsAppMessage_(MI_TELEFONO, 'No hay una orden P2P reciente para rehacer.'); return; }
    var frase = String(texto || '').replace(/^\s*next\b[\s:,-]*/i, '').trim();
    var saltados = u.saltados, aviso;
    var forzar = null;
    if (accion && accion.indexOf('usar:') === 0) {
      forzar = accion.slice(5);
      olvidarTrader_(forzar);
      if (frase) guardarFrase_(frase, forzar, 'PERMITIR');
      aviso = '✅ Usando ' + forzar + (frase ? ' · permitida: ' + frase : '') + '\n\n';
    } else if (accion === 'permitir') {
      if (frase) guardarFrase_(frase, u.apodo, 'PERMITIR');
      aviso = '✅ Permitida: ' + frase + '\n\n';
    } else {
      if (frase) guardarFrase_(frase, u.apodo, 'BLOQUEAR');
      saltados = saltados.concat(u.apodo ? [u.apodo] : []);
      aviso = (frase ? '🚫 Bloqueada: ' + frase + '\n' : '') + '⏭️ Salteado ' + (u.apodo || '') + '\n\n';
    }
    sendWhatsAppMessage_(MI_TELEFONO, aviso + prepararOrdenP2P_(u.montoArs, u.nombre, saltados, forzar, u.metodos));
  } catch (e) {
    logError_('manejarNextP2P_', e.message || e);
    sendWhatsAppMessage_(MI_TELEFONO, '⚠️ NEXT falló: ' + (e.message || e));
  }
}

/** Prueba por WhatsApp: arma la orden para 20.000 ARS y te la manda a vos. No abre nada. */
function enviarOrdenPruebaP2P() {
  try {
    sendWhatsAppMessage_(MI_TELEFONO, prepararOrdenP2P_(20000, 'Prueba'));
  } catch (e) {
    logError_('enviarOrdenPruebaP2P', e.message || e);
    throw e;
  }
}

// ==========================================
// NEXT POR LINK: el mensaje trae un link a una página chiquita con un campo para la frase
// y un botón. No depende de leer tus mensajes de WhatsApp.
// Usa la misma implementación web que el webhook de WAHA (la URL /exec).
// ==========================================

/** Clave secreta para que solo tus links puedan saltar órdenes. Se crea sola la primera vez. */
function claveNext_() {
  var props = PropertiesService.getScriptProperties();
  var k = props.getProperty('P2P_CLAVE');
  if (!k) { k = Utilities.getUuid().replace(/-/g, ''); props.setProperty('P2P_CLAVE', k); }
  return k;
}

function linkNext_() {
  // WEBAPP_URL: la URL /exec que usa WAHA (propiedad del script). Si falta, la que da Google.
  var base = PropertiesService.getScriptProperties().getProperty('WEBAPP_URL') || ScriptApp.getService().getUrl();
  return base + '?p2p=next&k=' + claveNext_();
}

/** Página del link. Solo responde si la clave es correcta. */
function doGet(e) {
  var p = (e && e.parameter) || {};
  if (p.p2p === 'pre' && p.k === claveNext_()) return paginaPreOrden_(p);   // 11_PreOrden.gs
  if (p.p2p !== 'next' || p.k !== claveNext_()) {
    return HtmlService.createHtmlOutput('No autorizado');
  }
  var props = PropertiesService.getScriptProperties();
  var u = JSON.parse(props.getProperty('P2P_ULTIMA') || '{}');
  var desc = JSON.parse(props.getProperty('P2P_DESCARTADOS') || '[]');
  var esc = function (t) { return String(t || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); };
  var boton = 'style="margin-top:8px;width:100%;font-size:18px;padding:12px"';
  var campo = 'style="width:100%;font-size:16px;padding:8px;box-sizing:border-box"';
  var tarjetas = desc.map(function (d, i) {
    return '<div style="border:1px solid #ccc;border-radius:8px;padding:10px;margin:10px 0">' +
      '<b>' + esc(d.apodo) + '</b> <span style="color:#a00">🚫 "' + esc(d.motivo) + '"</span>' +
      '<p style="font-size:15px;white-space:pre-wrap">' + esc(d.descripcion) + '</p>' +
      '<input id="f' + i + '" ' + campo + ' placeholder="Frase que sí sirve (opcional)">' +
      '<button ' + boton + ' onclick="ir(\'usar:\'+' + esc(JSON.stringify(d.apodo)) + ',\'f' + i + '\')">✅ Este sirve: usarlo</button></div>';
  }).join('');
  var wa = 'https://wa.me/' + MI_TELEFONO;
  var html =
    '<meta name="viewport" content="width=device-width,initial-scale=1">' +
    '<div style="font-family:sans-serif;font-size:17px;padding:14px;max-width:520px">' +
    '<p>Trader actual: <b>' + esc(u.apodo || '?') + '</b></p>' +
    '<input id="f" ' + campo + ' placeholder="Frase a bloquear (opcional)">' +
    '<button ' + boton + ' onclick="ir(\'next\',\'f\')">⏭️ NEXT (saltar este)</button>' +
    (desc.length ? '<h3 style="margin-top:22px">Descartados (' + desc.length + ')</h3>' + tarjetas : '') +
    '<p id="r" style="font-size:18px"></p></div>' +
    '<script>function ir(accion,campo){' +
    'document.querySelectorAll("button").forEach(function(b){b.disabled=true;});' +
    'document.getElementById("r").textContent="Buscando...";window.scrollTo(0,document.body.scrollHeight);' +
    'google.script.run.withSuccessHandler(function(m){document.getElementById("r").innerHTML=m+' +
    '\'<br><br><a target="_top" href="' + wa + '" style="font-size:20px">↩️ Volver a WhatsApp</a>\';' +
    'try{window.top.location.href="' + wa + '";}catch(x){}})' +
    '.withFailureHandler(function(err){document.getElementById("r").textContent="Error: "+err.message;' +
    'document.querySelectorAll("button").forEach(function(b){b.disabled=false;});})' +
    '.nextP2PWeb(' + JSON.stringify(p.k) + ',document.getElementById(campo).value,accion);}</script>';
  return HtmlService.createHtmlOutput(html).setTitle('NEXT P2P');
}

/** Lo llaman los botones de la página. */
function nextP2PWeb(k, frase, accion) {
  if (k !== claveNext_()) throw new Error('No autorizado');
  frase = String(frase || '').trim().slice(0, 200);
  accion = String(accion || 'next');
  manejarNextP2P_(frase, accion.indexOf('usar:') === 0 ? accion : 'next');
  return 'Listo. Te mandé el resultado por WhatsApp.';
}
