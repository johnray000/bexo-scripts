// Prueba sin Google la tarjeta del comprobante y el botón "Armar en Binance":
//   node pruebas/probar_tarjeta_ntfy_appscript.js   (desde la raíz del repo)
const fs = require('fs'), vm = require('vm');
function cargar() {
  const props = { NTFY_TOPIC: 'bexo-prueba', RELAY_URL: 'http://vps:8082', RELAY_TOKEN: 't', P2P_CLAVE: 'clave123', WEBAPP_URL: 'https://script.google.com/macros/s/X/exec' };
  const cache = {}, pedidos = [];
  const ctx = { console, Logger: { log: () => {} }, Session: { getScriptTimeZone: () => 'America/Montevideo' },
    PropertiesService: { getScriptProperties: () => ({ getProperties: () => props, getProperty: k => props[k] || null,
                                                       setProperty: (k, v) => { props[k] = v; } }) },
    CacheService: { getScriptCache: () => ({ get: k => cache[k] || null, put: (k, v) => { cache[k] = v; } }) },
    UrlFetchApp: { fetch: (url, o) => { pedidos.push({ url, o }); return { getResponseCode: () => 200, getContentText: () => '' }; } },
    logError_: (a, b) => console.log('logError_', a, b) };
  vm.createContext(ctx);
  for (const f of ['0_Config', '4_LeerComprobantes', '9_P2P', '11_PreOrden', '21_Ntfy'])
    vm.runInContext(fs.readFileSync('apps-script/' + f + '.gs', 'utf8'), ctx);
  return { ctx, pedidos, props };
}
let bien = 0, n = 0;
function ver(nombre, ok, detalle) { n++; bien += ok ? 1 : 0; console.log((ok ? 'BIEN ' : 'MAL  ') + nombre + (detalle ? ' · ' + detalle : '')); }
const L = 'https://c2c.binance.com/es-LA/adv?code=1295&monto=59000&pago=PagoMovil&alt=11,22';
{ // la tarjeta
  const { ctx, pedidos } = cargar();
  const ok = ctx.avisarComprobanteNtfy_({ id: 'MOV-77', nombre: 'Juan Pérez García', monto: 100000, institucion: 'Mercado Pago',
    ref: '0123456789', confianza: 0.98, driveId: 'DRV1', hora: '14:32', telefono: '59899123456' }, 0.59);
  const c = JSON.parse(pedidos[0].o.payload), todo = JSON.stringify(c);
  ver('tarjeta enviada al tema, por el relay', ok && c.topic === 'bexo-prueba' && c.priority === 4 &&
      pedidos[0].url === 'http://vps:8082/ntfy?token=t', pedidos[0].url);
  ver('título corto', c.title === '💸 Juan P. · 100.000 ARS → 59.000 Bs', c.title);
  ver('detalle recortado', c.message === 'Mercado Pago · 14:32 · ref …6789 · lectura 98 %', c.message);
  ver('sin datos de más', !/Pérez|García|0123456|59899/.test(todo));
  ver('botón Armar llama al Apps Script con id y clave', c.actions[0].action === 'http' && c.actions[0].method === 'GET' &&
      c.actions[0].url === 'https://script.google.com/macros/s/X/exec?p2p=armar&id=MOV-77&k=clave123', c.actions[0].url);
  ver('botón Comprobante abre Drive', c.actions[1].action === 'view' && /DRV1/.test(c.actions[1].url));
}
function fila(moneda) { const d = []; d[2] = 'Juan Pérez'; d[3] = 100000; d[4] = moneda; d[5] = 'cuenta'; return d; }
function armar(moneda, texto, id) {
  const r = cargar();
  r.ctx.hojaMovimientos_ = () => ({});
  r.ctx.filaPorId_ = (sh, i) => i === 'MOV-77' ? { fila: 5, datos: fila(moneda) } : null;
  r.ctx.textoAnuncio_ = (monto, nombre) => { r.props.P2P_ULTIMA = JSON.stringify({ apodo: 'CARI7', precio: 1069 }); return texto; };
  r.resultado = r.ctx.armarDesdeNtfy_(id || 'MOV-77');
  const cuerpos = r.pedidos.map(p => JSON.parse(p.o.payload));
  r.cmd = cuerpos.filter(c => /-cmd$/.test(c.topic));
  r.avisos = cuerpos.filter(c => !/-cmd$/.test(c.topic));
  r.porRelay = r.pedidos.every(p => p.url.indexOf('http://vps:8082/ntfy?token=t') === 0);
  return r;
}
{ // el botón
  const r = armar('ARS', 'algo\n' + L + '\n🔁 Reservas: RonalditoP2P 1.069');
  ver('Armar: manda el link al teléfono', r.resultado === 'ok' && r.cmd.length === 1 && r.cmd[0].message === L);
  ver('todo pasa por el relay del VPS', r.porRelay);
  ver('Armar: avisa qué eligió', r.avisos.length === 1 && r.avisos[0].title === 'Armando · CARI7 · 59000 Bs' &&
      /RonalditoP2P/.test(r.avisos[0].message), r.avisos[0] && r.avisos[0].title);
  const otra = r.ctx.armarDesdeNtfy_('MOV-77');
  ver('doble toque: no busca otra vez', otra === 'ya estaba armando' && r.pedidos.filter(p => /-cmd$/.test(JSON.parse(p.o.payload).topic)).length === 1);
  const s = armar('ARS', 'No hay anuncios VES con Pago Movil');
  ver('sin anuncio: avisa y no manda nada al teléfono', s.resultado === 'sin anuncio' && !s.cmd.length && s.avisos[0].priority === 4);
  const v = armar('VES', L);
  ver('comprobante en VES: no arma', v.resultado === 'no ARS' && !v.cmd.length);
  const x = armar('ARS', L, 'NO-EXISTE');
  ver('id inexistente: no arma', x.resultado === 'no encontrado' && !x.cmd.length);
}
{ // el relay no responde: último recurso, directo a ntfy.sh
  const r = cargar();
  r.ctx.UrlFetchApp.fetch = (url, o) => { r.pedidos.push({ url, o });
    return { getResponseCode: () => (url.indexOf('http://vps') === 0 ? 502 : 200), getContentText: () => '' }; };
  const ok = r.ctx.avisarNtfy_('t', 'x');
  ver('relay caído: prueba directo a ntfy.sh', ok && r.pedidos.length === 2 && r.pedidos[1].url === 'https://ntfy.sh');
}
console.log(bien + ' de ' + n + ' bien');
process.exit(bien === n ? 0 : 1);
