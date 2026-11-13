// ==========================================
// 0_Config.gs — Datos privados del bot (claves, IPs, teléfonos, ids)
// ==========================================
// El código vive en un repo PÚBLICO de GitHub, así que acá no va ningún dato privado.
// Los valores están en: editor → ⚙️ Configuración del proyecto → Propiedades de la secuencia de comandos.
// Para revisar que estén todos: ejecutá revisarConfiguracion() y mirá el registro.
//
// Este archivo tiene que ir PRIMERO (lo asegura filePushOrder en .clasp.json): los demás usan CONFIG al cargar.

var CONFIG = PropertiesService.getScriptProperties().getProperties();

/** Lista separada por comas en una propiedad → array sin espacios ni vacíos. */
function listaConfig_(clave) {
  return String(CONFIG[clave] || '').split(',').map(function (s) { return s.trim(); }).filter(String);
}

var CONFIG_CLAVES = {
  WAHA_URL: 'URL de WAHA/GOWS en el VPS, sin barra al final (http://IP:8080)',
  WAHA_API_KEY: 'X-Api-Key de WAHA',
  RELAY_URL: 'URL del relay de Binance en el VPS (http://IP:8082)',
  RELAY_TOKEN: 'token del relay (ya estaba cargado de antes)',
  OPENCLAW_URL: 'webhook de OpenClaw en Digital Ocean (http://IP:5000/webhook_orquestador)',
  OPENCLAW_KEY: 'X-Api-Key de OpenClaw',
  DEEPSEEK_KEY: 'clave de DeepSeek para leer comprobantes (ya estaba cargada de antes)',
  MI_TELEFONO: 'tu número, sin + ni espacios',
  ESTADO_TEST_TEL: 'a quién va la prueba de estados',
  BLACKLIST_TELEFONOS: 'números bloqueados en la recepción, separados por coma',
  ESC_IGNORAR_NUMEROS: 'números que el escáner no revisa (familia, amigos), separados por coma',
  REGISTRO_BEXO_ID: 'id de la planilla Registro Bexo (Movs UY)'
};

/** Ejecutala desde el editor: dice qué propiedades faltan. No cambia nada. */
function revisarConfiguracion() {
  var faltan = Object.keys(CONFIG_CLAVES).filter(function (k) { return !CONFIG[k]; });
  Logger.log(faltan.length ? '❌ Faltan: ' + faltan.map(function (k) { return k + ' (' + CONFIG_CLAVES[k] + ')'; }).join('; ')
                           : '✅ Están todas las propiedades (' + Object.keys(CONFIG_CLAVES).length + ').');
  return faltan;
}
