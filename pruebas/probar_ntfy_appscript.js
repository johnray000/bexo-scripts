// Prueba sin Google el aviso de pre-orden por ntfy: node pruebas/probar_ntfy_appscript.js (desde la raíz del repo)
const fs = require('fs'), vm = require('vm');
function cargar(conTopic) {
  const props = { P2P_ULTIMA: JSON.stringify({ apodo: 'CARI7', precio: 1069 }), RELAY_URL: 'http://vps:8082', RELAY_TOKEN: 't' };
  if (conTopic) props.NTFY_TOPIC = 'bexo-prueba';
  const enviados = { ntfy: [], wa: [] };
  const ctx = { console, Logger: { log: () => {} },
    PropertiesService: { getScriptProperties: () => ({ getProperties: () => props, getProperty: k => props[k] || null,
                                                       setProperty: (k, v) => { props[k] = v; } }) },
    UrlFetchApp: { fetch: (url, o) => { enviados.ntfy.push({ url, cuerpo: JSON.parse(o.payload) });
                                        return { getResponseCode: () => 200, getContentText: () => '' }; } },
    logError_: (a, b) => console.log('logError_', a, b) };
  vm.createContext(ctx);
  for (const f of ['0_Config', '9_P2P', '11_PreOrden', '21_Ntfy']) vm.runInContext(fs.readFileSync('apps-script/' + f + '.gs', 'utf8'), ctx);
  ctx.whatsAppConfirmado_ = t => { enviados.wa.push(t); return true; };
  return { ctx, enviados };
}
const L = 'https://c2c.binance.com/es-LA/adv?code=1295&monto=5000&pago=PagoMovil&alt=11,22';
const texto = '*Juan* · Enviar *5.000 Bs*\n👤 CARI7 · nuevo\n' + L + '\n🔁 Reservas: RonalditoP2P 1.069 · YourPerfectDeal2025 1.068 (−0.1%)';
let bien = 0, n = 0;
function ver(nombre, ok, detalle) { n++; bien += ok ? 1 : 0; console.log((ok ? 'BIEN ' : 'MAL  ') + nombre + (detalle ? ' · ' + detalle : '')); }
{ // con ntfy: va a ntfy con botón al tema -cmd y sin el nombre del cliente; no manda el link solo por WhatsApp
  const { ctx, enviados } = cargar(true);
  ctx.avisarPreOrdenTelefono_(texto);
  const c = (enviados.ntfy[0] || {}).cuerpo || {};
  const b = (c.actions || [])[0] || {};
  ver('con ntfy: un aviso, sin WhatsApp', enviados.ntfy.length === 1 && enviados.wa.length === 0);
  ver('título', c.title === '💸 CARI7 · 5000 Bs · PagoMovil', c.title);
  ver('reservas en el texto', /RonalditoP2P/.test(c.message));
  ver('sin datos del cliente', !/Juan/.test(JSON.stringify(c)));
  ver('botón al tema de comandos con el link', b.action === 'http' && b.url === 'https://ntfy.sh/bexo-prueba-cmd' &&
      b.body === L && b.label === 'Armar en Binance', JSON.stringify(b));
  ver('prioridad alta', c.priority === 4 && c.topic === 'bexo-prueba');
}
{ // sin ntfy: el link solo por WhatsApp, como antes
  const { ctx, enviados } = cargar(false);
  ctx.avisarPreOrdenTelefono_(texto);
  ver('sin ntfy: link solo por WhatsApp', enviados.ntfy.length === 0 && enviados.wa.length === 1 && enviados.wa[0] === L);
}
console.log(bien + ' de ' + n + ' bien');
process.exit(bien === n ? 0 : 1);
