// ==========================================
// MÓDULO 22: INTAKE — qué quiere el cliente y qué le contestarías vos
//
// Etapa 1 del diseño "Bexo · Diseño del intake de WhatsApp": SOLO calcula, no manda nada.
//   intencionesIntake_(texto, media)  → ['saludo','tasa','calculo',...] (varias por tanda)
//   pedidoDeCalculo_(texto)           → {de:'ARS'|'VES'|'USD'|'EUR', monto, base} o null
//   calcularIntake_(pedido, tasas)    → {texto:'15.600 bs', ars, ves} o null
//   aliasParaCobrar_(ars)             → {alias:[...], mitad:bool}
//   respuestaIntake_(texto, media, ctx) → {intenciones, mensajes:[...], tipos:[...], manual}
// Las respuestas copian tus frases (sacadas de 5.839 mensajes de WAHA, ago–nov 2026).
// Pruebas: node pruebas/probar_intake_appscript.js [chats_waha.json.gz]
// Usa de otros archivos (si están): MAPA_CUENTAS de 4_LeerComprobantes, cuentasParaCobrar_ y
// CUENTAS_PAUSADAS de 5_Dashboard, tasaNetaActual_ de 9_P2P, CONFIG de 0_Config.
// ==========================================

var INTAKE_MITAD_DESDE = 250000;      // ARS: desde acá "Envía mitad y mitad" a dos alias
var INTAKE_CACHE_TASAS_SEG = 1800;
var INTAKE_YADIO_URL = 'https://api.yadio.io/exrates/USD';

var FRASES_JOHN = {
  disponible:  'Si tengo disponibilidad',
  ya_te_digo:  'Ya te digo',
  alias:       'Puedes transferir a este alias',
  aliasDos:    'Puedes transferir a estos alias',
  mitad:       'Envía mitad y mitad',
  en_proceso:  'Ok fino te aviso apenas tenga el capturé',
  confirma_cuenta: 'Confírmame a qué cuenta',
  cierre:      'Listo mí pana 👍🏼'
};

function normIntake_(t) {
  return String(t || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/\s+/g, ' ').trim();
}

// Reglas por intención. Se prueban todas: una tanda puede tener varias.
var REGLAS_INTAKE = [
  ['saludo',        /\b(hola+|holi+|buen(as|os)|buen ?dias?|buen(a|o)s? (tardes?|noches?|dias?)|bns|que (tal|hay|mas)|como (estas|andas|vas|esta)|saludos|epale)\b/],
  ['disponibilidad',/(habra|hay|tendra[s]?|tienes|tenes|tenias) (tiempo|chance|disponib\w*|cupo|para (enviar|mandar|pasar|cambiar|transferir))|estas (laburando|trabajando|activo|operando|enviando|mandando|disponible)|(puedo|podemos|podria|se puede|puedes) (mandar|enviar|hacer|cambiar|transferir)|hay posibilidad|hasta (que|q) hora|feriado|horita|por la hora|atendiendo|disponibilidad/],
  ['tasa',          /\b(tasa|taza|tarifa|cambio de hoy|el cambio|cotizacion|remesa|a como (esta|tienes|tenes|la)|como (esta|tienes|tenes) (la|el) (tasa|cambio|dolar)|mismo valor)/],
  ['calculo',       /(cuant[oa]s?\b|(llegue|lleguen|llegar|llegaria|llegarian)\b|serian? \d|\bequivale|\bda \d|en (pesos|bolivares|bs|dolares)\?|tasa bcv|(a )?base de euro|tasa euro)/],
  ['monto',         /(\d+\s*(mil|k|lucas?)\b|\d[\d.,]{2,}\s*(pesos|bs|bsf|bolivares|\$|usd|dolares|ars|€)|\$\s*\d|\d\s*(\$|usd|dolares|dolar|dolres|€|euros?)|(mandar|enviar|pasar|transferir(te)?|depositar(te)?|cambiar|pasarte) \d|^\d{4,6}$)/],
  ['quiere_enviar', /((quiero|quisiera|necesito|queria|tengo (q|que)|voy a|para) (mandar|enviar|pasar|hacer un envio|cambiar|transferir)|(puedo|podria) (hacer )?(un )?envio|para (mandar|enviar) esto|(enviar|mandar) (esto|algo)|me (podrias|puedes) enviar)/],
  ['pide_alias',    /(alias|cbu|cvu|(a|en) donde (te )?(los |lo |la )?(mando|envio|transfiero|deposito|paso)|donde te (paso|transfiero|mando|envio|deposito)|(pasame|me pasas?|me das|me envias|me dices) (un|el|tu|la|los) (dato|alias|numero|cuenta|cbu)|cuenta tuya|tu cuenta|a (que|q) cuenta te)/],
  ['avisa_pago',    /(ya te (pase|mande|envie|transferi|lo pase)|ahi (te )?(va|esta|lo tienes|te lo)|^listo\b|te (lo )?(transferi|pase)|ya (lo )?(hice|pague|transferi)|ahi te (envio|paso|mando)|ya te (envio|paso))/],
  ['datos_cuenta',  /(\b01\d\d\b|\b04\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}\b|\b0\d{3}\s?\d{7}\b|pago movil|banesco|banco (de )?venezuela|\bbdv\b|\bbnc\b|mercantil|provincial|banplus|bancamiga|venezolano de credito|\bnequi\b|\bpix\b|bancolombia|daviplata|cedula|\bc\.?i\b)/],
  ['destino_ref',   /(la de siempre|(a )?la misma|(el )?mismo (numero|de|pago)|(a|para|en) (esa|esta|este|ese|aqui|alli|aca)\b|misma cuenta|cta de siempre|cuenta de (siempre|ayer|antes)|igual que (ayer|la otra|siempre)|(a|para) (la cuenta de )?mi (mama|papa|hermana|hermano|esposa|hija|hijo|tia|abuela|madre|padre|amiga|amigo|prima|primo))/],
  ['division',      /((\d.*(a|para) (esta|esa|una).*(el resto|la otra|otra cuenta))|el resto a|divid|la mitad|dos cuentas|\d+ a una y)/],
  ['pide_capture',  /((me (pasas?|envias|mandas)|pasame) (el )?(capture|captur|comprobante)|apenas tengas (el )?captur|captur.* (te lo pasaron|me lo (envias|pasas))|confirmame si|ya (lo )?(enviaste|mandaste|hiciste)\?)/],
  ['incidente',     /(no (ha )?(llego|llegado|me llego|le llego|recib)|rebot|devuelv|devuelven|falta plata|falto plata|nada que|aun no (sabes|llega)|ayer no transferiste|sale (que hay )?error|me dice error|no existe)/],
  ['otra_ruta',     /(colombia|brasil|brazil|\bpix\b|nequi|neki|peso colombiano|reais|peru|soles|\byape\b|\bplin\b|chile|de venezuela (para|a)|desde venezuela|me van a enviar de|tengo (en venezuela)?[ /]*[\d.,]+ ?(mil )?(bs|bolivares)|(bs|bolivares) en (el )?(banco|venezuela|bdv)|en dolares\b|cuantos dolares|zelle|(te )?(podre|puedo|podria) (pasar|mandar|enviar|dar)(te)? (unos |algunos )?(bs|bolivares)|(bs|bolivares).{0,40}(me los|me lo) (pases|des|cambies|transfieras|mandes))/],
  ['difusion',      /(\bgente\b|a todos|mis amigos|familiares y contactos|tomando pedido|rifa|lanzamiento|promo(cion)?\b|sorteo|estaremos)/],
  ['gracias',       /(gracias|graciaz|graciaa|grax|bendicion|dios te)/]
];
var CONFIRMA_INTAKE = /^(si+|dale+|ok+|okis|okey|oki|perfecto|correcto|exacto|va|si va|esa|eso|listo|fino|de una|bueno)[\s.!👍🙏]*$/;

function intencionesIntake_(texto, media) {
  var lineas = String(texto || '').split('\n').map(function (l) { return l.trim(); })
    .filter(function (l) { return l && !/^\[mensaje sin texto\]$/i.test(l); });
  var t = normIntake_(lineas.join(' / '));
  var out = [];
  if (media) out.push('comprobante');
  REGLAS_INTAKE.forEach(function (r) { if (r[1].test(t)) out.push(r[0]); });
  if (lineas.some(function (l) { return CONFIRMA_INTAKE.test(normIntake_(l)); })) out.push('confirma');
  if (/\d\s*(\$|usd|dolares|dolar|dolres)|\$\s*\d{1,3}\b(?![.,]\d{3})|tasa bcv|\bbcv\b|euro/.test(t) ||
      /(llegue|lleguen|llegar)\s+(alla\s+)?\d{1,3}(?![\d.,]|\s*(mil|k|luca|bs|bolivares|pesos))/.test(t)) out.push('usd');
  // "pasame el capture" o "apenas tengas capture" no es un aviso de pago
  if (out.indexOf('pide_capture') !== -1) out = out.filter(function (x) { return x !== 'avisa_pago'; });
  return out;
}

// ---------- cálculo ----------
function numeroIntake_(s, mil) {
  s = String(s).replace(/\s/g, '');
  var n;
  if (/^\d{1,3}([.,]\d{3})+([.,]\d{1,2})?$/.test(s)) {          // 30.000 / 2.300,00 / 1,234.50
    var dec = s.match(/[.,](\d{1,2})$/);
    var ent = dec ? s.slice(0, -dec[0].length) : s;
    n = Number(ent.replace(/[.,]/g, '')) + (dec ? Number('0.' + dec[1]) : 0);
  } else n = Number(s.replace(',', '.'));
  return mil ? n * 1000 : n;
}

/** Qué cálculo pide el cliente. de = la moneda del monto que dio; base = BCV o EURO si habla de dólares/euros. */
function pedidoDeCalculo_(texto) {
  var t = normIntake_(texto).replace(/\[mensaje sin texto\]/g, ' ');
  var base = /euro/.test(t) ? 'EURO' : 'BCV';
  var NUM = '(\\d[\\d.,]*\\d|\\d)';
  var m;
  t = t.replace(/(\d+(?:[.,]\d+)?)\s*(millon(es)?|palo)s?\b( de| d)?/g, function (x, n) { return String(Math.round(Number(n.replace(',', '.')) * 1e6)) + ' '; });
  // "¿cuánto es en pesos?" / "¿cuántos pesos?": el monto que dio son bolívares
  var enBs = /(cuanto|cuantos) (es |son |seria |serian |sería )?en pesos|cuantos pesos|cuanto (te )?(tengo|debo) (que |q )?(enviar|transferir|pasar|depositar)/.test(t);
  // "para que llegue(n) (allá) 15": número chico sin moneda = dólares a tasa BCV (así lo usan tus clientes)
  if ((m = t.match(/(llegue|lleguen|llegar|llegaran|lleguen alla|llegue alla)\s+(alla\s+)?(\d{1,3})(?![\d.,]|\s*(mil|k|luca|bs|bolivares|pesos|ars))/))) {
    return { de: base === 'EURO' ? 'EUR' : 'USD', monto: Number(m[3]), base: base };
  }
  if ((m = t.match(new RegExp(NUM + '\\s*(\\$|usd|dolares|dolar|dolres|verdes)'))) ||
      (m = t.match(new RegExp('\\$\\s*' + NUM + '(?![\\d.,])')))) {
    var v = numeroIntake_(m[1]);
    if (/^\$/.test(m[0].trim()) && v >= 1000) return { de: 'ARS', monto: v };   // "$31.000" son pesos
    return { de: base === 'EURO' ? 'EUR' : 'USD', monto: v, base: base };
  }
  if ((m = t.match(new RegExp(NUM + '\\s*(mil|k|lucas?)?\\s*(bs|bsf|bolivares|bolos)\\b')))) {
    return { de: 'VES', monto: numeroIntake_(m[1], !!m[2]) };
  }
  if ((m = t.match(new RegExp(NUM + '\\s*(mil|k|lucas?)?\\s*(pesos|ars|mangos)?')))) {
    // el primer número "de plata": salta teléfonos, cédulas y cuentas
    var re = new RegExp(NUM + '\\s*(mil|k|lucas?)?\\s*(pesos|ars|mangos)?', 'g'), x;
    while ((x = re.exec(t))) {
      var crudo = x[1].replace(/[.,]/g, '');
      if ((crudo.length >= 7 && !x[3]) || /^0\d/.test(crudo)) continue;     // 0412..., cédulas, cuentas
      var val = numeroIntake_(x[1], !!x[2]);
      if (!x[2] && !x[3] && val < 1000) {
        if (!/(mandar|enviar|pasar|transferir|depositar|cambiar)\s*$/.test(t.slice(0, x.index).trim() + ' ') &&
            !/(mandar|enviar|pasar|transferir|depositar|cambiar) $/.test(t.slice(Math.max(0, x.index - 12), x.index))) continue;
        val *= 1000;                                               // "tengo q mandar 60" = 60 mil
      }
      if (val < 1000) continue;
      return { de: (enBs && !x[3]) ? 'VES' : 'ARS', monto: val };
    }
  }
  return null;
}

function redondearIntake_(v, a) { return Math.round(v / a) * a; }
function milesIntake_(v) { return String(Math.round(v)).replace(/\B(?=(\d{3})+(?!\d))/g, '.'); }

/** tasas = {neta: Bs por peso, usd: Bs por dólar BCV, eur: Bs por euro BCV}. Devuelve lo que contestarías. */
function calcularIntake_(p, tasas) {
  if (!p || !tasas || !(tasas.neta > 0)) return null;
  var ves, ars;
  if (p.de === 'ARS') { ars = p.monto; ves = redondearIntake_(ars * tasas.neta, 100); return { ars: ars, ves: ves, texto: milesIntake_(ves) + ' bs' }; }
  if (p.de === 'VES') { ves = p.monto; ars = redondearIntake_(ves / tasas.neta, 100); return { ars: ars, ves: ves, texto: milesIntake_(ars) + ' pesos' }; }
  var porUnidad = p.de === 'EUR' ? tasas.eur : tasas.usd;
  if (!(porUnidad > 0)) return null;                                // sin tasa BCV/euro: a mano
  ves = p.monto * porUnidad;
  ars = redondearIntake_(ves / tasas.neta, 100);
  return { ars: ars, ves: Math.round(ves), texto: milesIntake_(ars) + ' pesos' };
}

/**
 * Tasa neta (hoja Tasas) + Bs por dólar y por euro oficiales (BCV). Fuentes en orden, la primera que dé un valor sano:
 *   1. ve.dolarapi.com (/v1/dolares/oficial y /v1/euros/oficial)
 *   2. Yadio (si su respuesta trae BCV)
 *   3. TASA_BCV / TASA_EURO de la config (a mano)
 *   4. la última buena guardada (hasta 72 h), por si todo lo anterior se cae
 * Un valor más del triple o menos de un tercio del último bueno se descarta (falla de la API).
 */
var INTAKE_FUENTES_BCV = {
  usd: ['https://ve.dolarapi.com/v1/dolares/oficial'],
  eur: ['https://ve.dolarapi.com/v1/euros/oficial']
};
var INTAKE_ULTIMA_HORAS = 72;

function jsonDe_(url) {
  try {
    var r = UrlFetchApp.fetch(url, { muteHttpExceptions: true, headers: { Accept: 'application/json' } });
    return r.getResponseCode() === 200 ? JSON.parse(r.getContentText()) : null;
  } catch (e) { return null; }
}

/** Saca un número de las formas conocidas: {promedio}, {venta}, {official}, {data:{official}}, [{fuente:'oficial',...}] */
function valorOficial_(j) {
  if (!j) return 0;
  if (Array.isArray(j)) { var o = j.filter(function (x) { return /oficial|bcv/i.test(x.fuente || x.nombre || ''); })[0]; return valorOficial_(o); }
  if (j.data) return valorOficial_(j.data);
  return Number(j.promedio || j.official || j.venta || j.price || 0);
}

function sano_(v, anterior) {
  return v > 0 && isFinite(v) && !(anterior > 0 && (v > anterior * 3 || v < anterior / 3));
}

function tasasIntake_() {
  var t = { neta: 0, usd: 0, eur: 0, fuente: {} };
  try { t.neta = tasaNetaActual_(); } catch (e) {}
  var cache = CacheService.getScriptCache(), c = cache.get('intake_tasas_bcv');
  if (c) { var o = JSON.parse(c); t.usd = o.usd; t.eur = o.eur; t.fuente = o.fuente; return t; }

  var props = PropertiesService.getScriptProperties();
  var ultima = JSON.parse(props.getProperty('INTAKE_ULTIMA_BCV') || '{}');
  var yadio = null;
  ['usd', 'eur'].forEach(function (k) {
    var ant = ultima[k] || 0, v = 0;
    INTAKE_FUENTES_BCV[k].some(function (url) { v = valorOficial_(jsonDe_(url)); return sano_(v, ant); });
    if (sano_(v, ant)) { t[k] = v; t.fuente[k] = 'dolarapi'; return; }
    if (yadio === null) yadio = jsonDe_(INTAKE_YADIO_URL) || {};
    var b = yadio.BCV || yadio.bcv || {};
    v = Number(b[k.toUpperCase()] || b[k] || 0);
    if (sano_(v, ant)) { t[k] = v; t.fuente[k] = 'yadio'; return; }
    var cfg = (typeof CONFIG !== 'undefined') ? CONFIG : {};
    v = Number(cfg[k === 'usd' ? 'TASA_BCV' : 'TASA_EURO']) || 0;
    if (v > 0) { t[k] = v; t.fuente[k] = 'config'; return; }
    if (ant > 0 && Date.now() - (ultima.ts || 0) < INTAKE_ULTIMA_HORAS * 3600e3) { t[k] = ant; t.fuente[k] = 'última guardada'; }
  });
  if (t.fuente.usd === 'dolarapi' || t.fuente.usd === 'yadio') {
    props.setProperty('INTAKE_ULTIMA_BCV', JSON.stringify({ usd: t.usd, eur: t.eur || ultima.eur || 0, ts: Date.now() }));
  }
  if (t.usd > 0) cache.put('intake_tasas_bcv', JSON.stringify({ usd: t.usd, eur: t.eur, fuente: t.fuente }), INTAKE_CACHE_TASAS_SEG);
  return t;
}

/** Para mirar cada fuente (ejecutar en el editor). */
function probarTasasIntake() {
  ['usd', 'eur'].forEach(function (k) {
    INTAKE_FUENTES_BCV[k].forEach(function (u) { Logger.log(k + ' ' + u + ' → ' + valorOficial_(jsonDe_(u))); });
  });
  var y = jsonDe_(INTAKE_YADIO_URL) || {};
  Logger.log('Yadio: claves ' + Object.keys(y).join(', ') + ' · USD→VES ' + (y.USD && y.USD.VES) +
    ' · BCV ' + JSON.stringify(y.BCV || y.bcv || null));
  CacheService.getScriptCache().remove('intake_tasas_bcv');
  Logger.log('Queda: ' + JSON.stringify(tasasIntake_()));
}

// ---------- alias ----------
/** Alias de cobro según el dashboard. ctx.cuentas = lista ordenada de códigos (si no, la recomendación del dashboard). */
function aliasParaCobrar_(ars, cuentasOrdenadas) {
  var porCuenta = {};
  var mapa = (typeof MAPA_CUENTAS !== 'undefined') ? MAPA_CUENTAS : {};
  Object.keys(mapa).forEach(function (k) {
    if (/^john\./i.test(k) && !porCuenta[mapa[k]]) porCuenta[mapa[k]] = k.toLowerCase().replace(/^john/, 'John');
  });
  var pausadas = (typeof CUENTAS_PAUSADAS !== 'undefined') ? CUENTAS_PAUSADAS : [];
  if (!cuentasOrdenadas && typeof cuentasParaCobrar_ === 'function') cuentasOrdenadas = cuentasParaCobrar_();
  var lista = (cuentasOrdenadas || []).filter(function (c) { return porCuenta[c] && pausadas.indexOf(c) === -1; });
  var mitad = Number(ars) > INTAKE_MITAD_DESDE;
  var alias = lista.slice(0, mitad ? 2 : 1).map(function (c) { return porCuenta[c]; });
  return { alias: alias, mitad: mitad && alias.length === 2 };
}

// ---------- respuesta ----------
function saludoIntake_(hora) {
  return hora < 12 ? 'Hola buenos días como estás' : (hora < 19 ? 'Hola buenas tardes como estás' : 'Hola buenas noches como estás');
}

/**
 * Lo que contestarías a una tanda del cliente. ctx = {tasas, hora, cuentas (orden de cobro), yaSaludo}.
 * tipos: saludo, disponible, tasa, calculo, alias, en_proceso. manual = true cuando es para vos.
 */
function respuestaIntake_(texto, media, ctx) {
  ctx = ctx || {};
  var it = intencionesIntake_(texto, media), tiene = function (k) { return it.indexOf(k) !== -1; };
  var r = { intenciones: it, mensajes: [], tipos: [], manual: false, motivo: '' };
  var a_mano = function (m) { r.manual = true; r.motivo = r.motivo || m; };
  if (tiene('difusion') && !tiene('comprobante')) { a_mano('difusión'); return r; }
  if (tiene('saludo') && !ctx.yaSaludo) { r.mensajes.push(saludoIntake_(ctx.hora == null ? 12 : ctx.hora)); r.tipos.push('saludo'); }
  if (tiene('incidente') || tiene('otra_ruta') || tiene('division')) {
    a_mano(tiene('incidente') ? 'incidente' : (tiene('division') ? 'división' : 'otra ruta'));
    return r;
  }
  // foto (o los datos que faltaban después de la foto): una sola vez por operación
  if ((tiene('comprobante') && !tiene('calculo')) ||
      (ctx.fotoPendiente && (tiene('datos_cuenta') || tiene('destino_ref')))) {
    if (!ctx.enProceso) { r.mensajes.push(FRASES_JOHN.en_proceso); r.tipos.push('en_proceso'); }
    return r;
  }
  var tasas = ctx.tasas || {}, calc = null, pedido = pedidoDeCalculo_(texto);
  if (tiene('disponibilidad') || (tiene('quiere_enviar') && !tiene('calculo') && !tiene('pide_alias')) ||
      (tiene('monto') && !tiene('calculo') && !tiene('pide_alias') && !tiene('datos_cuenta') &&
       (pedido || {}).de !== 'VES')) {
    r.mensajes.push(FRASES_JOHN.disponible); r.tipos.push('disponible');
  }
  if (tiene('calculo')) {
    calc = calcularIntake_(pedido, tasas);
    if (calc) { r.mensajes.push(calc.texto); r.tipos.push('calculo'); }
    else if (pedido) a_mano(pedido.de === 'USD' || pedido.de === 'EUR' ? 'sin tasa BCV/euro' : 'cálculo sin tasa');
    else if (!tiene('tasa')) a_mano('cálculo sin monto claro');
  }
  if (tiene('tasa') && !calc) {
    if (tasas.neta > 0) { r.mensajes.push(String(tasas.neta)); r.tipos.push('tasa'); } else a_mano('sin tasa');
  }
  if (tiene('pide_alias')) {
    var a = aliasParaCobrar_(calc ? calc.ars : (pedido || {}).monto, ctx.cuentas);
    if (a.alias.length) {
      r.mensajes.push(a.alias.length > 1 ? FRASES_JOHN.aliasDos : FRASES_JOHN.alias);
      a.alias.forEach(function (x) { r.mensajes.push(x); });
      if (a.mitad) r.mensajes.push(FRASES_JOHN.mitad);
      r.tipos.push('alias');
    } else a_mano('sin alias');
  }
  var algo = r.tipos.length || ['gracias', 'confirma', 'datos_cuenta', 'destino_ref', 'pide_capture', 'avisa_pago', 'saludo']
    .some(function (k) { return tiene(k); });
  var corto = normIntake_(texto).split(' ').length <= 8 && texto.indexOf('?') === -1;
  if (!algo && !corto) a_mano('pregunta general');
  return r;
}
