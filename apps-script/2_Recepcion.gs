// ==========================================
// MÓDULO 2: TÚNEL DE ENTRADA Y BUFFER
// ==========================================
/*Cuando entra un mensaje, busca el número en tu Directorio. Si te encuentra, te pone la etiqueta Es_Cliente = TRUE. Si no te encuentra, entras como FALSE. Esta pequeña bandera booleana es la que usará el barrendero más adelante para decidir si dispara la auto-respuesta o si se queda callado*/

var BUFFER_SHEET = 'Buffer';
var WINDOW_SEC = 60;

function doPost(e) {
  try {
        //volcarCrudo_(e);   // ← SOLO ESTA LÍNEA

    const ss = SpreadsheetApp.getActiveSpreadsheet();
    let sh = ss.getSheetByName(BUFFER_SHEET);

    if (!sh) {
      sh = ss.insertSheet(BUFFER_SHEET);
      sh.appendRow(['Teléfono', 'Nombre', 'Mensajes Acumulados', 'Última Actividad', 'Intención', 'Prioridad', 'Tiene_Imagen', 'Es_Cliente', 'Drive_ID']);
      sh.getRange("A1:I1").setFontWeight("bold");
    }

    const data = JSON.parse(e.postData.contents);
    if (data.diagnostico) return diagnosticoPlanilla_(data);
    if (data.movimientosUY) return recibirMovimientosUY_(data);
    if (data.ordenesP2P) return recibirOrdenesP2P_(data);
    if (data.ordenesOKX) return recibirOrdenesOKX_(data);
    const payload = data.payload || {};
    const _data = payload._data || {};
    const key = _data.key || {};

    let rawFrom = payload.from || "";
    let altFrom = (key.remoteJid && key.remoteJid.includes('@s.whatsapp.net')) ? key.remoteJid : (key.remoteJidAlt || "");

   // --- FIREWALL ANTI-BASURA ---
    if (e.postData.contents.includes("status@broadcast") || rawFrom.includes('@g.us') || altFrom.includes('@g.us')) {
    return ContentService.createTextOutput(JSON.stringify({status: "ignorado"})).setMimeType(ContentService.MimeType.JSON);
    }
    if (payload.fromMe === true || key.fromMe === true) {
    return ContentService.createTextOutput(JSON.stringify({status: "ignorado_saliente"})).setMimeType(ContentService.MimeType.JSON);
    }

    // --- LIMPIEZA DE TELÉFONO ---
    let phone = telefonoRemitente_(payload);

    if (!phone) {
    return ContentService.createTextOutput(JSON.stringify({status: "ignorado_sin_telefono"})).setMimeType(ContentService.MimeType.JSON);
    }

    // Comando NEXT tuyo para la orden P2P (9_P2P.gs)
    if (phone === MI_TELEFONO && /^\s*next\b/i.test(payload.body || '')) {
      manejarNextP2P_(payload.body);
      return ContentService.createTextOutput(JSON.stringify({status: "next_p2p"})).setMimeType(ContentService.MimeType.JSON);
    }

    let name = _data.pushName || (_data.Info && _data.Info.PushName) || 'Sin Nombre';
    // ==========================================
    // --- BLACKLIST (BLOQUEO DE SPAM/INTAKE) ---
    // ==========================================
    // RECOMENDACIÓN: Pon su número real aquí. Es la única forma infalible.
    const BLACKLIST_PHONES = listaConfig_('BLACKLIST_TELEFONOS'); // propiedad del script, ver 0_Config.gs
    const BLACKLIST_NAMES = ['bexo gudy']; 

    if (BLACKLIST_PHONES.includes(phone) || BLACKLIST_NAMES.some(bName => name.toLowerCase().includes(bName))) {
    return ContentService.createTextOutput(JSON.stringify({status: "ignorado_blacklist"})).setMimeType(ContentService.MimeType.JSON);
    }

  
    const message  = payload.body || '[Mensaje sin texto]';
    const hasMedia = payload.hasMedia === true;
    let   isClient = false;

    // Bajamos la imagen YA, antes de que WAHA la borre
    let driveId = null;
    if (hasMedia && payload.media && payload.media.url) {
      driveId = guardarEnDrive_(payload.media.url, phone, payload.media.mimetype);
      
    }
  

    // --- BÚSQUEDA EN DIRECTORIO (El Portero Blindado) ---
    let dirSh = ss.getSheetByName(DIR_SHEET);
    if (dirSh) {
      const dirData = dirSh.getDataRange().getValues();
      for (let i = 1; i < dirData.length; i++) {
        let dirPhone = String(dirData[i][0]).replace(/\D/g, '');
        let wahaPhone = String(phone).replace(/\D/g, '');
        
        // Exigimos mínimo 8 dígitos para comparar de forma segura
        if (dirPhone.length >= 8 && wahaPhone.length >= 8) {
          // Extrae y compara solo los últimos 8 dígitos (Ignora el 54 vs 549)
          if (dirPhone.slice(-8) === wahaPhone.slice(-8)) {
            name = dirData[i][1]; // Sobrescribe con nombre CRM
            isClient = true;      // Autoriza auto-respuesta
            break;
          }
        }
      }
    }

    // Solo clientes del Directorio. Si no lo es, la imagen se va a la papelera.
    if (driveId && isClient) { encolarMovimiento_(phone, name, driveId); agendarLecturaRapida_(); }
    
    else if (driveId) {
      try { DriveApp.getFileById(driveId).setTrashed(true); } catch (e) { logError_('NO_CLIENTE', e.message); }
      driveId = null;
    }

    if (isClient) registrarDatosPago_(name, message);   // datos de pago a la Agenda (10_AgendaCuentas.gs)

    // --- LÓGICA DE BUFFER Y AGRUPACIÓN ---
    const dataRange = sh.getDataRange().getValues();
    const now = new Date();
    let rowIndex = -1;

    for (let r = dataRange.length - 1; r > 0; r--) {
      if (String(dataRange[r][0]) === String(phone)) {
        rowIndex = r + 1;
        break;
      }
    }

    if (rowIndex !== -1) {
      const lastUpdate = new Date(sh.getRange(rowIndex, 4).getValue());
      const diffSec = (now.getTime() - lastUpdate.getTime()) / 1000;

      if (diffSec <= WINDOW_SEC) {
        const currentText = sh.getRange(rowIndex, 3).getValue();
        const currentMediaStatus = sh.getRange(rowIndex, 7).getValue();
        
        const fullText = currentText + "\n" + message;
        const groupHasMedia = currentMediaStatus === true || hasMedia;
        
        const triage = classifyMessage_(fullText, groupHasMedia);

        sh.getRange(rowIndex, 3).setValue(fullText);
        sh.getRange(rowIndex, 4).setValue(now);
        sh.getRange(rowIndex, 5).setValue(triage.intent);
        sh.getRange(rowIndex, 6).setValue(triage.priority);
        sh.getRange(rowIndex, 7).setValue(groupHasMedia);

        if (driveId) {
          const prev = sh.getRange(rowIndex, 9).getValue();
          sh.getRange(rowIndex, 9).setValue(prev ? prev + ',' + driveId : driveId);
        }

        
        return ContentService.createTextOutput(JSON.stringify({status: "concatenado"})).setMimeType(ContentService.MimeType.JSON);
      }
    }

    const triage = classifyMessage_(message, hasMedia);
    sh.appendRow([phone, name, message, now, triage.intent, triage.priority, hasMedia, isClient, driveId]);

    return ContentService.createTextOutput(JSON.stringify({status: "nueva_fila"})).setMimeType(ContentService.MimeType.JSON);

  } catch (error) {
    return ContentService.createTextOutput(JSON.stringify({error: error.message})).setMimeType(ContentService.MimeType.JSON);
  }
  /*
  function volcarCrudo_(e) {
    try {
    if (e.postData.contents.includes('status@broadcast')) return; 
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    let sh = ss.getSheetByName('Debug_Raw');
    if (!sh) {
      sh = ss.insertSheet('Debug_Raw');
      sh.appendRow(['Fecha', 'Payload']);
    }
    // Truncado a 45k: una celda aguanta 50k caracteres
    sh.appendRow([new Date(), e.postData.contents.substring(0, 45000)]);
  } catch (err) {}
  }*/
}

var CARPETA_COMPROBANTES = 'Comprobantes_WZP';

function logError_(etapa, detalle) {
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    let sh = ss.getSheetByName('Debug_Errores');
    if (!sh) { sh = ss.insertSheet('Debug_Errores'); sh.appendRow(['Fecha','Etapa','Detalle']); }
    sh.appendRow([new Date(), etapa, String(detalle).substring(0, 5000)]);
  } catch (e) {}
}

function guardarEnDrive_(mediaUrl, phone, mimetype) {
  try {
    // Solo imagenes y PDF. Nada de audios, videos ni stickers.
    var PERMITIDOS = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf'];
    if (!mimetype) return null;
    var mt = mimetype.split(';')[0].trim().toLowerCase();
    if (PERMITIDOS.indexOf(mt) === -1) return null;

    const res = UrlFetchApp.fetch(mediaUrl, {
      headers: { 'X-Api-Key': WAHA_API_KEY },
      muteHttpExceptions: true
    });

    if (res.getResponseCode() !== 200) {
      logError_('FETCH_FAIL', res.getResponseCode() + ' | ' + mediaUrl);
      return null;
    }

    const it = DriveApp.getFoldersByName(CARPETA_COMPROBANTES);
    const folder = it.hasNext() ? it.next() : DriveApp.createFolder(CARPETA_COMPROBANTES);

    const ext = (mt === 'application/pdf') ? 'pdf' : mt.split('/')[1];
    const nombre = phone + '_' + Utilities.formatDate(new Date(), 'GMT-3', 'yyyyMMdd_HHmmss') + '.' + ext;
    return folder.createFile(res.getBlob().setName(nombre)).getId();

  } catch (err) {
    logError_('EXCEPCION', err.message);
    return null;
  }
}

function test4_permisos() {
  const it = DriveApp.getFoldersByName(CARPETA_COMPROBANTES);
  const folder = it.hasNext() ? it.next() : DriveApp.createFolder(CARPETA_COMPROBANTES);
  Logger.log('Carpeta OK: ' + folder.getId());
}

function limpiarDebug() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  ['Debug_Errores', 'Debug_Raw'].forEach(function (n) {
    const sh = ss.getSheetByName(n);
    if (sh && sh.getLastRow() > 1) sh.deleteRows(2, sh.getLastRow() - 1);
  });
}