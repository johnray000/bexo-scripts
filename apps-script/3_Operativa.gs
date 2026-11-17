// ==========================================
// MÓDULO 3: OPERATIVA (TRIAJE, RESPUESTA Y CIERRE)dop
// ==========================================

var INBOX_SHEET = 'Bandeja_Entrada';
var WAHA_URL = CONFIG.WAHA_URL;          // 0_Config.gs
var WAHA_API_KEY = CONFIG.WAHA_API_KEY;  // 0_Config.gs

// --- BARRENDERO CON AUTORESPUESTA, ENRUTADOR Y KILL SWITCH ---
function processBuffer() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const bufferSh = ss.getSheetByName(BUFFER_SHEET); // Viene de 2_Recepcion.gs
  let inboxSh = ss.getSheetByName(INBOX_SHEET);

  if (!inboxSh) {
    inboxSh = ss.insertSheet(INBOX_SHEET);
    inboxSh.appendRow(['Estado', 'Fecha', 'Teléfono', 'Nombre', 'Mensaje Completo', 'Intención', 'Prioridad', 'Es_Cliente', 'Auto-Respuesta:', 'OFF']);
    inboxSh.getRange("A1:J1").setFontWeight("bold");
    inboxSh.setFrozenRows(1);
  }
  if (!bufferSh) return;

  // LECTURA DEL INTERRUPTOR EN LA CELDA J1 (AUTO / AGENT / OFF)
  const botStatusRaw = inboxSh.getRange("J1").getValue();
  const botStatus = String(botStatusRaw).toUpperCase().trim();

  const data = bufferSh.getDataRange().getValues();
  if (data.length <= 1) return;

  // Mapa de tickets activos en la Bandeja de Entrada
  const inboxData = inboxSh.getDataRange().getValues();
  const activeTickets = {};
  for (let j = 1; j < inboxData.length; j++) {
    activeTickets[String(inboxData[j][2])] = j + 1;
  }

  const now = new Date();
  const rowsToDelete = [];

  for (let i = 1; i < data.length; i++) {
    const phone = data[i][0];
    const name = data[i][1];
    const message = data[i][2];
    const lastUpdate = new Date(data[i][3]);
    const intent = data[i][4];
    const priority = data[i][5];
    const isClient = data[i][7];

    const diffSec = (now.getTime() - lastUpdate.getTime()) / 1000;

    if (diffSec > WINDOW_SEC) {
      rowsToDelete.push(i + 1);

      // EVALUAR ESTADO DE SESIÓN (Si ya existe, concatena y silencia)
      if (activeTickets[phone]) {
        const existingRow = activeTickets[phone];
        const oldMessage = inboxSh.getRange(existingRow, 5).getValue();
        
        inboxSh.getRange(existingRow, 5).setValue(oldMessage + "\n[NUEVO]: " + message);
        inboxSh.getRange(existingRow, 2).setValue(lastUpdate);
        inboxSh.getRange(existingRow, 6).setValue(intent);
        
        continue; // ABORTA AQUI, NO SALUDA NI RESPONDE.
      }

      // TICKET NUEVO: Se inserta en la Bandeja
      inboxSh.appendRow(['🔴 PENDIENTE', lastUpdate, phone, name, message, intent, priority, isClient]);
      activeTickets[phone] = inboxSh.getLastRow(); 

      // --- FRENO DE SEGURIDAD ---
      // Si el botón está en OFF o si no es un cliente VIP, aborta operaciones de salida.
      if (botStatus === "OFF" || (isClient !== true && String(isClient).toUpperCase() !== "TRUE")) continue;

      // --- 1. SALUDO INICIAL GENERAL ---
      const saludos = [
        "Hola buenos días como estas", 
        "Buenas como estás", 
        "Buen día", 
        "Hola, cómo estás?"
      ];
      const saludoElegido = saludos[Math.floor(Math.random() * saludos.length)];
      sendWhatsAppMessage_(phone, saludoElegido);

      // --- 2. ENRUTAMIENTO SEGÚN ESTADO (AGENT vs AUTO) ---
      if (botStatus === "AGENT") {
        // Enviar a OpenClaw
        sendToOpenClaw_(phone, message, intent);
      } 
      else if (botStatus === "AUTO") {
        // Lógica de respuesta estática manual
        let respuestasIntencion = [];

        if (intent === 'CONSULTA_TASA') {
          respuestasIntencion = ["Te aviso apenas la tenga"];
        } else if (intent === 'INCIDENTE') {
          respuestasIntencion = ["Ok, déjame revisar eso"];
        } else if (intent === 'COMPROBANTE') {
          respuestasIntencion = ["Ok fino te aviso apenas tenga el capture"];
        } else if (intent === 'OPERACION_ENVIO') {
          respuestasIntencion = [
            "Si tengo disponibilidad",
            "Dale",
            "puedes transferir a la misma cuenta de la ultima vez"
          ];
        }

        for (let j = 0; j < respuestasIntencion.length; j++) {
          Utilities.sleep(1500); 
          sendWhatsAppMessage_(phone, respuestasIntencion[j]);
        }
      }
    }
  }

  // Borrado de buffer y ordenamiento de bandeja
  if (rowsToDelete.length > 0) {
    bufferSh.insertRowAfter(1); // Fila de seguridad bajo el encabezado
    rowsToDelete.sort((a, b) => b - a).forEach(row => bufferSh.deleteRow(row + 1)); // +1 porque insertamos una fila arriba
  }
  
  if (inboxSh.getLastRow() > 1) {
    inboxSh.getRange(2, 1, inboxSh.getLastRow() - 1, inboxSh.getLastColumn()).sort({column: 2, ascending: false});
  }
}

// --- MOTOR DE TRIAJE 2.0 ---
function classifyMessage_(text, hasMedia) {
  let t = String(text).toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  t = t.replace(/[^\w\s]/gi, ''); 
  
  const correcciones = {
    "cotozacion": "cotizacion", "coti": "cotizacion", "taza": "tasa",
    "trasferir": "transferir", "embio": "envio", "pasa": "pasar",
    "cuanto": "cuanto", "encuanto": "cuanto", "nesesito": "necesito"
  };
  for (let error in correcciones) {
    t = t.replace(new RegExp(error, 'g'), correcciones[error]);
  }

  if (/(no llego|retenid|bloque|rebot|error|falla|estafa|fraude|problema)/.test(t)) return { intent: 'INCIDENTE', priority: 'P0' };
  if (hasMedia || /(listo|pase|captur|comprobante|recibo|transf|pago|pagad|envie|voucher|foto|imagen)/.test(t)) return { intent: 'COMPROBANTE', priority: 'P1' };
  if (/\b(para|depositar|mandar|enviar|envió|envio|envio|transferir|pasar|cuenta|cbu|cvu|alias|mismo|misma)\b/.test(t) || /\b(0102|0105|0104|0114|0424|0414|0412)\b/.test(t)) return { intent: 'OPERACION_ENVIO', priority: 'P1' };
  if (/(tasa|cotizacion|precio|cambio|cuanto|remesa|valor|bolivar|reais|dolar|peso)/.test(t)) return { intent: 'CONSULTA_TASA', priority: 'P2' };
  if (/(hola|buenas|buen dia|buen dia|como estas|saludos|gracias|fino|ok|dale)/.test(t)) return { intent: 'SALUDO', priority: 'P3' };

  return { intent: 'PREGUNTA_GENERAL', priority: 'P3' };
}

// --- TRANSMISIÓN HACIA WAHA ---
function sendWhatsAppMessage_(phone, text) {
  const payload = { "session": "default", "chatId": phone + "@c.us", "text": text };
  const options = {
    "method": "post",
    "contentType": "application/json",
    "headers": { "X-Api-Key": WAHA_API_KEY },
    "payload": JSON.stringify(payload),
    "muteHttpExceptions": true
  };
  try { UrlFetchApp.fetch(WAHA_URL + "/api/sendText", options); } catch (e) {}
}

// --- TRANSMISIÓN HACIA OPENCLAW (DIGITAL OCEAN) ---
function sendToOpenClaw_(phone, text, intent) {
  const OPENCLAW_PROXY_URL = CONFIG.OPENCLAW_URL;
  
  const payload = {
    "userId": phone,
    "message": text, // <--- EL CAMBIO CRÍTICO ESTÁ AQUÍ
    "intent": intent
  };
  
  const options = {
    "method": "post",
    "contentType": "application/json",
    "headers": { "X-Api-Key": CONFIG.OPENCLAW_KEY },
    "payload": JSON.stringify(payload),
    "muteHttpExceptions": true 
  };
  try { UrlFetchApp.fetch(OPENCLAW_PROXY_URL, options); } catch (e) {}
}

// --- LIMPIEZA AUTOMÁTICA DE SESIONES ---
function autoCloseTickets() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const inboxSh = ss.getSheetByName(INBOX_SHEET);
  let historySh = ss.getSheetByName('Historial');

  if (!inboxSh) return;
  if (!historySh) {
    historySh = ss.insertSheet('Historial');
    historySh.appendRow(['Estado', 'Fecha', 'Teléfono', 'Nombre', 'Mensaje Completo', 'Intención', 'Prioridad', 'Acción']);
    historySh.getRange("A1:H1").setFontWeight("bold");
    historySh.setFrozenRows(1);
  }

  const data = inboxSh.getDataRange().getValues();
  if (data.length <= 1) return;

  const now = new Date();
  const rowsToDelete = [];
  const HOURS_TO_CLOSE = 6;

  for (let i = data.length - 1; i > 0; i--) {
    const lastUpdate = new Date(data[i][1]);
    const diffHours = (now.getTime() - lastUpdate.getTime()) / (1000 * 60 * 60);

    if (diffHours >= HOURS_TO_CLOSE) {
      let rowData = data[i];
      rowData[0] = '✅ CERRADO (Inactividad)';
      historySh.appendRow(rowData);
      rowsToDelete.push(i + 1);
    }
  }

  if (rowsToDelete.length > 0) {
      inboxSh.insertRowAfter(1); // Fila de seguridad bajo el encabezado
      
      // Ordenar de mayor a menor y ajustar el índice por la fila insertada
      rowsToDelete.sort((a, b) => b - a).forEach(row => inboxSh.deleteRow(row + 1));
    }

  if (historySh.getLastRow() > 1) {
    historySh.getRange(2, 1, historySh.getLastRow() - 1, historySh.getLastColumn()).sort({column: 2, ascending: false});
  }
}

// --- HERRAMIENTA DE DIAGNÓSTICO HACIA OPENCLAW (DIGITAL OCEAN) ---
function testConexionProxy() {  
  const url = CONFIG.OPENCLAW_URL;
  
  const options = {
    method: "post",
    contentType: "application/json",
    headers: { "X-Api-Key": CONFIG.OPENCLAW_KEY },
    payload: JSON.stringify({ 
      "userId": "58412000000", 
      "message": "prueba de conexion",
      "intent": "TEST"
    }),
    muteHttpExceptions: true
  };
  
  try {
    const response = UrlFetchApp.fetch(url, options);
    Logger.log("ESTADO: " + response.getResponseCode());
    Logger.log("RESPUESTA: " + response.getContentText());
  } catch (e) {
    Logger.log("ERROR FATAL DE RED: " + e.message);
  }
}

// ---Genera chunks acumulativos - Crea nueva hoja:
function generarDatasetRouter_v2() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sourceSheet = ss.getSheetByName('Historial');
  if (!sourceSheet) return;

  let targetSheet = ss.getSheetByName('Dataset_Router');
  if (targetSheet) ss.deleteSheet(targetSheet);
  targetSheet = ss.insertSheet('Dataset_Router');

  targetSheet.appendRow(['Fecha', 'Telefono', 'Nombre', 'Chunk']);

  const data = sourceSheet.getDataRange().getValues();
  if (data.length <= 1) return;

  const COL_FECHA = 1;
  const COL_TELEFONO = 2;
  const COL_NOMBRE = 3;
  const COL_MENSAJE = 4;

  let output = [];

  for (let i = 1; i < data.length; i++) {
    const row = data[i];

    const fecha = row[COL_FECHA];
    const telefono = row[COL_TELEFONO];
    const nombre = row[COL_NOMBRE];
    let mensaje = row[COL_MENSAJE];

    // 🔴 FILTRO CLAVE → SOLO BEXO
    if (!nombre || !nombre.toString().startsWith('Bexo')) continue;

    if (!mensaje || mensaje.trim() === '') continue;

    // 🔧 Limpieza
    mensaje = mensaje
      .replace(/\[Mensaje sin texto\]/gi, '')
      .replace(/\r?\n+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();

    // 🔥 Split real
    let partes = mensaje.split(/\[NUEVO\]:?/i)
      .map(p => p.trim())
      .filter(p => p.length > 3); // evita basura tipo "ok"

    if (partes.length === 0) continue;

    // ✅ CHUNKS INDEPENDIENTES (NO acumulativos)
    for (let j = 0; j < partes.length; j++) {
      let chunk = partes[j];

      // filtro adicional anti ruido
      if (chunk.length < 8) continue;

      output.push([
        fecha,
        telefono,
        nombre,
        chunk
      ]);
    }
  }

  if (output.length > 0) {
    targetSheet.getRange(2, 1, output.length, 4).setValues(output);
  }

  targetSheet.getRange("A1:D1").setFontWeight("bold");
  targetSheet.setFrozenRows(1);

  Logger.log(`Dataset limpio generado: ${output.length} chunks`);
}

function test1_waha() {
  const res = UrlFetchApp.fetch(WAHA_URL + '/api/sessions', {
    headers: { 'X-Api-Key': WAHA_API_KEY },
    muteHttpExceptions: true
  });
  Logger.log('CODIGO: ' + res.getResponseCode());
  Logger.log('BODY: ' + res.getContentText());
}

function test3_descargarMedia() {
  const url = WAHA_URL + '/api/files/default/3EB09E6B78B3352CA3571C.jpeg';

  const res = UrlFetchApp.fetch(url, {
    headers: { 'X-Api-Key': WAHA_API_KEY },
    muteHttpExceptions: true
  });

  Logger.log('Codigo: ' + res.getResponseCode());
  Logger.log('Tipo: '   + res.getHeaders()['Content-Type']);

  if (res.getResponseCode() === 200) {
    const blob = res.getBlob().setName('comprobante_test.jpg');
    Logger.log('Bytes: ' + blob.getBytes().length);   // deberia dar ~28760
    DriveApp.createFile(blob);
    Logger.log('OK -> buscá "comprobante_test.jpg" en tu Drive');
  } else {
    Logger.log('BODY: ' + res.getContentText());
  }
}

var ARCHIVO_PROP      = 'ARCHIVO_HISTORIAL_ID';
var DIAS_A_CONSERVAR  = 30;
function nombreMes_(f) {
  var MESES = {'01':'Ene','02':'Feb','03':'Mar','04':'Abr','05':'May','06':'Jun',
               '07':'Jul','08':'Ago','09':'Sep','10':'Oct','11':'Nov','12':'Dic'};
  var mm = Utilities.formatDate(f, 'GMT-3', 'MM');
  var yy = Utilities.formatDate(f, 'GMT-3', 'yy');
  return MESES[mm] + ' ' + yy;
}

function archivarHistorial() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName('Historial');
  if (!sh || sh.getLastRow() < 2) { Logger.log('Nada que archivar.'); return; }

  // --- Abrir (o crear) el archivo externo ---
  var props = PropertiesService.getScriptProperties();
  var id = props.getProperty(ARCHIVO_PROP);
  var dest = null;
  if (id) { try { dest = SpreadsheetApp.openById(id); } catch (e) { dest = null; } }
  if (!dest) {
    dest = SpreadsheetApp.create('WZP Historial Archivo');
    props.setProperty(ARCHIVO_PROP, dest.getId());
    Logger.log('Archivo nuevo: ' + dest.getUrl());
  }

  var data     = sh.getDataRange().getValues();
  var cabecera = data[0];
  var corte    = new Date();
  corte.setDate(corte.getDate() - DIAS_A_CONSERVAR);

  var porMes = {}, conservar = [cabecera], viejas = 0;

  for (var i = 1; i < data.length; i++) {
    var f = new Date(data[i][1]);                 // columna B = Fecha
    if (isNaN(f.getTime()) || f >= corte) { conservar.push(data[i]); continue; }
    var mes = nombreMes_(f);
    (porMes[mes] = porMes[mes] || []).push(data[i]);
    viejas++;
  }

  if (!viejas) { Logger.log('Nada más viejo que ' + DIAS_A_CONSERVAR + ' días.'); return; }

  // --- 1. ESCRIBIR primero ---
  for (var mes in porMes) {
    var t = dest.getSheetByName(mes);
    if (!t) { t = dest.insertSheet(mes); t.appendRow(cabecera); t.setFrozenRows(1); }
    var filas = porMes[mes];
    t.getRange(t.getLastRow() + 1, 1, filas.length, cabecera.length).setValues(filas);
  }
  SpreadsheetApp.flush();

  // --- 2. Recién ahora reescribir el origen ---
  sh.clearContents();
  sh.getRange(1, 1, conservar.length, cabecera.length).setValues(conservar);

  var sobrantes = sh.getMaxRows() - conservar.length;
  if (sobrantes > 0) sh.deleteRows(conservar.length + 1, sobrantes);

  Logger.log(viejas + ' filas archivadas en ' + dest.getUrl());
}