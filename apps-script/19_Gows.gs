/**
 * 19_Gows.gs — Saca el teléfono de quien escribe, sirva el mensaje del motor NOWEB o del motor GOWS de WAHA.
 *
 * NOWEB manda el número en _data.key.remoteJid / remoteJidAlt. GOWS lo manda en _data.Info.Sender / SenderAlt
 * (a veces con el dispositivo pegado: "5491…:12@s.whatsapp.net") y, para algunos contactos, `from` llega como
 * "…@lid" (un identificador interno, no el número). En ese caso se le pregunta a WAHA el número real y se guarda
 * 6 h en caché.
 *
 * Instalación (una vez): archivo nuevo 19_Gows con esto, y en 2_Recepcion.gs (doPost) cambiar DOS líneas:
 *   1) estas dos:
 *        let phoneRaw = altFrom.includes('@s.whatsapp.net') ? altFrom : rawFrom;
 *        let phone = phoneRaw.replace(/\D/g, ''); // Deja solo números
 *      por esta:
 *        let phone = telefonoRemitente_(payload);
 *   2) esta:
 *        let name = _data.pushName || 'Sin Nombre';
 *      por esta:
 *        let name = _data.pushName || (_data.Info && _data.Info.PushName) || 'Sin Nombre';
 * Redesplegar (Nueva versión). Con NOWEB da exactamente el mismo número que antes.
 *
 * Usa WAHA_URL y WAHA_API_KEY de 3_Operativa.gs.
 */
function telefonoRemitente_(payload) {
  var d = payload._data || {};
  var key = d.key || {};
  var info = d.Info || d.info || {};
  var candidatos = [
    // NOWEB, igual que antes: remoteJid si es número, si no remoteJidAlt
    (key.remoteJid && String(key.remoteJid).indexOf('@s.whatsapp.net') !== -1) ? key.remoteJid : '',
    key.remoteJidAlt,
    // GOWS
    info.SenderAlt, info.Sender, info.Chat,
    payload.from
  ];
  for (var i = 0; i < candidatos.length; i++) {
    var c = String(candidatos[i] || '');
    if (c.indexOf('@s.whatsapp.net') !== -1 || c.indexOf('@c.us') !== -1) return soloNumero_(c);
  }
  // Solo hay LID: se le pregunta a WAHA
  for (var j = 0; j < candidatos.length; j++) {
    var lid = String(candidatos[j] || '');
    if (lid.indexOf('@lid') !== -1) {
      var pn = numeroDeLid_(lid);
      if (pn) return pn;
    }
  }
  return '';
}

/** "5491123:12@s.whatsapp.net" → "5491123". Sin el ":12" del dispositivo, que si no se pegaría al número. */
function soloNumero_(jid) {
  return String(jid).split('@')[0].split(':')[0].replace(/\D/g, '');
}

function numeroDeLid_(lid) {
  var cache = CacheService.getScriptCache();
  var k = 'LID_' + lid;
  var ya = cache.get(k);
  if (ya) return ya;
  try {
    var r = UrlFetchApp.fetch(WAHA_URL + '/api/default/lids/' + encodeURIComponent(lid),
      { headers: { 'X-Api-Key': WAHA_API_KEY }, muteHttpExceptions: true });
    if (r.getResponseCode() !== 200) return '';
    var pn = soloNumero_(JSON.parse(r.getContentText()).pn || '');
    if (pn) cache.put(k, pn, 6 * 3600);
    return pn;
  } catch (e) {
    logError_('LID', lid + ': ' + (e.message || e));
    return '';
  }
}
