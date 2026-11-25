/**
 * 20_DashboardP2P.gs — Calcula los números de la Brújula P2P (tablero P2P) y los entrega en JSON.
 *
 * - Lo pide el servidor del tablero en el VPS (vps/dashboard_p2p.py) cada 10 min:
 *   GET <url /exec>?dash=1&k=<DASH_TOKEN>   (la rama está en doGet, 9_P2P.gs)
 * - Solo LEE: Ordenes_P2P (esta planilla) y Movs UY (Registro BEXO). No escribe nada.
 * - Propiedades del script: DASH_TOKEN (la crea configurarTableroP2P) y DASH_CICLO_DESDE (dd/MM/yyyy),
 *   el día en que arrancó el ciclo UYU actual (si falta, toma los últimos 14 días). Al cerrar un ciclo, cambiala.
 *
 * Para probar desde el editor: ejecutá probarDashboardP2P y mirá el registro.
 */
var DASH_LIMITE_PENDIENTE = 150;     // USDT que se pueden deber antes de frenar la venta
var DASH_PENDIENTE_BAJO = 50;        // debajo de esto se puede bajar la venta
var DASH_MARGEN_MIN = 0.05;          // 5 % mínimo entre compra y venta
var DASH_CUPO_CUENTA = 120000;       // UYU por mes por cuenta
var DASH_CUENTAS_UY = ['Prex', 'MercadoPago', 'OcaBlue', 'MiDinero', 'Itau'];
var DASH_SIN_ORDENES_MIN = 120;      // minutos sin órdenes en hora de movimiento para mover el precio
var DASH_HORA_DESDE = 10, DASH_HORA_HASTA = 23;
// OKX sin moneda (la API no la trae y el historial del teléfono no siempre llega): john opera OKX solo en UYU (24/11).
// Se cuentan como esta moneda, con monto = cantidad × último precio OKX conocido del mismo tipo, marcadas "supuesto".
// Vacío = no suponer (quedan como "sin moneda" y lo que debés se muestra como rango).
var DASH_OKX_SIN_MONEDA = '';

function dashboardP2PRespuesta_(p) {
  var salida = function (obj) {
    return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
  };
  var token = CONFIG.DASH_TOKEN;
  if (!token || p.k !== token) return salida({ error: 'no autorizado' });
  try {
    var vivos = {};
    try { vivos = JSON.parse(p.vivos || '{}'); } catch (x) { vivos = {}; }
    return salida(dashboardP2P_(vivos));
  } catch (e) {
    logError_('dashboardP2P_', e.message || e);
    return salida({ error: String(e.message || e) });
  }
}

/**
 * Ejecutar UNA vez desde el editor: crea la clave DASH_TOKEN (si no existe) y escribe en el registro
 * la dirección completa que hay que pegar en el VPS cuando la pide dashboard_instalar.sh.
 */
function configurarTableroP2P() {
  var props = PropertiesService.getScriptProperties();
  var token = props.getProperty('DASH_TOKEN');
  if (!token) {
    token = Utilities.getUuid().replace(/-/g, '');
    props.setProperty('DASH_TOKEN', token);
  }
  if (!props.getProperty('DASH_CICLO_DESDE')) props.setProperty('DASH_CICLO_DESDE', '03/11/2026');
  // La dirección es la /exec de la implementación web que actualiza subir.sh (la misma que usa WAHA), no la que
  // devuelve getUrl() desde el editor, que puede ser de otra implementación.
  Logger.log('Pegá esto en el VPS (cambiando ID por el de tu implementación, el "Deployed AKfycb..." de subir.sh):\n' +
             'https://script.google.com/macros/s/ID/exec?dash=1&k=' + token);
}

function probarDashboardP2P() {
  Logger.log(JSON.stringify(dashboardP2P_(), null, 1));
}

// ---------- lectura ----------

function dashNum_(x) {
  if (typeof x === 'number') return x;
  var s = String(x || '').trim();
  if (!s) return 0;
  return parseFloat(s.replace(/,/g, '')) || 0;
}

/** Date o texto "dd/MM/yyyy HH:mm[:ss]" → Date (o null). */
function dashFecha_(x) {
  if (x instanceof Date) return isNaN(x) ? null : x;
  var m = String(x || '').match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?/);
  if (!m) return null;
  return new Date(+m[3], +m[2] - 1, +m[1], +(m[4] || 0), +(m[5] || 0), +(m[6] || 0));
}

function dashLeerOrdenes_() {
  var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(HOJA_ORDENES_P2P);
  if (!sh || sh.getLastRow() < 2) return [];
  var v = sh.getDataRange().getValues();
  var h = {};
  v[0].forEach(function (n, i) { h[n] = i; });
  var lista = v.slice(1).map(function (r) {
    return {
      ex: String(r[h['Exchange']] || ''),
      f: dashFecha_(r[h['Creada']]),
      tipo: String(r[h['Tipo']] || ''),
      cripto: String(r[h['Cripto']] || ''),
      cant: dashNum_(r[h['Cantidad']]),
      mon: String(r[h['Moneda']] || ''),
      monto: dashNum_(r[h['Monto']]),
      precio: dashNum_(r[h['Precio']]),
      contra: String(r[h['Contraparte']] || ''),
      estado: String(r[h['Estado']] || ''),
      rol: String(r[h['Rol']] || ''),
      ad: String(r[h['Anuncio']] || '').replace(/^'/, '')
    };
  }).filter(function (o) { return o.f; });
  if (DASH_OKX_SIN_MONEDA) dashSuponerOKX_(lista);
  return lista;
}

/** Completa las órdenes OKX sin moneda con DASH_OKX_SIN_MONEDA y el último precio OKX conocido del mismo tipo. */
function dashSuponerOKX_(lista) {
  var okx = lista.filter(function (o) { return o.ex === 'OKX'; }).sort(function (a, b) { return a.f - b.f; });
  var ultimo = {};
  okx.forEach(function (o) {
    if (o.mon) { if (o.precio) ultimo[o.tipo] = o.precio; return; }
    o.mon = DASH_OKX_SIN_MONEDA;
    o.supuesto = true;
    o.precio = ultimo[o.tipo] || 0;
  });
  // Si no había un precio OKX anterior: el último precio conocido en esa moneda, mismo tipo y cripto, de cualquier exchange.
  var otro = {};
  lista.filter(function (o) { return o.mon === DASH_OKX_SIN_MONEDA && !o.supuesto && o.precio; })
    .sort(function (a, b) { return a.f - b.f; })
    .forEach(function (o) { otro[o.tipo + o.cripto] = o.precio; });
  okx.forEach(function (o) {
    if (!o.supuesto) return;
    if (!o.precio) o.precio = otro[o.tipo + o.cripto] || 0;
    o.monto = Math.round(o.cant * o.precio * 100) / 100;
  });
}

function dashLeerMovsUY_() {
  if (!CONFIG.REGISTRO_BEXO_ID) return [];
  var sh = SpreadsheetApp.openById(CONFIG.REGISTRO_BEXO_ID).getSheetByName(HOJA_MOVS_UY);
  if (!sh || sh.getLastRow() < 2) return [];
  return sh.getRange(2, 1, sh.getLastRow() - 1, 4).getValues().map(function (r) {
    return { f: dashFecha_(r[0]), monto: dashNum_(r[1]), nombre: String(r[2] || ''), cta: String(r[3] || '') };
  }).filter(function (m) { return m.f && m.monto > 0; });
}

// ---------- cálculo ----------

function dashP_(lista) {   // precio promedio ponderado
  var q = 0, m = 0;
  lista.forEach(function (o) { q += o.cant; m += o.monto; });
  return q ? m / q : 0;
}
function dashR_(x, d) { var k = Math.pow(10, d || 2); return Math.round(x * k) / k; }
function dashHace_(min) { return min === null ? 'esta semana' : 'hace ' + (min < 90 ? min + ' min' : Math.round(min / 60) + ' h'); }
function dashTxt_(x) { return (Math.round(x * 100) / 100).toFixed(2).replace('.', ','); }   // 41,90 para los textos

/**
 * vivos: precios en vivo de TUS anuncios de Binance, que manda el servidor del VPS (Apps Script no llega a Binance).
 * { "<n° de anuncio>": {tipo:'Compra'|'Venta', cripto, precio, puesto, total, mejor, visible} }
 */
function dashboardP2P_(vivos) {
  vivos = vivos || {};
  var ahora = new Date();
  var zona = Session.getScriptTimeZone();
  var ords = dashLeerOrdenes_();
  var ok = ords.filter(function (o) { return o.estado === 'Completada' && o.cant > 0; });
  var esUYU = function (o) { return o.mon === 'UYU'; };

  // Ciclo UYU
  var desde = dashFecha_(CONFIG.DASH_CICLO_DESDE) || new Date(ahora.getTime() - 14 * 864e5);
  var enCiclo = ok.filter(function (o) { return esUYU(o) && o.f >= desde; });
  var ventas = enCiclo.filter(function (o) { return o.tipo === 'Venta'; });
  var compras = enCiclo.filter(function (o) { return o.tipo === 'Compra'; });
  var vendido = ventas.reduce(function (s, o) { return s + o.cant; }, 0);
  var recomprado = compras.reduce(function (s, o) { return s + o.cant; }, 0);
  var pVenta = dashP_(ventas), pCompra = dashP_(compras);
  var pendiente = vendido - recomprado;
  // Órdenes del ciclo sin moneda (OKX sin historial completo): no sé si son UYU, así que el pendiente es un rango.
  var dudosas = ok.filter(function (o) { return !o.mon && o.f >= desde; });
  var dudaVenta = dudosas.filter(function (o) { return o.tipo === 'Venta'; }).reduce(function (s, o) { return s + o.cant; }, 0);
  var dudaCompra = dudosas.filter(function (o) { return o.tipo === 'Compra'; }).reduce(function (s, o) { return s + o.cant; }, 0);
  var ganUYU = pVenta && pCompra ? Math.min(recomprado, vendido) * (pVenta - pCompra) : 0;
  var dias = Math.max(1, Math.round((ahora - desde) / 864e5));
  // Días trabajados: días del ciclo con al menos una orden UYU completada (los días parados no bajan el promedio).
  var diasTrab = {};
  enCiclo.forEach(function (o) { diasTrab[Utilities.formatDate(o.f, zona, 'yyyyMMdd')] = 1; });
  var nTrab = Object.keys(diasTrab).length;

  // Precios de hoy: venta = la última venta UYU; compra = promedio del ciclo (o la última si no hay ciclo)
  var uyuOk = ok.filter(esUYU).sort(function (a, b) { return b.f - a.f; });
  var ultVenta = uyuOk.filter(function (o) { return o.tipo === 'Venta'; })[0];
  var ultCompra = uyuOk.filter(function (o) { return o.tipo === 'Compra'; })[0];
  var ventaHoy = ultVenta ? ultVenta.precio : pVenta;
  var compraHoy = pCompra || (ultCompra ? ultCompra.precio : 0);
  var techo = ventaHoy / (1 + DASH_MARGEN_MIN);
  var piso = compraHoy * (1 + DASH_MARGEN_MIN);

  // Anuncios (deducidos de las órdenes UYU de los últimos 7 días)
  var hace7 = new Date(ahora.getTime() - 7 * 864e5);
  // Un renglón por exchange × tipo × cripto. En Binance no se agrupa por n° de anuncio: Binance a veces cierra el
  // anuncio (sin límite) y crea otro con otro número. Solo cuentan las órdenes de TUS anuncios (Rol = Anunciante).
  var claveAnuncio = function (o) { return o.ex + '|' + o.tipo + '|' + o.cripto; };
  var esMio = function (o) { return o.ex !== 'Binance' || o.rol === 'Anunciante'; };
  var porAnuncio = {};
  ords.filter(function (o) { return esUYU(o) && esMio(o) && o.f >= hace7 && o.estado !== 'Cancelada'; })
    .sort(function (a, b) { return b.f - a.f; })
    .forEach(function (o) {
      var k = claveAnuncio(o);
      if (!porAnuncio[k]) porAnuncio[k] = { ex: o.ex, tipo: o.tipo, cripto: o.cripto, precio: o.precio, ultima: o.f, hoy: 0 };
      if (Utilities.formatDate(o.f, zona, 'yyyyMMdd') === Utilities.formatDate(ahora, zona, 'yyyyMMdd')) porAnuncio[k].hoy++;
    });
  // N° de anuncios de Binance de los últimos 30 días: el VPS los usa solo para aprender cuál es tu usuario.
  var hace30 = new Date(ahora.getTime() - 30 * 864e5);
  var misAnunciosBinance = {};
  ords.filter(function (o) { return o.ex === 'Binance' && o.rol === 'Anunciante' && o.ad && esUYU(o) && o.f >= hace30; })
    .forEach(function (o) { if (!misAnunciosBinance[o.ad]) misAnunciosBinance[o.ad] = { tipo: o.tipo, cripto: o.cripto }; });
  // Precio en vivo (clave "Venta|USDT"): pisa el de la última orden. Un anuncio visible sin órdenes esta semana
  // también aparece. Un grupo "no visible" solo se muestra si tuvo órdenes esta semana.
  Object.keys(vivos).forEach(function (g) {
    var v = vivos[g] || {};
    var k = 'Binance|' + g;
    if (!porAnuncio[k]) {
      if (v.visible === false) return;
      porAnuncio[k] = { ex: 'Binance', tipo: v.tipo, cripto: v.cripto, precio: v.precio, ultima: null, hoy: 0 };
    }
    var a = porAnuncio[k];
    a.vivo = true;
    a.visible = v.visible !== false;
    a.revisados = v.revisados || null;
    if (a.visible) {
      a.precio = +v.precio || a.precio; a.puesto = v.puesto; a.total = v.total; a.completo = v.completo !== false;
      a.mejor = v.mejor; a.metodos = v.metodos || []; a.cuantos = v.cuantos || 1;
    }
  });
  // "258" si el pendiente es seguro; "258 a 330" si hay órdenes sin moneda que podrían ser UYU.
  var pMin = Math.round(pendiente - dudaCompra), pMax = Math.round(pendiente + dudaVenta);
  var pendTxt = pMin === pMax ? String(pMin) : pMin + ' a ' + pMax;
  var hora = +Utilities.formatDate(ahora, zona, 'H');
  var horaActiva = hora >= DASH_HORA_DESDE && hora <= DASH_HORA_HASTA;
  var anuncios = Object.keys(porAnuncio).map(function (k) {
    var a = porAnuncio[k];
    var min = a.ultima ? Math.round((ahora - a.ultima) / 60000) : null;
    if (a.vivo && !a.visible) {
      // No adivinamos: puede estar pausado, sin saldo, oculto por filtros de Binance, o cerrado.
      return { ex: a.ex, tipo: a.tipo, cripto: a.cripto, precio: dashR_(a.precio), accion: 'No sé', nuevo: null,
               porque: 'No está en el listado público de Binance' + (a.revisados ? ' (revisé los ' + a.revisados + ')' : '') +
                       ': pausado, sin saldo o fuera de línea. El precio es el de la última orden.',
               minUltima: min, hoy: a.hoy, vivo: false, fuente: 'orden' };
    }
    var quieto = horaActiva && (min === null || min >= DASH_SIN_ORDENES_MIN);
    var r = { accion: 'Mantener', nuevo: a.precio, porque: '' };
    if (a.tipo === 'Compra') {
      if (pendiente > DASH_LIMITE_PENDIENTE || quieto) {
        var paso = pendiente > DASH_LIMITE_PENDIENTE ? 0.10 : 0.05;
        var n = Math.min(a.precio + paso, techo);
        if (n > a.precio + 0.004) {
          r = { accion: 'Subir', nuevo: n, porque: pendiente > DASH_LIMITE_PENDIENTE
            ? 'Debés ' + pendTxt + ' USDT (más de ' + DASH_LIMITE_PENDIENTE + '). Techo ' + dashTxt_(techo) + '.'
            : 'Sin órdenes ' + dashHace_(min) + ' en hora de movimiento. Techo ' + dashTxt_(techo) + '.' };
        } else {
          r.porque = 'Ya estás en el techo (' + dashTxt_(techo) + '): subir más no deja margen.';
        }
      } else if (pendiente < DASH_PENDIENTE_BAJO) {
        r = { accion: 'Bajar', nuevo: a.precio - 0.10, porque: 'Ya casi no debés USDT: podés comprar más barato.' };
      } else {
        r.porque = 'Va entrando. Debés ' + pendTxt + ' USDT, dentro de lo normal.';
      }
    } else {
      if (pendiente > DASH_LIMITE_PENDIENTE) {
        r.porque = 'No bajes: debés ' + pendTxt + ' USDT y te llenarías de UYU sin recomprar.';
      } else if (pendiente < DASH_PENDIENTE_BAJO && quieto) {
        var nv = Math.max(a.precio - 0.05, piso);
        if (nv < a.precio - 0.004) r = { accion: 'Bajar', nuevo: nv, porque: 'Sin ventas ' + dashHace_(min) + ' y debés poco. Piso ' + dashTxt_(piso) + '.' };
        else r.porque = 'Ya estás en el piso (' + dashTxt_(piso) + ').';
      } else {
        r.porque = quieto ? 'Quieto, pero primero recomprá lo que debés.' : 'Va vendiendo.';
      }
    }
    return { ex: a.ex, tipo: a.tipo, cripto: a.cripto, precio: dashR_(a.precio), accion: r.accion,
             nuevo: dashR_(r.nuevo), porque: r.porque, minUltima: min, hoy: a.hoy,
             vivo: !!a.vivo, puesto: a.puesto || null, total: a.total || null, completo: a.completo !== false,
             mejor: a.mejor || null, metodos: a.metodos || null, cuantos: a.cuantos || null, fuente: a.visible ? 'vivo' : 'orden' };
  }).sort(function (a, b) { return (a.tipo === b.tipo ? 0 : a.tipo === 'Compra' ? -1 : 1) || a.ex.localeCompare(b.ex); });

  // Rutas
  var ultimas = function (filtro, n) {
    return ok.filter(filtro).sort(function (a, b) { return b.f - a.f; }).slice(0, n || 5);
  };
  var ars = ultimas(function (o) { return o.mon === 'ARS' && o.tipo === 'Compra'; });
  var ves = ultimas(function (o) { return o.mon === 'VES' && o.tipo === 'Venta'; });
  var usdc = ultimas(function (o) { return o.mon === 'UYU' && o.tipo === 'Compra' && o.cripto === 'USDC'; }, 3);
  var arsSemana = ok.filter(function (o) { return o.mon === 'ARS' && o.tipo === 'Compra' && o.f >= hace7; })
    .reduce(function (s, o) { return s + o.monto; }, 0);
  var vesSemana = ok.filter(function (o) { return o.mon === 'VES' && o.tipo === 'Venta' && o.f >= hace7; })
    .reduce(function (s, o) { return s + o.cant; }, 0);

  // Mapa de calor: órdenes completadas de los últimos 28 días, día × hora (8 a 23)
  var hace28 = new Date(ahora.getTime() - 28 * 864e5);
  var calor = [];
  for (var d = 0; d < 7; d++) { calor.push([]); for (var hh = 8; hh <= 23; hh++) calor[d].push(0); }
  ok.filter(function (o) { return o.f >= hace28; }).forEach(function (o) {
    var dia = (+Utilities.formatDate(o.f, zona, 'u')) - 1;   // 1 = lunes
    var h = +Utilities.formatDate(o.f, zona, 'H');
    if (h >= 8) calor[dia][h - 8]++;
  });

  // Cupo de cuentas UYU (mes actual) y conciliación
  var movs = [];
  var errMovs = '';
  try { movs = dashLeerMovsUY_(); } catch (e) { errMovs = String(e.message || e); }
  var mes = Utilities.formatDate(ahora, zona, 'yyyyMM');
  var cupo = DASH_CUENTAS_UY.map(function (c) {
    var usado = movs.filter(function (m) { return m.cta === c && Utilities.formatDate(m.f, zona, 'yyyyMM') === mes; })
      .reduce(function (s, m) { return s + m.monto; }, 0);
    return { cta: c, usado: Math.round(usado), pct: Math.round(usado / DASH_CUPO_CUENTA * 100) };
  });
  var ultMov = movs.reduce(function (mx, m) { return !mx || m.f > mx ? m.f : mx; }, null);

  // Datos faltantes / avisos
  var avisos = [];
  var okxSinMoneda = ords.filter(function (o) { return o.ex === 'OKX' && !o.mon && o.f >= hace7; }).length;
  var okxSupuestas = ords.filter(function (o) { return o.supuesto && o.f >= desde; }).length;
  if (okxSupuestas) avisos.push({ nivel: 'warn', texto: okxSupuestas + ' órdenes OKX del ciclo sin moneda: las cuento como ' + DASH_OKX_SIN_MONEDA +
    ' con el último precio de OKX (supuesto, no comprobado).' });
  if (okxSinMoneda) avisos.push({ nivel: 'warn', texto: okxSinMoneda + ' órdenes OKX de esta semana sin moneda. Corré el historial P2P en el teléfono.' });
  // Hasta cuándo hay órdenes cargadas de cada exchange: lo que pasó después todavía no entra en las cuentas.
  var cargadas = ['Binance', 'OKX', 'Bybit'].map(function (ex) {
    var u = ords.filter(function (o) { return o.ex === ex; }).reduce(function (mx, o) { return !mx || o.f > mx ? o.f : mx; }, null);
    var hs = u ? (ahora - u) / 36e5 : null;
    return { ex: ex, hasta: u ? Utilities.formatDate(u, zona, 'dd/MM HH:mm') : '', horas: hs === null ? null : Math.round(hs) };
  });
  // Cuándo llegó la última subida de cada fuente (no la última orden: si no operaste, la orden es vieja pero la
  // subida es reciente). Binance y Bybit las sube el teléfono cada 4 h; OKX la trae el Apps Script cada 4 h.
  var props = PropertiesService.getScriptProperties();
  var subidas = [['Binance', 'ORDENES_ULTIMA_SUBIDA'], ['Bybit', 'ORDENES_ULTIMA_BYBIT'], ['OKX', 'ORDENES_ULTIMA_OKX'],
                 ['OKX app', 'ORDENES_ULTIMA_OKX_APP']].map(function (x) {
    var ms = +props.getProperty(x[1]) || 0;
    var hs = ms ? (ahora - ms) / 36e5 : null;
    return { fuente: x[0], hace: hs === null ? null : Math.round(hs * 10) / 10,
             cuando: ms ? Utilities.formatDate(new Date(ms), zona, 'dd/MM HH:mm') : '',
             atrasada: x[0] !== 'OKX app' && hs !== null && hs > 5 };   // sin dato todavía = no se marca
  });
  var atrasadas = subidas.filter(function (x) { return x.atrasada; });
  atrasadas.forEach(function (x) {
    avisos.push({ nivel: 'bad', texto: x.fuente + ': ' + (x.hace === null ? 'nunca llegó una subida de órdenes.' :
      'la última subida de órdenes fue hace ' + (x.hace < 48 ? Math.round(x.hace) + ' h' : Math.round(x.hace / 24) + ' días') + ' (' + x.cuando +
      '). Lo que hiciste después no está en ningún número.') });
  });
  cargadas.forEach(function (c) {
    if (c.horas === null || c.horas >= 24) avisos.push({ nivel: 'warn', texto: c.ex + ': ' + (c.horas === null ? 'sin órdenes cargadas.' : 'la última orden cargada es de hace ' + c.horas + ' h.') });
  });

  // Balance de toda la rueda desde el inicio del ciclo: USDT/USDC que entraron y salieron por cada moneda.
  var rueda = {};
  ok.filter(function (o) { return o.f >= desde && o.mon; }).forEach(function (o) {
    var m = rueda[o.mon] || (rueda[o.mon] = { mon: o.mon, entro: 0, salio: 0, fiatPagado: 0, fiatCobrado: 0, n: 0 });
    if (o.tipo === 'Compra') { m.entro += o.cant; m.fiatPagado += o.monto; } else { m.salio += o.cant; m.fiatCobrado += o.monto; }
    m.n++;
  });
  var ruedaLista = Object.keys(rueda).map(function (k) {
    var m = rueda[k];
    return { mon: m.mon, entro: dashR_(m.entro), salio: dashR_(m.salio), neto: dashR_(m.entro - m.salio), ordenes: m.n,
             pCompra: m.entro ? dashR_(m.fiatPagado / m.entro, 2) : null, pVenta: m.salio ? dashR_(m.fiatCobrado / m.salio, 2) : null };
  }).sort(function (a, b) { return (b.entro + b.salio) - (a.entro + a.salio); });
  var sinMoneda = ok.filter(function (o) { return o.f >= desde && !o.mon; });
  // Cómo va cada vuelta: Uruguay = vendés USDT por UYU y recomprás con UYU. Remesas = comprás USDT con los ARS
  // que te mandan y los vendés por Bs o COP. Las demás monedas van cada una por su lado.
  var r0 = function (m) { return rueda[m] || { entro: 0, salio: 0, n: 0 }; };
  var vuelta = function (nombre, cuenta, vendio, repuso, n, como) {
    return { nombre: nombre, cuenta: cuenta, vendido: dashR_(vendio), repuesto: dashR_(repuso), falta: dashR_(vendio - repuso), ordenes: n, como: como };
  };
  var vueltas = [];
  var uy = r0('UYU'), ve = r0('VES'), ar = r0('ARS');
  if (uy.n) vueltas.push(vuelta('Uruguay', 'UYU', uy.salio, uy.entro, uy.n, 'recompraste|con UYU'));
  // Remesas: los USDT comprados con ARS se venden por Bs y por pesos colombianos (en el ciclo 03/11 dio justo:
  // 3.214,81 comprados con ARS = 2.654,81 VES + 560,40 COP).
  var co = r0('COP');
  if (ve.n || ar.n || co.n) vueltas.push(vuelta('Remesas', 'ARS → VES y COP', ve.salio + co.salio + ar.salio, ar.entro + ve.entro + co.entro,
                                                ve.n + ar.n + co.n, 'repusiste|con ARS'));
  Object.keys(rueda).filter(function (m) { return ['UYU', 'VES', 'ARS', 'COP'].indexOf(m) < 0; }).forEach(function (m) {
    var x = rueda[m];
    vueltas.push(vuelta(m, m, x.salio, x.entro, x.n, 'recompraste|con ' + m));
  });
  if (errMovs) avisos.push({ nivel: 'bad', texto: 'No pude leer Movs UY: ' + errMovs });
  else if (ultMov) {
    var dm = Math.round((ahora - ultMov) / 864e5);
    if (dm >= 3) avisos.push({ nivel: 'warn', texto: 'Movs UY tiene depósitos hasta hace ' + dm + ' días: cupos y conciliación pueden estar atrasados.' });
  }
  if (!CONFIG.DASH_CICLO_DESDE) avisos.push({ nivel: 'warn', texto: 'Sin fecha de inicio de ciclo (DASH_CICLO_DESDE): uso los últimos 14 días.' });
  if (!avisos.length) avisos.push({ nivel: 'ok', texto: 'Todo cargado al día.' });

  return {
    generado: ahora.toISOString(),
    generadoTexto: Utilities.formatDate(ahora, zona, 'dd/MM HH:mm'),
    ciclo: {
      desde: Utilities.formatDate(desde, zona, 'dd/MM'), dias: dias,
      vendido: dashR_(vendido), recomprado: dashR_(recomprado), pendiente: dashR_(pendiente),
      pendienteMin: dashR_(pendiente - dudaCompra), pendienteMax: dashR_(pendiente + dudaVenta),
      dudosas: dudosas.length, dudaVenta: dashR_(dudaVenta), dudaCompra: dashR_(dudaCompra),
      limitePendiente: DASH_LIMITE_PENDIENTE,
      pVenta: dashR_(pVenta), pCompra: dashR_(pCompra),
      gananciaUYU: Math.round(ganUYU), gananciaUSD: pVenta ? dashR_(ganUYU / pVenta, 0) : 0,
      porDiaUSD: pVenta ? dashR_(ganUYU / pVenta / dias, 1) : 0,
      diasTrabajados: nTrab,
      porDiaTrabajadoUSD: pVenta && nTrab ? dashR_(ganUYU / pVenta / nTrab, 1) : 0,
      // Por cada 100 USDT vendidos y recomprados (vuelta cerrada): no depende de cuántos días trabajaste.
      por100USD: pVenta && pCompra ? dashR_(100 * (pVenta - pCompra) / pVenta, 2) : 0
    },
    punta: {
      compra: dashR_(compraHoy), venta: dashR_(ventaHoy), techo: dashR_(techo), piso: dashR_(piso),
      margen: compraHoy ? dashR_((ventaHoy / compraHoy - 1) * 100, 1) : 0, minimo: DASH_MARGEN_MIN * 100
    },
    anuncios: anuncios,
    misAnunciosBinance: misAnunciosBinance,
    rutas: {
      uyu: { margen: pCompra ? dashR_((pVenta / pCompra - 1) * 100, 1) : 0, gananciaUSD: pVenta ? dashR_(ganUYU / pVenta, 0) : 0 },
      ars: { precio: dashR_(dashP_(ars), 1), semanaARS: Math.round(arsSemana) },
      ves: { precio: dashR_(dashP_(ves), 1), semanaUSDT: dashR_(vesSemana, 0) },
      usdc: { precio: dashR_(dashP_(usdc)), margen: usdc.length && ventaHoy ? dashR_((ventaHoy / dashP_(usdc) - 1) * 100, 1) : 0 }
    },
    calor: calor,
    cupo: { limite: DASH_CUPO_CUENTA, cuentas: cupo },
    cargadas: cargadas,
    subidas: subidas,
    vueltas: vueltas,
    rueda: { lista: ruedaLista, neto: dashR_(ruedaLista.reduce(function (s, m) { return s + m.neto; }, 0)),
             sinMoneda: sinMoneda.length, sinMonedaUSDT: dashR_(sinMoneda.reduce(function (s, o) { return s + (o.tipo === 'Compra' ? o.cant : -o.cant); }, 0)) },
    // Las últimas 10 órdenes tal como las leyó el tablero, para comprobarlas de memoria.
    ultimasOrdenes: ords.slice().sort(function (a, b) { return b.f - a.f; }).slice(0, 10).map(function (o) {
      return { fecha: Utilities.formatDate(o.f, zona, 'dd/MM HH:mm'), ex: o.ex, tipo: o.tipo, cripto: o.cripto, cant: dashR_(o.cant),
               mon: o.mon, monto: dashR_(o.monto), precio: dashR_(o.precio, 3), estado: o.estado, supuesto: !!o.supuesto };
    }),
    movsHasta: ultMov ? Utilities.formatDate(ultMov, zona, 'dd/MM') : '',
    avisos: avisos
  };
}
