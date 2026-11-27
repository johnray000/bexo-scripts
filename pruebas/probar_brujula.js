#!/usr/bin/env node
/**
 * Pruebas del cálculo de la Brújula P2P (apps-script/20_DashboardP2P.gs) sin Google: corre el .gs en node con
 * Ordenes_P2P de mentira y revisa cada caso que alguna vez falló en producción.
 *   node pruebas/probar_brujula.js
 * Termina con "N de N bien" o dice qué caso falló y qué esperaba.
 */
const fs = require('fs');
const path = require('path');
const RAIZ = path.join(__dirname, '..');
const GS = fs.readFileSync(path.join(RAIZ, 'apps-script/20_DashboardP2P.gs'), 'utf8') + '\n' +
  fs.readFileSync(path.join(RAIZ, 'apps-script/22_RevisionBrujula.gs'), 'utf8');
const HTML = fs.readFileSync(path.join(RAIZ, 'vps/dashboard_index.html'), 'utf8');

const H = ['Exchange', 'Orden', 'Creada', 'Cerrada', 'Tipo', 'Cripto', 'Cantidad', 'Moneda', 'Monto', 'Precio',
  'Método de pago', 'Contraparte', 'Estado', 'Comisión', 'Rol', 'Anuncio', 'Fuente', 'Ref API', 'Ref app'];
// ex, 'dd/MM/yyyy HH:mm', tipo, cripto, cantidad, moneda, monto, precio, estado, rol, anuncio
const F = (ex, f, tipo, cr, cant, mon, monto, precio, estado, rol, ad, fuente, refApi, orden) =>
  [ex, orden || '', f, '', tipo, cr, cant, mon, monto, precio, '', 'x', estado || 'Completada', '', rol || '', ad || '', fuente || 'api', refApi || '', ''];
const RealDate = Date;
const GUARDADO = [];
const AHORA = new RealDate(2026, 10, 17, 22, 21);   // 17/11/2026 22:21

function correr(filas, vivos, props, extra) {
  const pad = (n) => String(n).padStart(2, '0');
  const fmt = (d, f) => {
    if (f === 'H') return String(d.getHours());
    if (f === 'u') return String((d.getDay() + 6) % 7 + 1);
    return f.replace('yyyy', d.getFullYear()).replace('MM', pad(d.getMonth() + 1)).replace('dd', pad(d.getDate()))
      .replace('HH', pad(d.getHours())).replace('mm', pad(d.getMinutes()));
  };
  const ctx = {
    Utilities: { formatDate: (d, z, f) => fmt(d, f) },
    Session: { getScriptTimeZone: () => 'x' },
    SpreadsheetApp: { getActiveSpreadsheet: () => ({
      getSheetByName: (n) => n === 'Revision_Brujula' ? null : ({ getLastRow: () => filas.length + 1,
        getDataRange: () => ({ getValues: () => [H].concat(filas) }) }),
      insertSheet: () => ({ clearContents: () => {}, getRange: () => ({ setValues: (v) => { GUARDADO.push(v); } }) }) }) },
    PropertiesService: { getScriptProperties: () => ({ getProperty: (k) => (props || {})[k] || null }) },
    HOJA_ORDENES_P2P: 'Ordenes_P2P', CONFIG: { DASH_CICLO_DESDE: '03/11/2026' }, logError_: () => {},
    Date: class extends RealDate { constructor(...a) { super(...(a.length ? a : [AHORA.getTime()])); } static now() { return AHORA.getTime(); } }
  };
  const fn = new Function(...Object.keys(ctx), GS + (extra || '') + '\nreturn dashboardP2P_;');
  return fn(...Object.values(ctx))(vivos || {});
}

const casos = [];
const caso = (nombre, f) => casos.push([nombre, f]);
const igual = (a, b, que) => { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(que + ': esperaba ' + JSON.stringify(b) + ' y dio ' + JSON.stringify(a)); };
const fila = (r, ex, tipo, cr) => r.anuncios.filter((a) => a.ex === ex && a.tipo === tipo && (!cr || a.cripto === cr));

// Órdenes base: venta Binance con anuncio viejo (…6192) y nuevo (…7728), compra Binance, Bybit, OKX.
const base = [
  F('Binance', '17/11/2026 21:08', 'Venta', 'USDT', 68.19, 'UYU', 3000, 43.99, '', 'Anunciante', '7728'),
  F('Binance', '17/11/2026 18:47', 'Venta', 'USDT', 57.47, 'UYU', 2500, 43.5, '', 'Anunciante', '7728'),
  F('Binance', '16/11/2026 11:02', 'Venta', 'USDT', 55.43, 'UYU', 2411.39, 43.5, '', 'Anunciante', '6192'),
  F('Binance', '16/11/2026 16:00', 'Compra', 'USDT', 19.81, 'UYU', 818.22, 41.3, '', 'Anunciante', '9852'),
  F('Bybit', '17/11/2026 19:47', 'Compra', 'USDT', 9.73, 'UYU', 400, 41.1),
  F('Bybit', '16/11/2026 23:58', 'Venta', 'USDT', 11.37, 'UYU', 500, 43.99),
  F('OKX', '16/11/2026 12:10', 'Compra', 'USDT', 41.92, 'UYU', 1718.72, 41),
];

caso('17/11: el anuncio viejo de Binance no sale como "Revisar" (una fila por tipo)', () => {
  const r = correr(base, { 'Venta|USDT': { tipo: 'Venta', cripto: 'USDT', precio: 44.42, puesto: 43, total: 59, completo: true, mejor: 43.1, visible: true } });
  const v = fila(r, 'Binance', 'Venta');
  igual(v.length, 1, 'filas de venta Binance');
  igual([v[0].precio, v[0].fuente, v[0].accion !== 'Revisar'], [44.42, 'vivo', true], 'venta Binance');
});

caso('Binance no lo encuentra: dice "No sé", sin precio nuevo, con el de la última orden', () => {
  const r = correr(base, { 'Venta|USDT': { tipo: 'Venta', cripto: 'USDT', visible: false, revisados: 65 } });
  const v = fila(r, 'Binance', 'Venta')[0];
  igual([v.accion, v.nuevo, v.fuente, v.precio], ['No sé', null, 'orden', 43.99], 'venta Binance');
});

caso('Sin datos en vivo (VPS sin Binance): precio de la última orden, marcado como tal', () => {
  const r = correr(base, {});
  const v = fila(r, 'Binance', 'Venta')[0];
  igual([v.fuente, v.precio, v.vivo], ['orden', 43.99, false], 'venta Binance');
});

caso('Un grupo "no visible" sin órdenes esta semana no aparece (venta USDC)', () => {
  const r = correr(base, { 'Venta|USDC': { tipo: 'Venta', cripto: 'USDC', visible: false, revisados: 10 } });
  igual(fila(r, 'Binance', 'Venta', 'USDC').length, 0, 'filas venta USDC');
});

caso('Anuncio nuevo visible sin órdenes esta semana sí aparece', () => {
  const r = correr(base, { 'Compra|USDC': { tipo: 'Compra', cripto: 'USDC', precio: 40.4, puesto: 1, total: 4, completo: true, visible: true } });
  igual(fila(r, 'Binance', 'Compra', 'USDC').map((a) => a.precio), [40.4], 'compra USDC');
});

caso('Órdenes OKX sin moneda: lo que debés es un rango, no un número inventado', () => {
  const filas = base.concat([F('OKX', '17/11/2026 14:38', 'Venta', 'USDT', 22.73, '', '', ''), F('OKX', '16/11/2026 16:07', 'Compra', 'USDT', 21, '', '', '')]);
  const c = correr(filas, {}).ciclo;
  const r2 = (x) => Math.round(x * 100) / 100;
  igual([c.dudosas, r2(c.pendienteMax - c.pendiente), r2(c.pendiente - c.pendienteMin)], [2, 22.73, 21], 'rango');
});

caso('Sin órdenes sin moneda: un solo número', () => {
  const c = correr(base, {}).ciclo;
  igual([c.dudosas, c.pendienteMin === c.pendienteMax], [0, true], 'pendiente');
});

caso('Subida de Binance de hace más de 5 h: aviso rojo; sin dato todavía: no se marca', () => {
  const hace = (h) => String(AHORA.getTime() - h * 36e5);
  const r = correr(base, {}, { ORDENES_ULTIMA_SUBIDA: hace(26), ORDENES_ULTIMA_OKX: hace(1) });
  const s = {}; r.subidas.forEach((x) => { s[x.fuente] = x.atrasada; });
  igual([s.Binance, s.OKX, s.Bybit], [true, false, false], 'atrasadas');
  igual(r.avisos.some((a) => a.nivel === 'bad' && /Binance: la última subida/.test(a.texto)), true, 'aviso rojo');
});

caso('Días trabajados: solo cuentan los días con órdenes UYU completadas', () => {
  const c = correr(base, {}).ciclo;
  igual(c.diasTrabajados, 2, 'días trabajados (16 y 17/11)');
  igual(c.porDiaTrabajadoUSD > c.porDiaUSD, true, 'el promedio por día trabajado es mayor');
});

caso('Remesas: VES y COP se comparan contra lo comprado con ARS', () => {
  const filas = base.concat([
    F('Binance', '13/11/2026 19:54', 'Compra', 'USDT', 100, 'ARS', 166600, 1666, '', 'Tomador'),
    F('Binance', '14/11/2026 18:24', 'Venta', 'USDT', 80, 'VES', 85000, 1062, '', 'Tomador'),
    F('Binance', '17/11/2026 11:57', 'Venta', 'USDT', 20, 'COP', 64800, 3240, '', 'Tomador')]);
  const v = correr(filas, {}).vueltas.filter((x) => x.nombre === 'Remesas')[0];
  igual([v.vendido, v.repuesto, v.falta], [100, 100, 0], 'vuelta remesas');
});

caso('Últimas órdenes: las 10 más nuevas, de la más nueva a la más vieja', () => {
  const u = correr(base, {}).ultimasOrdenes;
  igual([u.length, u[0].fecha], [base.length, '17/11 21:08'], 'últimas órdenes');
});

caso('Las órdenes canceladas no cuentan en lo que debés', () => {
  const filas = base.concat([F('Binance', '17/11/2026 20:00', 'Venta', 'USDT', 500, 'UYU', 22000, 44, 'Cancelada', 'Anunciante', '7728')]);
  igual(correr(filas, {}).ciclo.pendiente, correr(base, {}).ciclo.pendiente, 'pendiente');
});

caso('Página: se apaga solo lo comprobado (Binance no listado o Bybit pausado; OKX nunca, 25/11 y 27/11)', () => {
  const m = HTML.match(/var apagado = function \(a\) \{ return ([^;]+); \};/);
  igual(m && m[1].trim(), "(a.ex === 'Binance' && a.accion === 'No sé') || a.estado === 'pausado'", 'condición de apagado');
});

const adsBybit = (hace, lista) => ({ BYBIT_ANUNCIOS: JSON.stringify({ cuando: AHORA.getTime() - hace * 36e5, lista }) });

caso('27/11: Bybit dice que la compra está pausada y la venta activa: la compra se apaga, la venta usa el precio del anuncio', () => {
  const r = correr(base, {}, adsBybit(1, [
    { id: '1', tipo: 'Compra', cripto: 'USDT', fiat: 'UYU', precio: 41.2, estado: 'pausado' },
    { id: '2', tipo: 'Venta', cripto: 'USDT', fiat: 'UYU', precio: 44.1, estado: 'activo' }]));
  const c = fila(r, 'Bybit', 'Compra')[0], v = fila(r, 'Bybit', 'Venta')[0];
  igual([c.estado, c.accion, c.nuevo], ['pausado', 'Pausado', null], 'compra Bybit');
  igual([v.estado, v.precio, v.fuente], ['activo', 44.1, 'anuncio'], 'venta Bybit');
});

caso('Bybit: dato de más de 6 h u OKX: no se sabe, no se apaga', () => {
  const r = correr(base, {}, adsBybit(7, [{ id: '1', tipo: 'Compra', cripto: 'USDT', fiat: 'UYU', precio: 41.2, estado: 'pausado' }]));
  igual([fila(r, 'Bybit', 'Compra')[0].estado, fila(r, 'OKX', 'Compra')[0].estado], [null, null], 'estados');
});

caso('Bybit: anuncio activo sin órdenes esta semana también aparece', () => {
  const r = correr(base, {}, adsBybit(1, [{ id: '3', tipo: 'Compra', cripto: 'USDC', fiat: 'UYU', precio: 40.5, estado: 'activo' }]));
  const u = fila(r, 'Bybit', 'Compra', 'USDC')[0];
  igual(u && [u.estado, u.precio], ['activo', 40.5], 'compra USDC Bybit');
  igual(fila(r, 'Bybit', 'Compra', 'USDT')[0].estado, 'pausado', 'compra USDT sin anuncio activo');
});

const rev = (r, prueba) => r.revision.filter((x) => x.prueba === prueba)[0] || {};

caso('Revisión: datos sanos dan "ok" y el recálculo de lo que debés coincide', () => {
  const r = correr(base, {});
  igual(['Órdenes repetidas', 'OKX sin unir', 'Monto = cantidad × precio', 'Lo que debés (recálculo)'].map((p) => rev(r, p).estado),
    ['ok', 'ok', 'ok', 'ok'], 'estados');
  igual(GUARDADO.length > 0, true, 'guardó la hoja Revision_Brujula');
});

caso('Revisión: detecta la compra OKX repetida entre API y app (16/11) y dice la fila', () => {
  const filas = base.concat([F('OKX', '16/11/2026 16:07', 'Compra', 'USDT', 41.92, '', '', '', '', '', '', 'api', '1056')]);
  filas[6][16] = 'app';
  const x = rev(correr(filas, {}), 'OKX sin unir');
  igual([x.estado, /filas 9/.test(x.detalle)], ['mal', true], 'OKX sin unir');
});

caso('Revisión: detecta un n° de orden repetido', () => {
  const filas = base.concat([F('Binance', '17/11/2026 21:08', 'Venta', 'USDT', 68.19, 'UYU', 3000, 43.99, '', 'Anunciante', '7728', 'api', '', '229'),
    F('Binance', '17/11/2026 21:08', 'Venta', 'USDT', 68.19, 'UYU', 3000, 43.99, '', 'Anunciante', '7728', 'api', '', '229')]);
  igual(rev(correr(filas, {}), 'Órdenes repetidas').estado, 'mal', 'repetidas');
});

caso('Revisión: monto que no cierra con cantidad × precio', () => {
  const filas = base.concat([F('Bybit', '17/11/2026 10:00', 'Venta', 'USDT', 10, 'UYU', 900, 43.99)]);
  igual(rev(correr(filas, {}), 'Monto = cantidad × precio').estado, 'mal', 'monto');
});

let bien = 0;
casos.forEach(([nombre, f]) => {
  try { f(); bien++; console.log('BIEN', nombre); } catch (e) { console.log('MAL ', nombre, '\n     ', e.message); }
});
console.log(bien + ' de ' + casos.length + ' bien');
process.exit(bien === casos.length ? 0 : 1);
