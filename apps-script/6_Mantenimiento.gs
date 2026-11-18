// ==========================================
// MÓDULO 6: MANTENIMIENTO DE MOVIMIENTOS
//
//  - colorearMovimientos(): colores por estado. Correr UNA vez.
//  - limpiarDescartados_(): manda a la papelera de Drive las
//    imágenes de filas DESCARTADO y DUPLICADO. Corre sola dentro
//    de refrescarTodo() (casilla B3 y trigger horario).
// ==========================================

var COLOR_CONTADO    = '#d9f2e3';   // verde claro
var COLOR_DESCARTADO = '#e6e6e6';   // gris claro
var ESTADOS_A_BORRAR = ['DESCARTADO', 'DUPLICADO'];
var MARCA_BORRADA    = 'borrada';   // texto que queda en la columna Imagen

// ==========================================
// 1. COLORES POR ESTADO
//    Usa formato condicional (2 reglas simples), así el color
//    cambia solo cuando editás el Estado a mano, incluso desde
//    el teléfono. Va sobre columnas enteras A:Q para que las
//    filas nuevas (que se insertan arriba) también queden cubiertas.
//    Correr UNA vez desde el editor. Si lo corrés de nuevo,
//    reemplaza las reglas en vez de duplicarlas.
// ==========================================
function colorearMovimientos() {
  var sh = hojaMovimientos_();
  var rango = sh.getRange('A:Q');

  // Conserva otras reglas que tengas, saca solo las nuestras
  var reglas = sh.getConditionalFormatRules().filter(function (r) {
    var c = r.getBooleanCondition();
    if (!c) return true;
    var f = String(c.getCriteriaValues()[0] || '');
    return f.indexOf('"CONTADO"') === -1 && f.indexOf('"DESCARTADO"') === -1;
  });

  reglas.push(SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied('=$A1="CONTADO"')
    .setBackground(COLOR_CONTADO)
    .setRanges([rango]).build());

  reglas.push(SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied('=$A1="DESCARTADO"')
    .setBackground(COLOR_DESCARTADO)
    .setRanges([rango]).build());

  sh.setConditionalFormatRules(reglas);
  Logger.log('Colores aplicados a Movimientos');
}

// ==========================================
// 2. LIMPIEZA DE IMÁGENES DESCARTADAS / DUPLICADAS
//    - Solo toca archivos que estén dentro de Comprobantes_WZP.
//    - Los manda a la PAPELERA (se pueden recuperar 30 días).
//    - Marca la columna Imagen con "borrada" para no repetir.
//    - La fila queda en Movimientos como registro.
// ==========================================
function limpiarDescartados_() {
  var sh = hojaMovimientos_();
  if (sh.getLastRow() < 2) return 0;

  var data = sh.getDataRange().getValues();
  var borradas = 0;

  for (var i = 1; i < data.length; i++) {
    var estado  = String(data[i][C.ESTADO - 1] || '').trim();
    var imagen  = String(data[i][C.IMAGEN - 1] || '').trim();
    var driveId = String(data[i][C.DRIVE_ID - 1] || '').trim();

    if (ESTADOS_A_BORRAR.indexOf(estado) === -1) continue;
    if (!driveId || imagen === MARCA_BORRADA) continue;

    try {
      var file = DriveApp.getFileById(driveId);

      if (!estaEnCarpetaComprobantes_(file)) {
        logError_('LIMPIEZA', 'No está en ' + CARPETA_COMPROBANTES + ', no se toca: ' + driveId);
        continue;
      }

      file.setTrashed(true);
      sh.getRange(i + 1, C.IMAGEN).setValue(MARCA_BORRADA);
      borradas++;

    } catch (err) {
      logError_('LIMPIEZA', driveId + ' | ' + err.message);
    }
  }
  return borradas;
}

function estaEnCarpetaComprobantes_(file) {
  var padres = file.getParents();
  while (padres.hasNext()) {
    if (padres.next().getName() === CARPETA_COMPROBANTES) return true;
  }
  return false;
}

// Para probar a mano desde el editor
function testLimpieza() {
  Logger.log('Imágenes enviadas a la papelera: ' + limpiarDescartados_());
}

function probarBinance() {
  const r = UrlFetchApp.fetch('https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search', {
    method: 'post',
    contentType: 'application/json',
    muteHttpExceptions: true,
    payload: JSON.stringify({ asset: 'USDT', fiat: 'VES', tradeType: 'SELL', page: 1, rows: 5, payTypes: [] })
  });
  Logger.log(r.getResponseCode());
  Logger.log(r.getContentText().slice(0, 500));
}

function probarApiBinance() { Logger.log(UrlFetchApp.fetch('https://api.binance.com/api/v3/ping', {muteHttpExceptions: true}).getResponseCode()); }
