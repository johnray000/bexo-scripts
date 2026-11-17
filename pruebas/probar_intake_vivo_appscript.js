// Prueba sin Google el intake en vivo (apps-script/23_IntakeVivo.gs): hoja Intake, estado de cada chat,
// borradores en ntfy, botón "📤 Enviar" (un solo uso) y "💬 Ok fino" (una vez por operación).
//   node pruebas/probar_intake_vivo_appscript.js   (desde la raíz del repo)
const fs = require('fs'), vm = require('vm');
let bien = 0, n = 0;
function ver(nombre, ok, detalle) { n++; bien += ok ? 1 : 0; console.log((ok ? 'BIEN ' : 'MAL  ') + nombre + (detalle ? ' · ' + detalle : '')); }

function cargar(modo) {
  const props = { NTFY_TOPIC: 'bexo-prueba', RELAY_URL: 'http://vps:8082', RELAY_TOKEN: 't', P2P_CLAVE: 'k1',
                  WEBAPP_URL: 'https://script.google.com/macros/s/X/exec', MI_TELEFONO: '5491100000000', TASA_BCV: '900' };
  if (modo) props.INTAKE_MODO = modo;
  const cache = {}, hojas = {}, ntfy = [], waha = [];
  const hoja = nombre => hojas[nombre] || (hojas[nombre] = {
    filas: [], appendRow(r) { this.filas.push(r); }, getRange: () => ({ setFontWeight() { return this; } }), setFrozenRows() {},
    getDataRange() { return { getValues: () => this.filas }; },
    getLastColumn() { return Math.max(1, ...this.filas.map(f => f.length)); }, getLastRow() { return this.filas.length; } });
  hoja('Directorio').filas.push(['Teléfono', 'Nombre'], ['5491155550001', 'BEXO Ana'], ['5491155550002', 'BEXO Juan Pérez']);
  hoja('Movimientos');
  const ctx = {
    console, Logger: { log: () => {} }, Session: { getScriptTimeZone: () => 'America/Montevideo' },
    PropertiesService: { getScriptProperties: () => ({ getProperties: () => props, getProperty: k => props[k] || null,
      setProperty: (k, v) => { props[k] = v; } }) },
    CacheService: { getScriptCache: () => ({ get: k => (k in cache ? cache[k] : null), put: (k, v) => { cache[k] = v; }, remove: k => { delete cache[k]; } }) },
    SpreadsheetApp: { getActiveSpreadsheet: () => ({ getSheetByName: k => hojas[k] || null, insertSheet: hoja }) },
    UrlFetchApp: { fetch: (url, o) => {
      if (/ntfy/.test(url)) ntfy.push(JSON.parse(o.payload));
      else if (/sendText/.test(url)) waha.push(JSON.parse(o.payload));
      return { getResponseCode: () => (/dolarapi|yadio/.test(url) ? 503 : 200), getContentText: () => '{}' };
    } },
    Utilities: { sleep: () => {}, formatDate: () => '15', getUuid: () => 'u' },
    ContentService: { createTextOutput: t => ({ texto: t }) },
    ScriptApp: { getService: () => ({ getUrl: () => 'https://x' }) },
    logError_: (a, b) => console.log('logError_', a, b)
  };
  vm.createContext(ctx);
  for (const f of ['0_Config', '1_Identidad', '4_LeerComprobantes', '9_P2P', '11_PreOrden', '21_Ntfy', '22_Intake', '23_IntakeVivo'])
    vm.runInContext(fs.readFileSync('apps-script/' + f + '.gs', 'utf8'), ctx);
  // sendWhatsAppMessage_ de 3_Operativa (el archivo entero necesita más de Google)
  const op = fs.readFileSync('apps-script/3_Operativa.gs', 'utf8');
  vm.runInContext('var WAHA_URL = "http://waha"; var WAHA_API_KEY = "w";\n' + op.match(/function sendWhatsAppMessage_[\s\S]*?\n}\n/)[0], ctx);
  ctx.tasaNetaActual_ = () => 0.52;
  ctx.cuentasParaCobrar_ = () => ['APJ', 'NJ'];
  ctx.hojaMovimientos_ = () => hojas.Movimientos;   // sin mapear columnas: la prueba usa el orden por defecto
  return { ctx, hojas, ntfy, waha, props };
}
const tuyo = (tel, body, extra) => Object.assign({ fromMe: true, body, hasMedia: false,
  _data: { Info: { Chat: tel + '@s.whatsapp.net', Sender: '5491100000000@s.whatsapp.net', IsFromMe: true } } }, extra || {});
const hace = s => new Date(Date.now() - s * 1000);
const urlId = u => decodeURIComponent(u.match(/id=([^&]+)/)[1]);

{ // 1. pide tasa sin saludo previo: borrador con saludo + tasa; Enviar manda los dos; segundo toque no repite
  const { ctx, hojas, ntfy, waha } = cargar();
  const r = ctx.registrarTandaIntake_('5491155550001', 'BEXO Ana', 'Hola buenas tardes\nA cómo la tasa?', false, true, hace(70));
  ver('tanda registrada en Intake', hojas.Intake.filas.length === 2 && hojas.Intake.filas[1][3] === 'cliente');
  ver('sugiere saludo + tasa', JSON.stringify(r.tipos) === '["saludo","tasa"]', JSON.stringify(r.mensajes));
  const b = ntfy[0] || {};
  ver('borrador en ntfy con botón Enviar', b.title === 'Ana' && b.actions && b.actions[0].label === '📤 Enviar' &&
      /\?intake=enviar&id=IK/.test(b.actions[0].url), b.title);
  ver('el borrador muestra lo que se va a mandar', /→ Hola buenas tardes como estás\n→ 0.52/.test(b.message), JSON.stringify(b.message));
  const id = urlId(b.actions[0].url);
  const out = ctx.rutaIntake_({ intake: 'enviar', id, k: 'k1' });
  ver('Enviar manda los 2 mensajes por WAHA al cliente', out.texto === 'enviado' && waha.length === 2 &&
      waha[0].chatId === '5491155550001@c.us' && waha[1].text === '0.52', JSON.stringify(waha.map(w => w.text)));
  ver('segundo toque no manda nada', ctx.rutaIntake_({ intake: 'enviar', id, k: 'k1' }).texto === 'vencida o ya enviada' && waha.length === 2);
}
{ // 2. ya saludaste vos: la tasa sola; alias con mitad y mitad
  const { ctx, ntfy, hojas } = cargar();
  ctx.registrarMensajeTuyo_(tuyo('5491155550002', 'Buenas tardes hermano como estás'));
  ver('tu mensaje queda en Intake como "vos"', hojas.Intake.filas[1][3] === 'vos' && hojas.Intake.filas[1][8] === 'saludo');
  const r = ctx.registrarTandaIntake_('5491155550002', 'BEXO Juan Pérez', 'Me pasas el alias? son 300.000 pesos', false, true, hace(400));
  ver('sin saludo (ya saludaste) y alias mitad y mitad', JSON.stringify(r.tipos) === '["alias"]' &&
      r.mensajes.includes('Envía mitad y mitad') && r.mensajes.includes('John.ray.astro') && r.mensajes.includes('John.ray.naranja'),
      JSON.stringify(r.mensajes));
  ver('igual llega el borrador', ntfy.length === 1);
}
{ // 3. contestaste vos mientras la tanda esperaba: no hay borrador
  const { ctx, ntfy } = cargar();
  ctx.registrarTandaIntake_('5491155550001', 'BEXO Ana', 'Hola', false, true, hace(4000));
  ctx.registrarMensajeTuyo_(tuyo('5491155550001', '0.52'));
  ctx.registrarTandaIntake_('5491155550001', 'BEXO Ana', 'A cómo la tasa?', false, true, hace(90));
  ver('sin borrador si ya contestaste', ntfy.length === 0, ntfy.length + ' borradores');
}
{ // 4. foto, no cliente, solo saludo, modo registro y apagado
  const { ctx, ntfy, hojas } = cargar();
  ctx.registrarTandaIntake_('5491155550001', 'BEXO Ana', '[Mensaje sin texto]', true, true, hace(70));
  ver('la foto no genera borrador (lo hace la tarjeta)', ntfy.length === 0);
  ctx.registrarTandaIntake_('5491199999999', 'Amigo', 'Hola a cómo la tasa', false, false, hace(70));
  ver('no cliente: ni hoja ni ntfy', hojas.Intake.filas.length === 2 && ntfy.length === 0);
  ctx.registrarTandaIntake_('5491155550002', 'BEXO Juan Pérez', 'Hola buenas', false, true, hace(70));
  ver('solo saludo: queda registrado, sin borrador', ntfy.length === 0 && hojas.Intake.filas.length === 3);
  ctx.registrarMensajeTuyo_(tuyo('5491199999999', 'hola'));
  ver('tus mensajes a quien no es cliente no se registran', hojas.Intake.filas.length === 3);
  const reg = cargar('registro');
  reg.ctx.registrarTandaIntake_('5491155550001', 'BEXO Ana', 'A cómo la tasa?', false, true, hace(70));
  ver('modo registro: hoja sí, ntfy no', reg.hojas.Intake.filas.length === 2 && reg.ntfy.length === 0);
  const ap = cargar('apagado');
  ap.ctx.registrarTandaIntake_('5491155550001', 'BEXO Ana', 'A cómo la tasa?', false, true, hace(70));
  ver('modo apagado: nada', !ap.hojas.Intake && ap.ntfy.length === 0);
}
{ // 5. "Ok fino" de la tarjeta: una vez por operación; tu "Listo" cierra y vuelve a habilitar
  const { ctx, hojas, waha } = cargar();
  const fila = []; fila[ctx.C.ID - 1] = 'MOV-1'; fila[ctx.C.TELEFONO - 1] = '5491155550002';
  hojas.Movimientos.filas.push(ctx.ENCABEZADOS, fila);
  ver('Ok fino se manda', ctx.rutaIntake_({ intake: 'okfino', id: 'MOV-1' }).texto === 'enviado' &&
      waha[0].text === 'Ok fino te aviso apenas tenga el capturé');
  ver('no se repite en la misma operación', ctx.rutaIntake_({ intake: 'okfino', id: 'MOV-1' }).texto === 'ya estaba dicho' && waha.length === 1);
  ctx.registrarMensajeTuyo_(tuyo('5491155550002', 'Listo mí pana 👍🏼'));
  ver('después de tu "Listo" se puede de nuevo', ctx.rutaIntake_({ intake: 'okfino', id: 'MOV-1' }).texto === 'enviado' && waha.length === 2);
  ver('Pedir cuenta con Ok fino ya dicho: solo la pregunta', ctx.rutaIntake_({ intake: 'cuenta', id: 'MOV-1' }).texto === 'enviado' &&
      waha.length === 3 && waha[2].text === 'Confírmame a qué cuenta', JSON.stringify(waha.map(w => w.text)));
  ver('Pedir cuenta no se repite', ctx.rutaIntake_({ intake: 'cuenta', id: 'MOV-1' }).texto === 'ya estaba dicho' && waha.length === 3);
  ver('id desconocido', ctx.rutaIntake_({ intake: 'okfino', id: 'MOV-9' }).texto === 'no encontrado');
}
{ // 6. datos en ntfy tapados; tu número no cuenta como chat
  const { ctx } = cargar();
  ver('números largos tapados en ntfy', ctx.textoCortoIntake_('Banesco 0412-555-0101 cédula 12.345.678') === 'Banesco ••• cédula •••',
      ctx.textoCortoIntake_('Banesco 0412-555-0101 cédula 12.345.678'));
  ver('el chat de tu mensaje es el cliente, no vos', ctx.telefonoChat_(tuyo('5491155550001', 'x')) === '5491155550001');
}
console.log(`${bien} de ${n} bien`);
process.exit(bien === n ? 0 : 1);
