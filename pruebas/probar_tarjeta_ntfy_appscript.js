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
  for (const f of ['0_Config', '4_LeerComprobantes', '9_P2P', '10_AgendaCuentas', '11_PreOrden', '21_Ntfy', '23_IntakeVivo'])
    vm.runInContext(fs.readFileSync('apps-script/' + f + '.gs', 'utf8'), ctx);
  ctx.textoChatCliente_ = () => '';
  // las fechas se crean dentro del contexto del Apps Script (si no, instanceof Date da false)
  const FechaGs = vm.runInContext('Date', ctx);
  ctx.leerAgenda_ = () => AGENDA.map(c => Object.assign({}, c, { msj: new FechaGs(c.msj.getTime()) }));
  return { ctx, pedidos, props };
}
const ahora = new Date();
// Agenda de prueba: Juan mandó recién un Pago Móvil Banesco; Ana tiene una transferencia Mercantil de siempre.
const AGENDA = [
  { clave: 'a', tipo: 'PM', banco: '0134', numero: '04141234567', titular: 'Juan Perez', clientes: ['BEXO Juan Pérez'],
    veces: 1, msj: ahora, de: 'BEXO Juan Pérez' },
  { clave: 'b', tipo: 'TRANSF', banco: '0105', numero: '01050000000000009876', titular: 'Rosa Diaz', clientes: ['BEXO Ana'],
    veces: 3, msj: new Date(ahora - 30 * 864e5), de: 'BEXO Ana' }];
let bien = 0, n = 0;
function ver(nombre, ok, detalle) { n++; bien += ok ? 1 : 0; console.log((ok ? 'BIEN ' : 'MAL  ') + nombre + (detalle ? ' · ' + detalle : '')); }
{ // sin datos en la Agenda: el segundo botón pide la cuenta
  const { ctx, pedidos } = cargar();
  ctx.avisarComprobanteNtfy_({ id: 'MOV-88', nombre: 'BEXO Nadie', monto: 70000, hora: '12:00' }, 0.585);
  const c = JSON.parse(pedidos[0].o.payload);
  ver('sin cuenta: avisa y el botón es "Pedir cuenta"', /Sin datos de cuenta/.test(c.message) && c.actions[1].label === '💬 Pedir cuenta' &&
      /\?intake=cuenta&id=MOV-88/.test(c.actions[1].url), c.actions[1].label);
}
const L = 'https://c2c.binance.com/es-LA/adv?code=1295&monto=59000&pago=PagoMovil&alt=11,22';
{ // la tarjeta
  const { ctx, pedidos } = cargar();
  const ok = ctx.avisarComprobanteNtfy_({ id: 'MOV-77', nombre: 'BEXO Juan Pérez', monto: 100000, institucion: 'Mercado Pago',
    ref: '0123456789', confianza: 0.98, driveId: 'DRV1', hora: '14:32', telefono: '59899123456' }, 0.59);
  const c = JSON.parse(pedidos[0].o.payload), todo = JSON.stringify(c);
  ver('tarjeta enviada al tema, por el relay', ok && c.topic === 'bexo-prueba' && c.priority === 4 &&
      pedidos[0].url === 'http://vps:8082/ntfy?token=t', pedidos[0].url);
  ver('título: nombre sin BEXO y un solo emoji (la etiqueta)', c.title === 'Juan Pérez · 100.000 ARS → 59.000 Bs' &&
      JSON.stringify(c.tags) === '["moneybag"]', c.title);
  const largo = ctx.nombreTarjeta_('BEXO - María Fernanda Gutiérrez Rodríguez');
  ver('nombre largo: cortado con …', largo === 'María Fernanda Gutiér…' && largo.length <= 22, largo);
  ver('sin prefijo BEXO queda igual', ctx.nombreTarjeta_('bexo:Ana') === 'Ana' && ctx.nombreTarjeta_('Pedro') === 'Pedro');
  ver('detalle recortado', c.message === 'Mercado Pago · 14:32 · ref …6789 · lectura 98 %\n→ PM Banesco …4567 · mandó ahora',
      JSON.stringify(c.message));
  ver('sin datos de más', !/BEXO|0123456|59899/.test(todo));
  ver('botón Armar llama al Apps Script con id y clave', c.actions[0].action === 'http' && c.actions[0].method === 'GET' &&
      c.actions[0].url === 'https://script.google.com/macros/s/X/exec?p2p=armar&id=MOV-77&k=clave123', c.actions[0].url);
  ver('el botón Armar queda después de tocarlo (sirve para reintentar)', c.actions[0].clear === false);
  ver('botón Ok fino llama al intake con el id', c.actions[1].action === 'http' &&
      c.actions[1].url === 'https://script.google.com/macros/s/X/exec?intake=okfino&id=MOV-77&k=clave123', c.actions[1].url);
  ver('botón Comprobante abre Drive', c.actions[2].action === 'view' && /DRV1/.test(c.actions[2].url));
}
function fila(moneda, nombre) { const d = []; d[2] = nombre || 'BEXO Juan Pérez'; d[3] = 100000; d[4] = moneda; d[5] = 'Mercado Pago'; return d; }
function armar(moneda, texto, id, nombre) {
  const r = cargar();
  r.ctx.hojaMovimientos_ = () => ({});
  r.ctx.filaPorId_ = (sh, i) => i === 'MOV-77' ? { fila: 5, datos: fila(moneda, nombre) } : null;
  r.ctx.textoAnuncio_ = (monto, nom, cuenta) => { r.cuentaUsada = cuenta; r.props.P2P_ULTIMA = JSON.stringify({ apodo: 'CARI7', precio: 1069 }); return texto; };
  r.resultado = r.ctx.armarDesdeNtfy_(id || 'MOV-77');
  const cuerpos = r.pedidos.map(p => JSON.parse(p.o.payload));
  r.cmd = cuerpos.filter(c => /-cmd$/.test(c.topic));
  r.avisos = cuerpos.filter(c => !/-cmd$/.test(c.topic));
  r.porRelay = r.pedidos.every(p => p.url.indexOf('http://vps:8082/ntfy?token=t') === 0);
  return r;
}
{ // el botón
  const r = armar('ARS', 'algo\n' + L + '\n🔁 Reservas: RonalditoP2P 1.069');
  const FIN = 'https://script.google.com/macros/s/X/exec?p2p=fin&id=MOV-77&k=clave123';
  ver('Armar: manda el link al teléfono, con el id y el botón FIN', r.resultado === 'ok' && r.cmd.length === 1 &&
      r.cmd[0].message === L + '&mov=MOV-77&fin=' + encodeURIComponent(FIN), r.cmd[0] && r.cmd[0].message);
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
{ // método: sale de la cuenta del cliente (17/11: caía en Banco de Venezuela)
  const j = armar('ARS', 'x\n' + L);
  ver('Juan: usa su Pago Móvil Banesco → método PagoMovil', j.cuentaUsada && j.cuentaUsada.clave === 'a' &&
      JSON.stringify(j.ctx.metodosParaCuenta_(j.cuentaUsada)) === '["PagoMovil"]');
  ver('nunca usa tu cuenta de cobro (columna CUENTA)', typeof j.cuentaUsada !== 'string');
  ver('el aviso "Armando" dice a qué cuenta', /→ PM Banesco …4567/.test(j.avisos[0].message), j.avisos[0].message);
  const a2 = armar('ARS', 'x\n' + L, 'MOV-77', 'BEXO Ana');
  ver('Ana: la de siempre (transferencia Mercantil) → método Mercantil', a2.cuentaUsada && a2.cuentaUsada.clave === 'b' &&
      JSON.stringify(a2.ctx.metodosParaCuenta_(a2.cuentaUsada)) === '["Mercantil"]' && /la de siempre/.test(a2.avisos[0].message));
  const z = armar('ARS', 'x\n' + L, 'MOV-77', 'BEXO Nadie');
  ver('sin datos de cuenta: lo avisa', z.cuentaUsada === null && /Sin datos de cuenta/.test(z.avisos[0].message));
}
{ // FIN: lo mismo que Confirmar en la página, con la cuenta usada para armar
  const r = cargar(), llamadas = [];
  r.ctx.hojaMovimientos_ = () => ({});
  r.ctx.filaPorId_ = (sh, i) => i === 'MOV-77' ? { fila: 5, datos: fila('ARS') } : null;
  r.ctx.confirmarPreOrdenWeb = (k, id, monto, clave, texto) => {
    llamadas.push([k, id, monto, clave]);
    if (llamadas.length > 1) throw new Error('Ya estaba confirmada');
    return {};
  };
  ver('FIN confirma con la cuenta del cliente', r.ctx.finDesdeNtfy_('MOV-77') === 'contado' &&
      JSON.stringify(llamadas[0]) === '["clave123","MOV-77",100000,"a"]', JSON.stringify(llamadas[0]));
  const aviso = JSON.parse(r.pedidos[r.pedidos.length - 1].o.payload);
  ver('FIN avisa "Contado"', /^Contado · Juan Pérez · 100.000 ARS/.test(aviso.title), aviso.title);
  ver('segundo FIN: ya estaba', r.ctx.finDesdeNtfy_('MOV-77') === 'ya estaba');
  ver('FIN con id inexistente', r.ctx.finDesdeNtfy_('NO') === 'no encontrado');
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
