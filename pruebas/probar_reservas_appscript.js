// Prueba sin Google las reservas del Apps Script: node pruebas/probar_reservas_appscript.js apps-script/9_P2P.gs
// Carga 9_P2P.gs con stubs de Google y prueba elegirAnuncioVes_ + reservas (filtro de frases real).
const fs = require('fs'), vm = require('vm');
const props = {};
const ctx = {
  CONFIG: { RELAY_URL: 'x' }, Logger: { log: () => {} }, console,
  PropertiesService: { getScriptProperties: () => ({ getProperty: k => props[k] || null,
    setProperty: (k, v) => { props[k] = v; }, deleteProperty: k => { delete props[k]; } }) },
  SpreadsheetApp: {}, UrlFetchApp: {}, logError_: () => {},
};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), ctx);
const desc = { A2: 'NO acepto pagos de terceros', A3: 'Hola, atiendo rápido. Pago móvil.', A4: 'Recibo de terceros sin problema',
               A5: 'Solo titulares', A6: 'todo bien' };
let leidas = [];
ctx.leerDescripcion_ = adNo => { leidas.push(adNo); return desc[adNo] || ''; };
ctx.registrarFiltro_ = () => {};
const ad = (n, apodo, precio) => ({ adNo: n, apodo, precio, min: 1000, max: 100000, pagos: ['PagoMovil'] });
let lista;
ctx.leerAnunciosP2P_ = () => lista.map(a => Object.assign({}, a));
const frases = ctx.leerFrasesAlerta_ ? { bloquear: [], permitir: [] } : null;
function caso(nombre, ads, traders, esperado, esperadoAlt) {
  lista = ads; leidas = []; delete props.P2P_MEMORIA;
  const r = ctx.elegirAnuncioVes_(5000, traders, { bloquear: [], permitir: [] }, [], null, ['PagoMovil']);
  const alt = (r.alternativas || []).map(x => x.apodo);
  const ok = (r.anuncio && r.anuncio.apodo) === esperado && JSON.stringify(alt) === JSON.stringify(esperadoAlt);
  console.log((ok ? 'BIEN ' : 'MAL  ') + nombre + ' → ' + (r.anuncio && r.anuncio.apodo) + ' + reservas ' +
              JSON.stringify(alt) + ' · link "' + ctx.linkAlternativas_(r) + '" · ' + ctx.lineaAlternativas_(r));
  return ok;
}
let bien = 0, n = 0;
// 1: el primero pasa; reservas: salta A2 (terceros), toma A3 y A4
n++; bien += caso('normal', [ad('A1', 'uno', 1070), ad('A2', 'dos', 1069), ad('A3', 'tres', 1068), ad('A4', 'cuatro', 1060)], {},
  'uno', ['tres', 'cuatro']);
// 2: el mismo trader con 2 anuncios no cuenta como reserva
n++; bien += caso('mismo trader', [ad('A1', 'uno', 1070), ad('A9', 'uno', 1069.5), ad('A3', 'tres', 1068), ad('A6', 'seis', 1067)], {},
  'uno', ['tres', 'seis']);
// 3: trader conocido elegido; reservas sin leer la del conocido
n++; bien += caso('conocido', [ad('A1', 'uno', 1070), ad('A3', 'tres', 1068), ad('A7', 'amigo', 1069)], { amigo: 5 },
  'amigo', ['uno', 'tres']);
// 4: solo uno pasa: sin reservas
n++; bien += caso('sin reservas', [ad('A3', 'tres', 1070), ad('A2', 'dos', 1069), ad('A5', 'cinco', 1068)], {},
  'tres', []);
console.log(bien + ' de ' + n + ' casos bien');
process.exit(bien === n ? 0 : 1);
