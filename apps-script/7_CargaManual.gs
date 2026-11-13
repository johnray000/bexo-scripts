// ==========================================
// MÓDULO 7: CARGA MANUAL EN MOVIMIENTOS
//
// Para seguir registrando cuando DeepSeek se cae o la lectura
// automática está apagada. Todo funciona desde el teléfono:
//
//  - NO toca validaciones, desplegables ni colores de Movimientos:
//    esos los configurás vos a mano (chips con colores incluidos).
//
//  - Autocompletado: cuando una fila tiene Nombre + Monto + Cuenta
//    y su Estado está vacío, PENDIENTE, REVISAR o NO_IMAGEN, pasa a
//    CONTADO y se completa Moneda (ARS), Fecha (ahora, si falta),
//    ID (MAN-...), Imagen ("manual" si no hay foto) y Telefono
//    (buscándolo por nombre en el Directorio).
//    Si el Estado ya es CONTADO, solo completa lo que falte.
//    Lo dispara alEditar() de 5_Dashboard.gs.
//
//  - Interruptor de lectura automática: casilla H3 del Dashboard.
//    Tildada = DeepSeek lee los PENDIENTE. Destildada = no se llama
//    a DeepSeek; los comprobantes siguen entrando como PENDIENTE con
//    nombre e imagen, y vos completás Monto y Cuenta a mano.
// ==========================================

var PROP_OCR        = 'OCR_ACTIVO';    // propiedad del script: 'SI' / 'NO'
var MONEDA_DEFECTO  = 'ARS';
var IMAGEN_MANUAL   = 'manual';        // texto en la columna Imagen de las filas sin foto
var MAX_FILAS_EDIT  = 50;              // si pegás más filas de una, no se autocompleta

// ==========================================
// 1. INTERRUPTOR DE LECTURA AUTOMÁTICA
//    Si la propiedad no existe, la lectura está ACTIVA
//    (así nada cambia hasta que destildes la casilla).
// ==========================================
function ocrActivo_() {
  return PropertiesService.getScriptProperties().getProperty(PROP_OCR) !== 'NO';
}

// La llama alEditar() cuando tocás H3 en el Dashboard
function fijarLectura_(activa) {
  PropertiesService.getScriptProperties().setProperty(PROP_OCR, activa ? 'SI' : 'NO');
  var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Dashboard');
  if (sh) etiquetaLectura_(sh, activa);
}

// Texto al lado de la casilla H3 (lo usa también construirDashboard)
function etiquetaLectura_(sh, activa) {
  sh.getRange('I3').setValue(activa ? 'lectura automática ON' : 'lectura OFF · carga manual')
    .setFontSize(8).setFontColor(activa ? VERDE : ROJO);
}

// ==========================================
// 2. AUTOCOMPLETADO DE FILAS MANUALES
//    La llama alEditar() cuando editás Movimientos.
//    Solo lee las filas tocadas; si no hay nada que hacer, no escribe.
// ==========================================
function completarFilasManuales_(rango) {
  if (rango.getColumn() > C.CUENTA) return;          // solo columnas A..F

  var sh = rango.getSheet();
  var f0 = Math.max(rango.getRow(), 2);
  var f1 = rango.getLastRow();
  if (f1 < f0 || f1 - f0 + 1 > MAX_FILAS_EDIT) return;

  var datos = sh.getRange(f0, 1, f1 - f0 + 1, ENCABEZADOS.length).getValues();
  var abiertos = ['', E_PEND, E_REVI, E_NOIM, E_CONT];   // estados que se completan a mano

  for (var i = 0; i < datos.length; i++) {
    var r      = datos[i];
    var fila   = f0 + i;
    var estado = String(r[C.ESTADO - 1] || '').trim();
    var fecha  = r[C.RECIBIDO - 1];
    var nombre = String(r[C.NOMBRE - 1] || '').trim();
    var monto  = Number(r[C.MONTO - 1]) || 0;
    var cuenta = String(r[C.CUENTA - 1] || '').trim();

    if (abiertos.indexOf(estado) === -1) continue;   // LEIDO, DESCARTADO, etc.: no se toca

    // Fila nueva sin fecha: se pone ya, así un reordenamiento no la manda al fondo
    if (fecha === '' && (nombre || monto || cuenta)) {
      fecha = new Date();
      sh.getRange(fila, C.RECIBIDO).setValue(fecha);
    }

    if (!nombre || !monto || !cuenta) continue;      // todavía incompleta
    if (!(fecha instanceof Date)) {
      logError_('CARGA_MANUAL', 'Fila ' + fila + ': la fecha no es fecha (' + fecha + ')');
      continue;
    }

    if (!String(r[C.MONEDA - 1] || '').trim()) sh.getRange(fila, C.MONEDA).setValue(MONEDA_DEFECTO);
    if (!String(r[C.TELEFONO - 1] || '').trim()) {
      var tel = telefonoDeNombre_(nombre);           // llave estable para métricas por cliente
      if (tel) sh.getRange(fila, C.TELEFONO).setValue(tel);
    }
    if (!r[C.ID - 1]) {
      sh.getRange(fila, C.ID).setValue('MAN-' + Utilities.formatDate(new Date(), 'GMT-3', 'yyyyMMdd-HHmmss') + '-' + fila);
    }
    if (!r[C.DRIVE_ID - 1] && !r[C.IMAGEN - 1]) sh.getRange(fila, C.IMAGEN).setValue(IMAGEN_MANUAL);

    if (estado !== E_CONT) marcar_(sh, fila, E_CONT);  // vos lo cargaste = vos lo revisaste
  }
}

// Teléfono del Directorio para ese nombre exacto (el primero si hay varios).
// Se lee solo cuando una fila se completa, no en cada edición.
function telefonoDeNombre_(nombre) {
  var dir = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(DIR_SHEET);
  if (!dir || dir.getLastRow() < 2) return '';
  var datos = dir.getRange(2, 1, dir.getLastRow() - 1, 2).getValues();
  for (var i = 0; i < datos.length; i++) {
    if (String(datos[i][1]).trim() === nombre) return String(datos[i][0]).trim();
  }
  return '';
}

// ==========================================
// 3. PARA PROBAR DESDE EL EDITOR
// ==========================================
function testCargaManual() {
  Logger.log('Lectura automática: ' + (ocrActivo_() ? 'ON' : 'OFF'));
}
