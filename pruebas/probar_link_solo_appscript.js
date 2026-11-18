// Prueba sin Google el mensaje con el link solo: node pruebas/probar_link_solo_appscript.js (desde la raíz del repo)
const fs=require('fs'),vm=require('vm');
const ctx={CONFIG:{},PropertiesService:{getScriptProperties:()=>({getProperty:()=>null})},console};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync('apps-script/9_P2P.gs','utf8'),ctx);
vm.runInContext(fs.readFileSync('apps-script/11_PreOrden.gs','utf8'),ctx);
const enviados=[]; ctx.whatsAppConfirmado_=t=>{enviados.push(t);return true;};
const L='https://c2c.binance.com/es-LA/adv?code=1295&monto=5000&pago=PagoMovil&alt=11,22';
const casos=[['*Orden P2P*\nVender\n'+L+'\n🔁 Reservas: x', L],
  ['python ~/bexo-scripts/binance_orden.py "'+L+'"', L],
  ['sin link', '']];
let bien=0;
casos.forEach(([t,esp])=>{const r=ctx.linkAnuncioDe_(t); const ok=r===esp; bien+=ok; console.log((ok?'BIEN ':'MAL  ')+JSON.stringify(r));});
ctx.enviarLinkSolo_(casos[0][0]); ctx.enviarLinkSolo_('nada');
console.log(enviados.length===1&&enviados[0]===L?'BIEN envía solo el link, una vez':'MAL '+JSON.stringify(enviados));
