// Pruebas del intake (apps-script/22_Intake.gs).
//   node pruebas/probar_intake_appscript.js                      casos públicos (pruebas/intake_casos.json)
//   node pruebas/probar_intake_appscript.js chats_waha.json.gz   + repetición contra tus chats reales:
//        cada tanda del cliente se pasa por respuestaIntake_ y se compara con lo que contestaste vos.
// Los chats reales tienen datos de clientes: nunca van al repo (el archivo se pasa por argumento).
const fs = require('fs'), vm = require('vm'), path = require('path'), zlib = require('zlib');
const AS = path.join(__dirname, '..', 'apps-script');

function cargar() {
  const ctx = {
    console, CacheService: { getScriptCache: () => ({ get: () => null, put: () => {} }) },
    UrlFetchApp: { fetch: () => { throw new Error('sin red en pruebas'); } },
    CONFIG: {}
  };
  vm.createContext(ctx);
  const leer = f => fs.readFileSync(path.join(AS, f), 'utf8');
  // MAPA_CUENTAS (alias) y las listas del dashboard, sin el resto de esos archivos
  const lc = leer('4_LeerComprobantes.gs');
  vm.runInContext(lc.match(/var MAPA_CUENTAS = \{[\s\S]*?\n\};/)[0], ctx);
  const ds = leer('5_Dashboard.gs');
  vm.runInContext(ds.match(/var CUENTAS_DASH = .*/)[0], ctx);
  vm.runInContext(ds.match(/var CUENTAS_PAUSADAS[\s\S]*?function cuentaRecomendada_[^\n]*\n/)[0], ctx);
  vm.runInContext(leer('22_Intake.gs'), ctx);
  return ctx;
}
const G = cargar();
const iguales = (a, b) => a.length === b.length && a.every((x, i) => x === b[i]);
let fallas = 0;

// ---------- 1. casos públicos ----------
const casos = JSON.parse(fs.readFileSync(path.join(__dirname, 'intake_casos.json'), 'utf8'));
const TASAS = { neta: 0.52, usd: 772, eur: 900 };
const CUENTAS = ['APJ', 'NJ', 'APB', 'RBJ'];
let ok = 0;
for (const c of casos) {
  const r = G.respuestaIntake_(c.texto, !!c.media, { tasas: TASAS, hora: c.hora ?? 15, cuentas: CUENTAS, yaSaludo: !!c.yaSaludo, enProceso: !!c.enProceso, fotoPendiente: !!c.fotoPendiente });
  const errores = [];
  for (const k of c.intenciones || []) if (!r.intenciones.includes(k)) errores.push('falta intención ' + k);
  for (const k of c.no || []) if (r.intenciones.includes(k)) errores.push('sobra intención ' + k);
  if (c.tipos && !iguales([...r.tipos].sort(), [...c.tipos].sort())) errores.push(`respuesta ${JSON.stringify(r.tipos)} (esperaba ${JSON.stringify(c.tipos)})`);
  if (c.manual !== undefined && r.manual !== c.manual) errores.push('manual=' + r.manual);
  for (const m of c.mensajes || []) if (!r.mensajes.includes(m)) errores.push(`falta "${m}" en ${JSON.stringify(r.mensajes)}`);
  if (errores.length) { fallas++; console.log('✗', c.nombre + ':', errores.join('; ')); } else ok++;
}
console.log(`Casos públicos: ${ok}/${casos.length}`);

// unidades sueltas del cálculo y los alias
const unidad = [
  ['30.000 pesos', { de: 'ARS', monto: 30000 }], ['cuanto llega con 100 mil', { de: 'ARS', monto: 100000 }],
  ['tengo q mandar 60', { de: 'ARS', monto: 60000 }], ['para que lleguen 2.300,00 Bolivares', { de: 'VES', monto: 2300 }],
  ['30 dólares', { de: 'USD', monto: 30, base: 'BCV' }], ['310$ a base de euro', { de: 'EUR', monto: 310, base: 'EURO' }],
  ['$31.000', { de: 'ARS', monto: 31000 }], ['0102 04241234567 12345678', null], ['60 luca', { de: 'ARS', monto: 60000 }]
];
for (const [t, esp] of unidad) {
  const r = G.pedidoDeCalculo_(t);
  if (JSON.stringify(r) !== JSON.stringify(esp)) { fallas++; console.log('✗ pedidoDeCalculo_', t, JSON.stringify(r), '≠', JSON.stringify(esp)); }
}
const a1 = G.aliasParaCobrar_(100000, CUENTAS), a2 = G.aliasParaCobrar_(300000, CUENTAS);
if (a1.alias.length !== 1 || a1.mitad) { fallas++; console.log('✗ 100.000 debería ser un alias', JSON.stringify(a1)); }
if (a2.alias.length !== 2 || !a2.mitad || a2.alias.some(x => /\.astro$/.test(x) === false && /\.naranja$/.test(x) === false)) { fallas++; console.log('✗ 300.000 debería ser mitad y mitad en APJ y NJ', JSON.stringify(a2)); }
if (G.aliasParaCobrar_(100000, ['APB', 'NJ']).alias[0] !== 'John.ray.naranja') { fallas++; console.log('✗ APB pausada no se ofrece'); }
console.log(`Unidades: ${unidad.length + 3} (fallas totales hasta acá: ${fallas})`);

// ---------- 2. repetición contra tus chats ----------
const archivo = process.argv[2];
if (archivo) {
  const d = JSON.parse(zlib.gunzipSync(fs.readFileSync(archivo)));
  const sin = t => (t || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').trim();
  const tipoJohn = m => {
    const t = sin(m.texto);
    if (!t) return m.media ? 'foto' : '';
    if (/te aviso apenas tenga/.test(t)) return 'en_proceso';
    if (/^0[.,]\d{2,3}$/.test(t)) return 'tasa';
    if (/^[\d.,]+ ?(mil )?(pesos|bs|bolivares|dolares|\$)/.test(t)) return 'calculo';
    if (/^john\.|alias/.test(t)) return 'alias';
    if (/disponibilidad|^si dale/.test(t)) return 'disponible';
    if (/^(hola|buen ?dia|buen[oa]s|bien dia|que tal)/.test(t)) return 'saludo';
    return 'otro';
  };
  // tasa del día: la que mandaste vos ese día (o la última antes)
  const tasaDia = {};
  for (const ch of d.chats) for (const m of ch.mensajes)
    if (m.yo && /^0[.,]\d{2,3}$/.test((m.texto || '').trim())) tasaDia[new Date((m.ts - 3 * 3600) * 1000).toISOString().slice(0, 10)] = Number(m.texto.trim().replace(',', '.'));
  const dias = Object.keys(tasaDia).sort();
  const tasaPara = ts => { const k = new Date((ts - 3 * 3600) * 1000).toISOString().slice(0, 10); let v = 0; for (const x of dias) { if (x <= k) v = tasaDia[x]; } return v || tasaDia[dias[0]]; };

  const TIPOS = ['saludo', 'disponible', 'tasa', 'calculo', 'alias', 'en_proceso'];
  const est = Object.fromEntries(TIPOS.map(t => [t, { ok: 0, falto: 0, sobro: 0 }]));
  let tandas = 0, manual = 0, sinUsd = 0, calcOk = 0, calcMal = 0; const ejemplos = { falto: {}, sobro: {}, calc: [] };
  for (const ch of d.chats) {
    const ms = ch.mensajes; let ultSaludo = -1e12, enProceso = 0, foto = 0;
    for (let i = 0; i < ms.length;) {
      if (ms[i].yo) { if (tipoJohn(ms[i]) === 'saludo') ultSaludo = ms[i].ts; i++; continue; }
      let j = i; const partes = []; let media = false;
      while (j < ms.length && !ms[j].yo && (j === i || ms[j].ts - ms[j - 1].ts < 3 * 3600)) { if (ms[j].texto) partes.push(ms[j].texto); media = media || ms[j].media; j++; }
      if (j < ms.length && !ms[j].yo) { i = j; continue; }               // la tanda quedó sin respuesta tuya
      let k = j; const tuyos = new Set(); const textos = [];
      while (k < ms.length && ms[k].yo && ms[k].ts - ms[j - 1].ts < 6 * 3600) { tuyos.add(tipoJohn(ms[k])); textos.push(ms[k].texto); k++; }
      if (k === j) { i = j; continue; }                                  // sin respuesta tuya
      const texto = partes.join('\n'); tandas++;
      const hora = new Date((ms[i].ts - 3 * 3600) * 1000).getUTCHours();
      const ctx = { tasas: { neta: tasaPara(ms[i].ts) }, hora, cuentas: ['APJ', 'NJ'], yaSaludo: ms[i].ts - ultSaludo < 6 * 3600,
        enProceso: ms[i].ts - enProceso < 12 * 3600, fotoPendiente: ms[i].ts - foto < 3 * 3600 };
      const r = G.respuestaIntake_(texto, media, ctx);
      if (media && !tuyos.has('en_proceso')) foto = ms[i].ts;
      if (tuyos.has('en_proceso')) { enProceso = ms[k - 1].ts; foto = 0; }
      if (textos.some(x => /^listo/i.test((x || '').trim()))) enProceso = 0;
      if (r.motivo === 'sin tasa BCV/euro') sinUsd++;
      if (r.manual) manual++;
      for (const t of TIPOS) {
        const vos = tuyos.has(t), sis = r.tipos.includes(t);
        if (t === 'calculo' && vos && !sis && r.motivo === 'sin tasa BCV/euro') continue;   // en vivo lo cubre Yadio
        if (vos && sis) est[t].ok++; else if (vos) { est[t].falto++; (ejemplos.falto[t] = ejemplos.falto[t] || []).push(texto); }
        else if (sis) { est[t].sobro++; (ejemplos.sobro[t] = ejemplos.sobro[t] || []).push(texto + '  →  vos: ' + textos.join(' | ')); }
      }
      if (tuyos.has('calculo') && r.tipos.includes('calculo')) {
        const tuyo = textos.find(x => tipoJohn({ texto: x }) === 'calculo'), mio = r.mensajes.find(x => /pesos|bs$/.test(x));
        const n = s => Number((String(s).match(/\d[\d.]*(,\d+)?/) || ['0'])[0].replace(/\./g, '').replace(',', '.'));
        const unidad = s => /^[\d.,\s]+bs/i.test(s) ? 'bs' : 'pesos';
        if (unidad(tuyo) === unidad(mio) && Math.abs(n(tuyo) - n(mio)) / n(tuyo) <= 0.03) calcOk++;
        else { calcMal++; ejemplos.calc.push(texto.replace(/\n/g, ' / ').slice(0, 90) + '  →  vos: ' + tuyo + ' · sistema: ' + mio); }
      }
      if (ms[i].ts && tuyos.has('saludo')) ultSaludo = ms[j].ts;
      i = k;
    }
  }
  console.log(`\nRepetición: ${tandas} tandas del cliente con respuesta tuya; el sistema la deja a mano en ${manual}.`);
  console.log('respuesta     acierta  faltó  sobró   (faltó = vos lo hiciste y el sistema no)');
  for (const t of TIPOS) { const e = est[t]; console.log(`${t.padEnd(12)} ${String(e.ok).padStart(7)} ${String(e.falto).padStart(6)} ${String(e.sobro).padStart(6)}`); }
  console.log(`Cálculos en dólares/euros sin tasa BCV en la repetición (no cuentan): ${sinUsd}`);
  console.log(`Cálculos con el mismo número que vos (±3 %): ${calcOk}/${calcOk + calcMal}`);
  if (process.argv.includes('--ver')) {
    const ver = (titulo, l) => { console.log('\n## ' + titulo); l.slice(0, 12).forEach(x => console.log('  ', x.replace(/\n/g, ' / ').slice(0, 170))); };
    for (const t of TIPOS) { if (ejemplos.falto[t]) ver('faltó ' + t, ejemplos.falto[t]); if (ejemplos.sobro[t]) ver('sobró ' + t, ejemplos.sobro[t]); }
    ver('cálculo distinto', ejemplos.calc);
  }
}
process.exit(fallas ? 1 : 0);
