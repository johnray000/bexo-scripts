// ==========================================
// MÓDULO 23: INTAKE EN VIVO — registra cada tanda y te propone la respuesta en ntfy
//
// - processBuffer (3_Operativa) llama a registrarTandaIntake_ cuando se cierra una tanda del cliente
//   (60 s sin mensajes nuevos). doPost (2_Recepcion) llama a registrarMensajeTuyo_ con cada mensaje tuyo.
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
  if (tipo === 'cierre') est.enProceso = 0;
  guardarEstadoChat_(tel, est);
  hojaIntake_().appendRow([new Date(), tel, nombre, 'vos', texto || (media ? '[foto]' : ''), media, '', '', tipo, '']);
}

/** processBuffer → una tanda del cliente que se cerró. */
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
  if (modo === 'borrador' && !yaContestaste && r.tipos.some(function (t) { return INTAKE_TIPOS_BORRADOR.indexOf(t) !== -1; })) {
    avisarBorradorIntake_(tel, nombre, texto, r);
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

/** Botón "💬 Ok fino" de la tarjeta del comprobante. id = ID de Movimientos. No se repite en la misma operación. */
function okFinoIntake_(id) {
  var f = filaPorId_(hojaMovimientos_(), id);
  if (!f) return 'no encontrado';
  var tel = String(f.datos[C.TELEFONO - 1] || '').replace(/\D/g, '');
  if (!tel) return 'sin teléfono';
  var est = estadoChat_(tel);
  if (Date.now() - (est.enProceso || 0) < 12 * 3600e3) return 'ya estaba dicho';
  sendWhatsAppMessage_(tel, FRASES_JOHN.en_proceso);
  est.enProceso = est.ultJohn = Date.now(); est.foto = 0;
  guardarEstadoChat_(tel, est);
  return 'enviado';
}

/** Ruta del doGet (9_P2P): ?intake=enviar|okfino&id=…&k=… */
function rutaIntake_(p) {
  var id = String(p.id || '');
  var r = p.intake === 'enviar' ? enviarSugerenciaIntake_(id) : (p.intake === 'okfino' ? okFinoIntake_(id) : 'acción desconocida');
  return ContentService.createTextOutput(r);
}
