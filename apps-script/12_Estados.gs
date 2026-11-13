// ==========================================
// MÓDULO 12: ESTADOS DE WHATSAPP AUTOMÁTICOS
// ==========================================
/* Publica UN estado por día desde WAHA, visible solo para los contactos del
   Directorio cuyo nombre empieza con "Bexo".
   - Si hay imágenes en la carpeta de Drive ESTADOS_CARPETA, publica la que sigue por nombre (D01, D03…)
     y, con ESTADO_ROTAR, al terminar vuelve a empezar
     (caption = descripción del archivo en Drive, si tiene); sin ESTADO_ROTAR la mueve a "Publicados".
   - Si la carpeta está vacía, publica el saludo de texto ESTADO_SALUDO.
   Usa WAHA_URL y WAHA_API_KEY de 3_Operativa.gs. No toca nada de lo que ya anda.

   OJO: si a WAHA le llega un estado SIN lista de contactos, lo manda a TODOS los
   contactos. Por eso acá, si la lista queda vacía, no se publica nada. */

var ESTADOS_SESSION   = 'default';
var ESTADOS_CARPETA   = 'Estados_WZP';           // la llena el otro flujo
var ESTADOS_PUBLICADOS = 'Publicados';           // subcarpeta adentro de la anterior
var ESTADO_PREFIJO    = 'bexo';                  // nombre del Directorio que EMPIECE con esto
var ESTADO_SALUDO     = '¡Buen día! 👋 Gracias por confiar en Bexo.';
var ESTADO_COLOR      = '#1f6f43';
var ESTADO_HORA       = 9;                       // hora del trigger diario (zona del script)
var ESTADO_CADA_DIAS  = 2;                       // 1 = todos los días, 2 = día por medio
var ESTADO_ROTAR      = true;                    // true = las imágenes quedan y se repiten en ronda (D01…D31, D01…)
var ESTADO_LOTE       = 250;                     // contactos por llamada a WAHA
var ESTADO_PARALELO   = 5;                       // consultas simultáneas a check-exists
var ESTADO_TEST_TEL   = CONFIG.ESTADO_TEST_TEL; // a quién va la prueba (propiedad del script, ver 0_Config.gs)
var ESTADO_PROPIO     = CONFIG.MI_TELEFONO;      // tu número: va siempre en la lista, si no el estado no aparece en "Mis estados"
var ESTADO_TIPOS_OK   = ['image/jpeg', 'image/png', 'image/webp'];

// --- Lo que corre el trigger diario ---
function publicarEstadoDiario() {
  var props = PropertiesService.getScriptProperties();
  var hoy = Utilities.formatDate(new Date(), 'GMT-3', 'yyyy-MM-dd');
  if (props.getProperty('ESTADO_ULTIMO_DIA') === hoy) return;   // ya hubo estado hoy

  try {
    var contactos = audienciaBexo_();
    if (contactos.length === 0) { logError_('ESTADO', 'Audiencia vacía: no se publica'); return; }
    if (publicarEstado_(contactos)) props.setProperty('ESTADO_ULTIMO_DIA', hoy);
  } catch (e) {
    logError_('ESTADO', e.message);
  }
}

// --- Prueba: manda el estado (imagen si hay, si no el saludo) SOLO a ESTADO_TEST_TEL ---
function probarEstadoConUnContacto() {
  var jids = resolverJids_([ESTADO_TEST_TEL]);
  Logger.log('Contacto de prueba: ' + JSON.stringify(jids));
  if (jids.length === 0) { Logger.log('Ese número no tiene WhatsApp según WAHA'); return; }
  publicarEstado_(jids, true);
}

// --- Para mirar a quién le llegaría, sin publicar nada ---
function verAudienciaEstados() {
  var jids = audienciaBexo_();
  Logger.log(jids.length + ' contactos Bexo con WhatsApp');
  Logger.log(jids.slice(0, 20).join('\n'));
}

// --- Diagnóstico: trigger, último estado y si un número está en la audiencia ---
// Para revisar otro número, cambiá ESTADO_TEST_TEL antes de ejecutarla.
function diagnosticoEstados() {
  var props = PropertiesService.getScriptProperties();
  var trig = ScriptApp.getProjectTriggers().filter(function (t) {
    return t.getHandlerFunction() === 'publicarEstadoDiario';
  });
  Logger.log('Trigger publicarEstadoDiario: ' + (trig.length ? 'instalado' : 'NO instalado'));
  Logger.log('Último día publicado: ' + props.getProperty('ESTADO_ULTIMO_DIA'));
  Logger.log('Última imagen: ' + props.getProperty('ESTADO_ULTIMA_IMAGEN'));
  Logger.log('Último id: ' + props.getProperty('ESTADO_ULTIMO_ID'));
  var lista = JSON.parse(props.getProperty('ESTADO_ULTIMO_CONTACTOS') || '[]');
  Logger.log('Contactos del último estado: ' + lista.length);
  var jid = resolverJids_([ESTADO_TEST_TEL])[0];
  Logger.log(ESTADO_TEST_TEL + ' → ' + jid + (lista.indexOf(jid) !== -1 ? ' ESTÁ' : ' NO está') + ' en el último estado');
}

// --- Borra el último estado publicado (sirve para deshacer una prueba) ---
function borrarUltimoEstado() {
  var props = PropertiesService.getScriptProperties();
  var id = props.getProperty('ESTADO_ULTIMO_ID');
  var lista = JSON.parse(props.getProperty('ESTADO_ULTIMO_CONTACTOS') || '[]');
  if (!id) { Logger.log('No hay estado guardado para borrar'); return; }
  for (var i = 0; i < lista.length; i += ESTADO_LOTE) {
    var r = wahaEstado_('delete', { id: id, contacts: lista.slice(i, i + ESTADO_LOTE) });
    Logger.log('delete ' + r.getResponseCode() + ' ' + r.getContentText().substring(0, 200));
  }
}

function instalarTriggerEstados() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'publicarEstadoDiario') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('publicarEstadoDiario').timeBased().everyDays(ESTADO_CADA_DIAS).atHour(ESTADO_HORA).create();
  Logger.log('Trigger instalado: publicarEstadoDiario cada ' + ESTADO_CADA_DIAS + ' día(s) ~' + ESTADO_HORA + ' h');
}

function quitarTriggerEstados() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'publicarEstadoDiario') ScriptApp.deleteTrigger(t);
  });
  Logger.log('Trigger de estados quitado');
}

// ==========================================
// INTERNOS
// ==========================================

// Elige qué publicar y lo manda en lotes con el mismo id. Devuelve true si salió.
function publicarEstado_(contactos, esPrueba) {
  var archivo = siguienteImagen_();
  var cuerpo;
  if (archivo) {
    var blob = archivo.getBlob();
    cuerpo = {
      file: {
        mimetype: blob.getContentType(),
        filename: archivo.getName(),
        data: Utilities.base64Encode(blob.getBytes())
      },
    };
    if (archivo.getDescription()) cuerpo.caption = archivo.getDescription();
  } else {
    cuerpo = { text: ESTADO_SALUDO, backgroundColor: ESTADO_COLOR, font: 0 };
  }

  // Un id para todos los lotes: así es UN estado, y después se puede borrar
  var rId = wahaGet_('/api/' + ESTADOS_SESSION + '/status/new-message-id');
  var id = rId.getResponseCode() === 200 ? JSON.parse(rId.getContentText()).id : null;
  if (id) cuerpo.id = id;
  else if (contactos.length > ESTADO_LOTE) {
    logError_('ESTADO', 'Sin new-message-id (' + rId.getResponseCode() + ') y hacen falta varios lotes');
    return false;
  }

  var tipo = archivo ? 'image' : 'text';
  for (var i = 0; i < contactos.length; i += ESTADO_LOTE) {
    cuerpo.contacts = contactos.slice(i, i + ESTADO_LOTE);
    var r = wahaEstado_(tipo, cuerpo);
    Logger.log('Lote ' + (i / ESTADO_LOTE + 1) + ': ' + r.getResponseCode() + ' ' + r.getContentText().substring(0, 300));
    if (r.getResponseCode() >= 300) {
      logError_('ESTADO_' + tipo.toUpperCase(), r.getResponseCode() + ' | ' + r.getContentText());
      return false;
    }
  }

  var props = PropertiesService.getScriptProperties();
  if (id) props.setProperty('ESTADO_ULTIMO_ID', id);
  props.setProperty('ESTADO_ULTIMO_CONTACTOS', JSON.stringify(contactos));
  Logger.log('Estado ' + tipo + ' publicado a ' + contactos.length + ' contactos (id ' + id + ')');

  // En la prueba no se avanza: la imagen la publica igual el diario
  if (archivo && !esPrueba) {
    if (ESTADO_ROTAR) props.setProperty('ESTADO_ULTIMA_IMAGEN', archivo.getName());
    else archivo.moveTo(carpetaPublicados_());
  }
  return true;
}

// Orden por nombre (D01, D03…). Rotando: la que sigue a la última publicada, y al
// terminar vuelve a la primera. Sin rotar: la primera (las de "Publicados" no cuentan).
function siguienteImagen_() {
  var it = carpetaEstados_().getFiles();
  var lista = [];
  while (it.hasNext()) {
    var f = it.next();
    if (ESTADO_TIPOS_OK.indexOf(f.getMimeType()) !== -1) lista.push(f);
  }
  if (lista.length === 0) return null;
  lista.sort(function (a, b) { return a.getName() < b.getName() ? -1 : 1; });
  if (!ESTADO_ROTAR) return lista[0];

  var ultima = PropertiesService.getScriptProperties().getProperty('ESTADO_ULTIMA_IMAGEN') || '';
  for (var i = 0; i < lista.length; i++) {
    if (lista[i].getName() > ultima) return lista[i];
  }
  return lista[0];   // se terminó la vuelta
}

function carpetaEstados_() {
  var it = DriveApp.getFoldersByName(ESTADOS_CARPETA);
  return it.hasNext() ? it.next() : DriveApp.createFolder(ESTADOS_CARPETA);
}

function carpetaPublicados_() {
  var padre = carpetaEstados_();
  var it = padre.getFoldersByName(ESTADOS_PUBLICADOS);
  return it.hasNext() ? it.next() : padre.createFolder(ESTADOS_PUBLICADOS);
}

// Teléfonos del Directorio con nombre "Bexo..." → chatIds reales de WhatsApp
function audienciaBexo_() {
  var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(DIR_SHEET);
  if (!sh) return [];
  var datos = sh.getDataRange().getValues();
  var tels = {};
  for (var i = 1; i < datos.length; i++) {
    var nombre = String(datos[i][1]).trim().toLowerCase();
    var tel = String(datos[i][0]).replace(/\D/g, '');
    if (nombre.indexOf(ESTADO_PREFIJO) === 0 && tel.length >= 8) tels[tel] = true;
  }
  tels[ESTADO_PROPIO] = true;
  return resolverJids_(Object.keys(tels));
}

// Le pregunta a WAHA el chatId de cada número, de a pocos para no saturarlo.
// "No existe" y "WAHA falló" se separan: lo que falla se reintenta una vez, de a uno.
function resolverJids_(tels) {
  var jids = {}, sinWa = [], fallidos = [], primerError = '';
  var pedido = function (t) {
    return {
      url: WAHA_URL + '/api/contacts/check-exists?session=' + ESTADOS_SESSION + '&phone=' + normalizarTel_(t),
      headers: { 'X-Api-Key': WAHA_API_KEY },
      muteHttpExceptions: true
    };
  };
  var leer = function (t, r, siFalla) {
    if (r.getResponseCode() !== 200) {
      if (!primerError) primerError = r.getResponseCode() + ' ' + r.getContentText().substring(0, 200);
      siFalla.push(t);
      return;
    }
    var j = JSON.parse(r.getContentText());
    // Con GOWS, check-exists devuelve el chatId como "…@lid" y el estado no llega: se usa siempre el número (@c.us), como con NOWEB
    if (j.numberExists && j.chatId) jids[String(j.chatId).indexOf('@lid') === -1 ? j.chatId : normalizarTel_(t) + '@c.us'] = true;
    else sinWa.push(t);
  };

  for (var i = 0; i < tels.length; i += ESTADO_PARALELO) {
    var tanda = tels.slice(i, i + ESTADO_PARALELO);
    UrlFetchApp.fetchAll(tanda.map(pedido)).forEach(function (r, k) { leer(tanda[k], r, fallidos); });
  }
  var siguenFallando = [];
  fallidos.forEach(function (t) {
    Utilities.sleep(500);
    leer(t, UrlFetchApp.fetch(pedido(t).url, pedido(t)), siguenFallando);
  });

  Logger.log(Object.keys(jids).length + ' con WhatsApp, ' + sinWa.length + ' sin WhatsApp, ' + siguenFallando.length + ' con error de WAHA');
  // Solo se anota cuando la cantidad cambia: si siempre son los mismos, no ensucia Debug_Errores
  var props = PropertiesService.getScriptProperties();
  if (sinWa.length && String(sinWa.length) !== props.getProperty('ESTADO_SIN_WA_CANT')) {
    logError_('ESTADO_SIN_WA', sinWa.length + ' números: ' + sinWa.slice(0, 30).join(', '));
  }
  if (tels.length > 1) props.setProperty('ESTADO_SIN_WA_CANT', String(sinWa.length));
  if (siguenFallando.length) logError_('ESTADO_ERROR_WAHA', siguenFallando.length + ' números | ' + primerError + ' | ' + siguenFallando.slice(0, 30).join(', '));
  return Object.keys(jids);
}

// Números argentinos cargados sin código de país (10 dígitos) o sin el 9 de celular
function normalizarTel_(t) {
  if (t.length === 10) return '549' + t;
  if (t.indexOf('54') === 0 && t.indexOf('549') !== 0 && t.length === 12) return '549' + t.substring(2);
  return t;
}

function wahaEstado_(tipo, cuerpo) {
  return UrlFetchApp.fetch(WAHA_URL + '/api/' + ESTADOS_SESSION + '/status/' + tipo, {
    method: 'post',
    contentType: 'application/json',
    headers: { 'X-Api-Key': WAHA_API_KEY },
    payload: JSON.stringify(cuerpo),
    muteHttpExceptions: true
  });
}

function wahaGet_(ruta) {
  return UrlFetchApp.fetch(WAHA_URL + ruta, {
    headers: { 'X-Api-Key': WAHA_API_KEY },
    muteHttpExceptions: true
  });
}
