// Temporal: copia la hoja Movimientos como CSV a la carpeta "Historial P2P" de Drive, para cruzarla con Ordenes_P2P.
// No toca la planilla. Se puede borrar después.

function exportarMovimientosCSV() {
  var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Movimientos');
  var datos = sh.getDataRange().getDisplayValues().map(function (fila) {
    return fila.slice(0, 21).map(function (v, i) {
      if (i === 16) v = '';                                   // Raw_JSON: no hace falta
      return '"' + String(v).replace(/"/g, '""') + '"';
    }).join(',');
  }).join('\n');
  var carpetas = DriveApp.getFoldersByName('Historial P2P');
  var carpeta = carpetas.hasNext() ? carpetas.next() : DriveApp.getRootFolder();
  var nombre = 'movimientos_' + Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd') + '.csv';
  var viejos = carpeta.getFilesByName(nombre);
  while (viejos.hasNext()) viejos.next().setTrashed(true);
  carpeta.createFile(nombre, datos, MimeType.CSV);
  Logger.log('Listo: %s en la carpeta %s', nombre, carpeta.getName());
}
