# Apps Script "INTAKE WZP GOOGLE" (el bot de comprobantes)

Esta carpeta **es** el código del Apps Script. Ya no se copia y pega en el editor de Google:
Claude cambia los archivos acá, en GitHub, y vos los subís con un solo comando desde Termux.

- `*.gs` y `appsscript.json`: el código, con los mismos nombres que en el editor de Google.
- `.clasp.json`: le dice a clasp a qué proyecto de Google subir (el id del proyecto, sin claves).
- `subir.sh`: el comando para subir.
- `0_Config.gs`: lee los datos privados (clave de WAHA, IPs, teléfonos, ids de planillas) de las
  **Propiedades del script**. Este repo es público: en los `.gs` nunca va un dato privado.
  Si hace falta uno nuevo, va en ⚙️ Configuración del proyecto → Propiedades de la secuencia de comandos,
  y en el código se lee con `CONFIG.NOMBRE`. `subir.sh` se niega a subir si encuentra una IP o una clave escrita.

## Subir un cambio (lo de todos los días)

1. Sube el código y publica una nueva versión de la implementación web.

```
sh ~/bexo-scripts/apps-script/subir.sh
```

Hace cuatro cosas: baja lo último de GitHub, se fija que nadie haya cambiado el código a mano en el editor
de Google (si pasó, **no sube** y te avisa, para no perder ese cambio), sube el código y crea la nueva versión
de la implementación (lo que antes era Implementar → Administrar implementaciones → ✏️ → Nueva versión).
La URL de la implementación no cambia, así que WAHA/GOWS, Termux y el diagnóstico siguen funcionando igual.

Regla de oro: **ya no edites en el editor de Google.** Si hace falta un cambio, pedíselo a Claude.
Mirar el código ahí, ejecutar funciones o ver los registros sí se puede, como siempre.

## Instalar clasp (una sola vez, en Termux)

1. Instala Node.js, que es lo que necesita clasp para funcionar.

```
pkg install nodejs
```

2. Instala clasp, la herramienta de Google para subir Apps Script desde la terminal.

```
npm install -g @google/clasp
```

3. Activá la "Apps Script API" en tu cuenta de Google: abrí esta página en el teléfono, con la misma cuenta
   dueña de la planilla, y poné el interruptor en **Activado**:
   https://script.google.com/home/usersettings

4. Loguéate con tu cuenta de Google (te va a mostrar un link largo).

```
clasp login --no-localhost
```

   Tocá el link, elegí tu cuenta y dale **Permitir** a todo. Al final el navegador va a mostrar una página
   que **no carga** ("no se puede acceder al sitio"): es normal. Copiá la dirección completa de esa página
   (empieza con `http://localhost`), volvé a Termux, pegala y Enter. Tiene que decir que te logueaste.

5. Cargá los datos privados en Google (una sola vez, antes de la primera subida). Claude te pasa aparte el
   archivo `CargarClaves_UNA_VEZ.gs` (no está en GitHub). En el editor de Apps Script: **+ → Secuencia de
   comandos**, llamalo `Temporal`, pegá todo el contenido, guardá, elegí `cargarClavesUnaVez` arriba y tocá
   **Ejecutar**. En el registro tiene que decir "✅ Listo: están las 12 propiedades". La primera subida borra
   el archivo `Temporal` sola.

6. Baja lo último del repo, para tener esta carpeta en el teléfono.

```
git -C ~/bexo-scripts pull
```

7. Primera subida.

```
sh ~/bexo-scripts/apps-script/subir.sh
```

   La primera vez busca sola cuál es tu implementación web y la recuerda. Si tenés más de una, te muestra la
   lista y te pide que pegues el id de la buena (empieza con `AKfy…`; es el mismo que aparece en la URL que
   usan WAHA/GOWS).

El login queda guardado en `~/.clasprc.json` y el id de la implementación en `~/.bexo-implementacion`,
los dos solo en el teléfono, nunca en GitHub.

## Si algo falla

- "Encontré datos privados escritos en el código": alguien puso una IP o clave en un `.gs`. Hay que pasarla a
  Propiedades del script; avisale a Claude.
- Algo deja de mandar WhatsApp después de subir: en el editor ejecutá `revisarConfiguracion` y fijate en el
  registro si falta alguna propiedad.

- "No encuentro clasp": falta el paso 2.
- "No pude leer el proyecto de Google": falta activar la API (paso 3), o el login venció (repetí el paso 4).
- "Estos archivos se cambiaron a mano en el editor": alguien tocó el código en Google. Avisale a Claude
  para pasar ese cambio a GitHub antes de subir. Si de verdad querés pisarlo:
  `sh ~/bexo-scripts/apps-script/subir.sh --pisar`
