// ==========================================
// MÓDULO 1: GESTIÓN DE IDENTIDAD (PEOPLE API)
// ==========================================
/* Gestiona la agenda. Se conecta a Google Contacts, extrae los "Bexo", limpia los símbolos (quita el + y los espacios) y actualiza el Directorio*/

var DIR_SHEET = 'Directorio';

function onOpen() {
  const ui = SpreadsheetApp.getUi();
  ui.createMenu('🤖 Caimán')
    //.addItem('🔄 Sincronizar Contactos Bexo', 'syncContactsToDirectory')
    .addItem('💵 Procesar comprobantes', 'revisarComprobantes')
    .addItem('✅ Contar los LEIDOS', 'contarTodosLosLeidos')
    .addItem('📋 Solo resumen', 'soloResumen')
    .addToUi();
}

function syncContactsToDirectory() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(DIR_SHEET);
  
  if (!sh) {
    sh = ss.insertSheet(DIR_SHEET);
    sh.appendRow(['Teléfono', 'Nombre CRM']);
    sh.getRange("A1:B1").setFontWeight("bold");
  }

  let updatedData = [];
  let pageToken = null;
  
  do {
    let response = People.People.Connections.list('people/me', {
      personFields: 'names,phoneNumbers',
      pageToken: pageToken,
      pageSize: 1000
    });
    
    let connections = response.connections;
    if (connections) {
      for (let i = 0; i < connections.length; i++) {
        let person = connections[i];
        
        let name = "";
        if (person.names && person.names.length > 0) {
          name = person.names[0].displayName || "";
        }
        
        // Filtro estricto: Solo contactos que contengan "bexo"
        if (name.toLowerCase().includes("bexo")) {
          if (person.phoneNumbers && person.phoneNumbers.length > 0) {
            for (let j = 0; j < person.phoneNumbers.length; j++) {
              let phoneRaw = person.phoneNumbers[j].value;
              // Limpia el +, guiones y espacios
              let phoneClean = phoneRaw.replace(/\D/g, ''); 
              if (phoneClean) {
                updatedData.push([phoneClean, name]);
              }
            }
          }
        }
      }
    }
    pageToken = response.nextPageToken;
  } while (pageToken);

  if (updatedData.length > 0) {
    const lastRow = sh.getLastRow();
    if (lastRow > 1) {
      sh.getRange(2, 1, lastRow - 1, 2).clearContent();
    }
    sh.getRange(2, 1, updatedData.length, 2).setValues(updatedData);
  }
}