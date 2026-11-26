// ==========================================
// MÓDULO 23: INTAKE EN VIVO — registra cada tanda y te propone la respuesta en ntfy
//
// - Con cada mensaje de un cliente, doPost (2_Recepcion) llama a agendarIntake_: un activador de una sola vez
//   (como la lectura de 90 s) corre intakePorMensaje a los 75 s y evalúa las tandas del Buffer que ya se cerraron
//   (60 s sin mensajes nuevos). processBuffer (cada 12 h) no tiene nada que ver.
//   doPost llama a registrarMensajeTuyo_ con cada mensaje tuyo.
// - Todo queda en la hoja Intake (cliente y vos), para comparar lo sugerido con lo que contestaste.
// - Si la sugerencia trae tasa, cálculo, alias o disponibilidad, llega a ntfy como borrador con "📤 Enviar".
//   Nada sale sin tu toque. La foto no genera borrador: la tarjeta del comprobante trae "💬 Ok fino".
// - Propiedad INTAKE_MODO: 'borrador' (por defecto), 'registro' (solo la hoja) o 'apagado'.
// Usa: respuestaIntake_, tasasIntake_, FRASES_JOHN (22), sendWhatsAppMessage_ (3), avisarNtfy_, nombreTarjeta_ (21),
//      claveNext_ (9), filaPorId_, hojaMovimientos_, C (4), DIR_SHEET (1).
// Pruebas: node pruebas/probar_intake_vivo_appscript.js
// ==========================================

var INTAKE_HOJA = 'Intake';
var INTAKE_ENCABEZADOS = ['Fecha', 'Teléfono', 'Nombre', 'Quién', 'Texto', 'Foto', 'Intenciones', 'Sugerido', 'Tipos', 'A mano'];
var INTAKE_SUGERENCIA_SEG = 6 * 3600;            // el botón "Enviar" sirve 6 h
var INTAKE_TIPOS_BORRADOR = ['tasa', 'calculo', 'alias', 'disponible'];
var INTAKE_BORRADOR_MAX_MIN = 10;   // una tanda más vieja (p. ej. el Buffer atrasado) se registra pero no genera borrador

function modoIntake_() {
  return String(PropertiesService.getScriptProperties().getProperty('INTAKE_MODO') || 'borrador').toLowerCase();
}

function hojaIntake_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet(), sh = ss.getSheetByName(INTAKE_HOJA);
  if (!sh) {
    sh = ss.insertSheet(INTAKE_HOJA);
    sh.appendRow(INTAKE_ENCABEZADOS);
    sh.getRange(1, 1, 1, INTAKE_ENCABEZADOS.length).setFontWeight('bold');
    sh.setFrozenRows(1);
  }
  return sh;
}

// ---------- estado de cada chat (lo que ya dijiste) ----------
function estadoChat_(tel) {
  try { return JSON.parse(PropertiesService.getScriptProperties().getProperty('IK_' + tel) || '{}'); } catch (e) { return {}; }
}
function guardarEstadoChat_(tel, est) {
  PropertiesService.getScriptProperties().setProperty('IK_' + tel, JSON.stringify(est));
}

/** Qué fue tu mensaje (las mismas categorías que la repetición de pruebas). */
function tipoTuyo_(texto, media) {
  var t = normIntake_(texto);
  if (!t) return media ? 'foto' : '';
  if (/te aviso apenas tenga/.test(t)) return 'en_proceso';
  if (/^listo\b/.test(t)) return 'cierre';
  if (/^0[.,]\d{2,3}$/.test(t)) return 'tasa';
  if (/^[\d.,]+ ?(mil )?(pesos|bs|bolivares|dolares|\$)/.test(t)) return 'calculo';
  if (/^john\.|alias/.test(t)) return 'alias';
  if (/disponibilidad|^si dale/.test(t)) return 'disponible';
  if (/^(hola|buen ?dia|buen[oa]s|bien dia|que tal)/.test(t)) return 'saludo';
  return 'otro';
}

/** Número del chat en un mensaje tuyo (el destinatario, no vos). */
function telefonoChat_(payload) {
  var d = payload._data || {}, info = d.Info || d.info || {}, key = d.key || {};
  var cands = [info.Chat, info.RecipientAlt, payload.to, payload.from, key.remoteJid, key.remoteJidAlt];
  for (var i = 0; i < cands.length; i++) {
    var c = String(cands[i] || '');
    if (c.indexOf('@s.whatsapp.net') !== -1 || c.indexOf('@c.us') !== -1) {
      var n = c.replace(/@.*/, '').replace(/\D/g, '');
      if (n && n !== String(MI_TELEFONO)) return n;
    }
  }
  for (var j = 0; j < cands.length; j++) {
    var lid = String(cands[j] || '');
    if (lid.indexOf('@lid') !== -1 && typeof numeroDeLid_ === 'function') { var pn = numeroDeLid_(lid); if (pn) return pn; }
  }
  return '';
}

/** Nombre del Directorio para ese teléfono (últimos 8 dígitos), o '' si no es cliente. Se guarda 10 min. */
function clienteDelDirectorio_(tel) {
  var cache = CacheService.getScriptCache(), k = 'ik_dir_' + tel, c = cache.get(k);
  if (c !== null) return c;
  var nombre = '', sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(DIR_SHEET);
  if (sh) {
    var datos = sh.getDataRange().getValues(), fin = String(tel).replace(/\D/g, '').slice(-8);
    for (var i = 1; i < datos.length && fin.length === 8; i++) {
      if (String(datos[i][0]).replace(/\D/g, '').slice(-8) === fin) { nombre = String(datos[i][1]); break; }
    }
  }
  cache.put(k, nombre, 600);
  return nombre;
}

/** doPost → cada mensaje tuyo. Solo chats de clientes. */
function registrarMensajeTuyo_(payload) {
  if (modoIntake_() === 'apagado') return;
  var tel = telefonoChat_(payload);
  if (!tel) return;
  var nombre = clienteDelDirectorio_(tel);
  if (!nombre) return;
  var texto = payload.body || '', media = payload.hasMedia === true, tipo = tipoTuyo_(texto, media), ahora = Date.now();
  var est = estadoChat_(tel);
  est.ultJohn = ahora;
  if (tipo === 'saludo') est.ultSaludo = ahora; else est.ultRespuesta = ahora;
  if (tipo === 'en_proceso') { est.enProceso = ahora; est.foto = 0; }
  if (tipo === 'cierre' || tipo === 'foto') { est.enProceso = 0; est.foto = 0; }   // tu capture = pago hecho: cierra la operación
  guardarEstadoChat_(tel, est);
  hojaIntake_().appendRow([new Date(), tel, nombre, 'vos', texto || (media ? '[foto]' : ''), media, '', '', tipo, '']);
}

var INTAKE_ESPERA_SEG = 75;   // la tanda se cierra a los 60 s (WINDOW_SEC) sin mensajes nuevos

/** doPost → mensaje de un cliente. Rápido: solo agenda (si no hay ya uno en camino). */
function agendarIntake_(segundos) {
  try {
    if (modoIntake_() === 'apagado') return;
    var props = PropertiesService.getScriptProperties();
    var mios = ScriptApp.getProjectTriggers().filter(function (t) { return t.getHandlerFunction() === 'intakePorMensaje'; });
    // 26/11: un activador que disparó contra una versión sin esta función quedó colgado y bloqueó el intake
    // 3 horas. Uno con más de 5 min ya debió correr: se borra y se agenda de nuevo.
    var agendado = Number(props.getProperty('IK_AGENDADO')) || 0;
    if (mios.length && Date.now() - agendado > 5 * 60e3) {
      mios.forEach(function (t) { ScriptApp.deleteTrigger(t); });
      logError_('INTAKE_AGENDAR', 'Activador colgado (' + Math.round((Date.now() - agendado) / 60e3) + ' min): se agenda de nuevo');
      mios = [];
    }
    if (!mios.length) {
      ScriptApp.newTrigger('intakePorMensaje').timeBased().after((segundos || INTAKE_ESPERA_SEG) * 1000).create();
      props.setProperty('IK_AGENDADO', String(Date.now()));
    }
  } catch (e) {
    logError_('INTAKE_AGENDAR', e.message || e);
  }
}

/** La corre el activador de una sola vez. Evalúa cada tanda cerrada una sola vez; si queda alguna abierta, se reagenda. */
function intakePorMensaje() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'intakePorMensaje') ScriptApp.deleteTrigger(t);
  });
  var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(BUFFER_SHEET);
  if (!sh) return;
  var datos = sh.getDataRange().getValues(), ahora = Date.now(), cache = CacheService.getScriptCache(), abierta = 0;
  for (var i = 1; i < datos.length; i++) {
    var f = datos[i], fecha = new Date(f[3]), edad = (ahora - fecha.getTime()) / 1000;
    if (String(f[7]).toUpperCase() !== 'TRUE' || !(edad >= 0) || edad > 3600) continue;   // clientes, última hora
    if (edad <= WINDOW_SEC) { abierta = Math.max(abierta, WINDOW_SEC - edad); continue; }   // todavía puede crecer
    var clave = 'ikev_' + f[0] + '_' + fecha.getTime();
    if (cache.get(clave)) continue;
    cache.put(clave, '1', 21600);
    try { registrarTandaIntake_(String(f[0]), String(f[1]), String(f[2]), String(f[6]).toUpperCase() === 'TRUE', true, fecha); }
    catch (e) { logError_('INTAKE_TANDA', e.message || e); }
  }
  if (abierta) agendarIntake_(Math.ceil(abierta) + 15);
}

/** Una tanda del cliente que se cerró (la llama intakePorMensaje). */
function registrarTandaIntake_(tel, nombre, texto, media, esCliente, fecha) {
  var modo = modoIntake_();
  if (modo === 'apagado' || !esCliente) return null;
  var ahora = Date.now(), est = estadoChat_(tel), H = 3600e3;
  var hora = Number(Utilities.formatDate(new Date(), 'GMT-3', 'H'));
  var ctx = {
    tasas: tasasIntake_(), hora: hora,
    yaSaludo: ahora - (est.ultSaludo || 0) < 6 * H || ahora - (est.ultJohn || 0) < 2 * H,
    enProceso: ahora - (est.enProceso || 0) < 12 * H,
    fotoPendiente: ahora - (est.foto || 0) < 3 * H
  };
  var r = respuestaIntake_(texto, media, ctx);
  if (media && !ctx.enProceso) { est.foto = ahora; guardarEstadoChat_(tel, est); }
  hojaIntake_().appendRow([fecha || new Date(), tel, nombre, 'cliente', texto, !!media, r.intenciones.join(' '),
                           r.mensajes.join(' | '), r.tipos.join(' '), r.manual ? (r.motivo || 'sí') : '']);
  // ¿ya contestaste vos (algo más que un saludo) mientras la tanda esperaba? entonces no hace falta borrador
  var yaContestaste = (est.ultRespuesta || 0) > new Date(fecha || 0).getTime();
  var vieja = fecha && ahora - new Date(fecha).getTime() > INTAKE_BORRADOR_MAX_MIN * 60e3;
  if (modo === 'borrador' && !yaContestaste && !vieja && r.tipos.some(function (t) { return INTAKE_TIPOS_BORRADOR.indexOf(t) !== -1; })) {
    avisarBorradorIntake_(tel, nombre, texto, r);
  } else if (modo === 'borrador' && !yaContestaste && !vieja && r.manual && r.motivo !== 'difusión' && preguntaIntake_(texto)) {
    avisarRevisarIntake_(nombre, texto, r);   // red de seguridad: pregunta que el sistema no sabe contestar
  }
  return r;
}

/** Texto del cliente para ntfy, sin datos completos: los números largos quedan tapados. */
function textoCortoIntake_(t) {
  var s = String(t || '').replace(/\[mensaje sin texto\]/gi, '📷').replace(/\s*\n\s*/g, ' / ')
    .replace(/\d[\d\s.\-]{5,}\d/g, '•••');
  return s.length > 140 ? s.slice(0, 139) + '…' : s;
}

function urlIntake_(accion, id) {
  var base = PropertiesService.getScriptProperties().getProperty('WEBAPP_URL') || ScriptApp.getService().getUrl();
  return base + '?intake=' + accion + '&id=' + encodeURIComponent(id) + '&k=' + claveNext_();
}

/** ¿El cliente pregunta algo? (para avisarte aunque el sistema no sepa contestarlo) */
function preguntaIntake_(texto) {
  return /\?|cuant|me dices|me decis|me puedes|me podes|me podrias|se puede|puedo |podes|puedes|sabes si|consulta/.test(normIntake_(texto));
}

/** Aviso sin botón: el cliente preguntó algo que va a mano (cálculo raro, otra ruta, incidente…). */
function avisarRevisarIntake_(nombre, texto, r) {
  return avisarNtfy_(nombreTarjeta_(nombre) + ' pregunta algo · revisar',
                     textoCortoIntake_(texto) + '\n→ a mano: ' + (r.motivo || 'no sé contestarlo') +
                     (r.mensajes.length ? '\n→ ' + r.mensajes.join('\n→ ') : ''),
                     { prioridad: 3, tags: ['question'] });
}

function avisarBorradorIntake_(tel, nombre, texto, r) {
  var id = 'IK' + Date.now().toString(36) + Math.floor(Math.random() * 1e4).toString(36);
  CacheService.getScriptCache().put('iksug_' + id, JSON.stringify({ tel: tel, nombre: nombre, mensajes: r.mensajes, tipos: r.tipos }),
                                    INTAKE_SUGERENCIA_SEG);
  return avisarNtfy_(nombreTarjeta_(nombre) + (r.manual ? ' · revisar' : ''),
                     textoCortoIntake_(texto) + '\n→ ' + r.mensajes.join('\n→ '),
                     { prioridad: 3, tags: ['speech_balloon'],
                       acciones: [{ action: 'http', label: '📤 Enviar', url: urlIntake_('enviar', id), method: 'GET', clear: true }] });
}

/** Botón "📤 Enviar": manda los mensajes sugeridos por WhatsApp. Un solo uso. */
function enviarSugerenciaIntake_(id) {
  var cache = CacheService.getScriptCache(), k = 'iksug_' + id, s = cache.get(k);
  if (!s) return 'vencida o ya enviada';
  cache.remove(k);
  var sug = JSON.parse(s);
  sug.mensajes.forEach(function (m, i) { if (i) Utilities.sleep(700); sendWhatsAppMessage_(sug.tel, m); });
  var est = estadoChat_(sug.tel);
  est.ultJohn = est.ultRespuesta = Date.now();
  if (sug.tipos.indexOf('saludo') !== -1) est.ultSaludo = est.ultJohn;
  guardarEstadoChat_(sug.tel, est);
  return 'enviado';
}

/** Botón "💬 Ok fino" de la tarjeta del comprobante. id = ID de Movimientos. No se repite en la misma operación.
 *  pedirCuenta: botón "💬 Pedir cuenta" (sin datos en la Agenda): además manda "Confírmame a qué cuenta", una vez. */
function okFinoIntake_(id, pedirCuenta) {
  var f = filaPorId_(hojaMovimientos_(), id);
  if (!f) return 'no encontrado';
  var tel = String(f.datos[C.TELEFONO - 1] || '').replace(/\D/g, '');
  if (!tel) return 'sin teléfono';
  var est = estadoChat_(tel), ahora = Date.now(), dicho = ahora - (est.enProceso || 0) < 12 * 3600e3;
  var pedir = pedirCuenta && !(ahora - (est.pidioCuenta || 0) < 12 * 3600e3);
  if (dicho && !pedir) return 'ya estaba dicho';
  if (!dicho) sendWhatsAppMessage_(tel, FRASES_JOHN.en_proceso);
  if (pedir) { if (!dicho) Utilities.sleep(700); sendWhatsAppMessage_(tel, FRASES_JOHN.confirma_cuenta); est.pidioCuenta = ahora; }
  if (!dicho) { est.enProceso = ahora; est.foto = 0; }
  est.ultJohn = est.ultRespuesta = ahora;
  guardarEstadoChat_(tel, est);
  return 'enviado';
}

/** Ruta del doGet (9_P2P): ?intake=enviar|okfino&id=…&k=… */
function rutaIntake_(p) {
  var id = String(p.id || '');
  var r = p.intake === 'enviar' ? enviarSugerenciaIntake_(id)
        : p.intake === 'okfino' ? okFinoIntake_(id, false)
        : p.intake === 'cuenta' ? okFinoIntake_(id, true) : 'acción desconocida';
  return ContentService.createTextOutput(r);
}

// ---------- cuánto acierta (hoja Intake) ----------
var INTAKE_TIPOS_MEDIDOS = ['saludo', 'disponible', 'tasa', 'calculo', 'alias', 'en_proceso'];

/**
 * Compara lo sugerido para cada tanda del cliente con lo que contestaste vos en los 30 min siguientes (filas "vos"),
 * igual que la repetición de pruebas. filas = la hoja Intake (con encabezado). Devuelve los números.
 */
function medirIntake_(filas, dias, ahora) {
  ahora = ahora || Date.now();
  var desde = ahora - dias * 86400e3, r = { tandas: 0, vos: 0, aMano: {}, sinRespuesta: 0, tipos: {} };
  INTAKE_TIPOS_MEDIDOS.forEach(function (t) { r.tipos[t] = { ok: 0, falto: 0, sobro: 0 }; });
  var fecha = function (v) { return v instanceof Date ? v.getTime() : fechaIntake_(v); };
  var datos = filas.slice(1).filter(function (f) { return fecha(f[0]) >= desde; });
  datos.forEach(function (f, i) {
    if (f[3] === 'vos') { r.vos++; return; }
    if (f[3] !== 'cliente') return;
    r.tandas++;
    if (f[9]) r.aMano[f[9]] = (r.aMano[f[9]] || 0) + 1;
    var t0 = fecha(f[0]), tuyos = {}, hubo = false;
    for (var j = i + 1; j < datos.length; j++) {
      var g = datos[j];
      if (String(g[1]) !== String(f[1])) continue;
      if (fecha(g[0]) - t0 > 30 * 60e3) break;
      if (g[3] === 'cliente') break;                 // el cliente volvió a escribir: lo que sigue es otra tanda
      if (g[3] === 'vos') { hubo = true; tuyos[g[8]] = true; }
    }
    if (!hubo) { r.sinRespuesta++; return; }        // sin tu respuesta registrada no se puede comparar
    var sug = String(f[8] || '').split(' ');
    INTAKE_TIPOS_MEDIDOS.forEach(function (t) {
      var s = sug.indexOf(t) !== -1, v = !!tuyos[t];
      if (s && v) r.tipos[t].ok++; else if (v) r.tipos[t].falto++; else if (s) r.tipos[t].sobro++;
    });
  });
  return r;
}

/** "26/11/2026 14:39:03" (como lo muestra la hoja) → ms. */
function fechaIntake_(v) {
  var m = String(v).match(/(\d{1,2})\/(\d{1,2})\/(\d{4})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?/);
  if (!m) { var d = new Date(v).getTime(); return isNaN(d) ? 0 : d; }
  return new Date(+m[3], +m[2] - 1, +m[1], +m[4], +m[5], +(m[6] || 0)).getTime();
}

function textoMedicionIntake_(r, dias) {
  var l = [r.tandas + ' tandas de clientes en ' + dias + ' días · ' + r.vos + ' mensajes tuyos registrados'];
  if (!r.vos) l.push('⚠️ No llegan tus mensajes: sin eso no se puede medir (vps/webhook_tus_mensajes.py aplicar).');
  else {
    l.push('Respuesta · acierta / faltó / sobró:');
    INTAKE_TIPOS_MEDIDOS.forEach(function (t) {
      var e = r.tipos[t];
      if (e.ok + e.falto + e.sobro) l.push('  ' + t + ': ' + e.ok + ' / ' + e.falto + ' / ' + e.sobro);
    });
    if (r.sinRespuesta) l.push(r.sinRespuesta + ' tandas sin respuesta tuya en 30 min (no cuentan)');
  }
  var m = Object.keys(r.aMano);
  if (m.length) l.push('A mano: ' + m.map(function (k) { return k + ' ' + r.aMano[k]; }).join(' · '));
  return l.join('\n');
}

/** Para el editor (o un activador semanal): manda a ntfy cómo viene el intake en los últimos 7 días. */
function resumenIntake() {
  var dias = 7, r = medirIntake_(hojaIntake_().getDataRange().getValues(), dias);
  var texto = textoMedicionIntake_(r, dias);
  Logger.log(texto);
  avisarNtfy_('Intake · últimos ' + dias + ' días', texto, { prioridad: 2, tags: ['bar_chart'] });
  return texto;
}
