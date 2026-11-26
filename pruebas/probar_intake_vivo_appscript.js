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
  const cache = {}, hojas = {}, ntfy = [], waha = [], activadores = [];
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
    ScriptApp: { getService: () => ({ getUrl: () => 'https://x' }), getProjectTriggers: () => activadores.slice(),
      deleteTrigger: t => activadores.splice(activadores.indexOf(t), 1),
      newTrigger: f => ({ timeBased: () => ({ after: ms => ({ create: () => activadores.push({ getHandlerFunction: () => f, ms }) }) }) }) },
    logError_: (a, b) => console.log('logError_', a, b)
  };
  vm.createContext(ctx);
  for (const f of ['0_Config', '1_Identidad', '4_LeerComprobantes', '9_P2P', '11_PreOrden', '21_Ntfy', '22_Intake', '23_IntakeVivo'])
    vm.runInContext(fs.readFileSync('apps-script/' + f + '.gs', 'utf8'), ctx);
  // sendWhatsAppMessage_ de 3_Operativa (el archivo entero necesita más de Google)
  const op = fs.readFileSync('apps-script/3_Operativa.gs', 'utf8');
  vm.runInContext('var WAHA_URL = "http://waha"; var WAHA_API_KEY = "w";\n' + op.match(/function sendWhatsAppMessage_[\s\S]*?\n}\n/)[0], ctx);
  ctx.tasaNetaActual_ = () => 0.52;
  vm.runInContext("var BUFFER_SHEET = 'Buffer'; var WINDOW_SEC = 60;", ctx);
  ctx.cuentasParaCobrar_ = () => ['APJ', 'NJ'];
  ctx.hojaMovimientos_ = () => hojas.Movimientos;   // sin mapear columnas: la prueba usa el orden por defecto
  return { ctx, hojas, ntfy, waha, props, activadores, hoja };
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
  ctx.registrarTandaIntake_('5491155550001', 'BEXO Ana', 'A cómo la tasa?', false, true, hace(5 * 3600));
  ver('tanda de hace 5 h (Buffer atrasado): se registra sin borrador', ntfy.length === 1 &&
      hojas.Intake.filas[hojas.Intake.filas.length - 1][7] === '0.52');
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
{ // 7. activador de una sola vez (no processBuffer): evalúa tandas cerradas una vez, se reagenda si hay abiertas
  const { ctx, hojas, ntfy, activadores, hoja } = cargar();
  ctx.agendarIntake_(); ctx.agendarIntake_();
  ver('con varios mensajes se agenda un solo activador a 75 s', activadores.length === 1 && activadores[0].ms === 75000);
  const b = hoja('Buffer');
  b.filas.push(['Teléfono', 'Nombre', 'Mensajes', 'Última', 'Int', 'Pri', 'Img', 'Cliente', 'Drive'],
    ['5491155550001', 'BEXO Ana', 'Hola corazón\nMe dices la tasa por favor', hace(80), '', '', false, true, ''],
    ['5491155550002', 'BEXO Juan Pérez', 'Me pasas el alias', hace(20), '', '', false, true, ''],
    ['5491155550001', 'BEXO Ana', 'A cómo está?', hace(5 * 3600), '', '', false, true, ''],
    ['5491199999999', 'Amigo', 'Hola a cómo la tasa', hace(80), '', '', false, false, '']);
  ctx.intakePorMensaje();
  const filas = (hojas.Intake || { filas: [] }).filas;
  ver('evalúa solo la tanda cerrada del cliente (no la abierta, la vieja ni el no cliente)', filas.length === 2 &&
      filas[1][2] === 'BEXO Ana' && ntfy.length === 1, filas.length + ' filas · ' + ntfy.length + ' borradores');
  ver('se borró y se reagendó para cuando cierre la abierta', activadores.length === 1 && activadores[0].ms <= 60000 && activadores[0].ms >= 50000,
      activadores.map(a => a.ms).join());
  ctx.intakePorMensaje();
  ver('la misma tanda no se evalúa dos veces', hojas.Intake.filas.length === 2 && ntfy.length === 1);
}
{ // 8. cuánto acierta: sugerido vs lo que contestaste en 30 min
  const { ctx } = cargar();
  const H = ['Fecha', 'Teléfono', 'Nombre', 'Quién', 'Texto', 'Foto', 'Intenciones', 'Sugerido', 'Tipos', 'A mano'];
  const f = (hm, tel, q, tipos, mano) => ['26/11/2026 ' + hm, tel, 'x', q, '', false, '', '', tipos, mano || ''];
  const filas = [H,
    f('10:00:00', '1', 'cliente', 'saludo tasa'), f('10:02:00', '1', 'vos', 'saludo'), f('10:03:00', '1', 'vos', 'tasa'),
    f('11:00:00', '2', 'cliente', 'calculo'), f('11:05:00', '2', 'vos', 'otro'),
    f('12:00:00', '3', 'cliente', '', 'otra ruta'), f('12:01:00', '3', 'vos', 'saludo'),
    f('13:00:00', '4', 'cliente', 'alias')];
  const r = ctx.medirIntake_(filas, 7, new Date(2026, 10, 26, 18).getTime());
  ver('mide aciertos, faltas y sobras', r.tandas === 4 && r.vos === 4 && r.tipos.saludo.ok === 1 && r.tipos.tasa.ok === 1 &&
      r.tipos.calculo.sobro === 1 && r.tipos.saludo.falto === 1 && r.sinRespuesta === 1 && r.aMano['otra ruta'] === 1, JSON.stringify(r));
  const sinVos = ctx.textoMedicionIntake_(ctx.medirIntake_([H, f('10:00:00', '1', 'cliente', 'tasa')], 7, new Date(2026, 10, 26, 18).getTime()), 7);
  ver('sin tus mensajes avisa cómo arreglarlo', /No llegan tus mensajes/.test(sinVos), sinVos);
  ver('lee la fecha como la muestra la hoja', ctx.fechaIntake_('26/11/2026 8:21:11') === new Date(2026, 10, 26, 8, 21, 11).getTime());
}
{ // 8. activador colgado (26/11: disparó contra una versión sin intakePorMensaje y bloqueó 3 horas)
  const { ctx, activadores, props } = cargar();
  ctx.agendarIntake_();
  ver('agenda y anota la hora', activadores.length === 1 && Number(props.IK_AGENDADO) > 0);
  ctx.agendarIntake_();
  ver('uno reciente: no agenda otro', activadores.length === 1);
  props.IK_AGENDADO = String(Date.now() - 20 * 60e3);
  ctx.agendarIntake_();
  ver('uno de hace 20 min está colgado: lo cambia por uno nuevo', activadores.length === 1 &&
      Date.now() - Number(props.IK_AGENDADO) < 5000);
}
console.log(`${bien} de ${n} bien`);
process.exit(bien === n ? 0 : 1);
