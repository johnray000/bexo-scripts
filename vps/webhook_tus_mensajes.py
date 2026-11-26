#!/usr/bin/env python3
"""Que WAHA le mande al Apps Script también TUS mensajes (evento message.any), para el intake (issue #57).

  python3 webhook_tus_mensajes.py           muestra cómo está el webhook (no cambia nada)
  python3 webhook_tus_mensajes.py aplicar   cambia "message" por "message.any" en el webhook del Apps Script
  python3 webhook_tus_mensajes.py volver    lo deja como antes ("message")

Desde el teléfono, sin copiar nada al VPS:
  ssh <vps> python3 - aplicar < ~/bexo-scripts/vps/webhook_tus_mensajes.py

"message.any" trae los mensajes de los clientes Y los tuyos, así que REEMPLAZA a "message" (tener los dos haría
llegar cada mensaje dos veces; igual doPost ignora un mensaje repetido por su id). Solo toca el webhook que va a
script.google.com. WAHA reinicia la sesión unos segundos al guardar. Python 3.8, sin librerías extra.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

WAHA = os.environ.get('WAHA', 'http://localhost:8080')
SESION = 'default'


def clave():
    if os.environ.get('WAHA_KEY'):
        return os.environ['WAHA_KEY']
    try:
        for linea in open(os.path.expanduser('~/waha.env')):
            if 'API_KEY=' in linea:
                return linea.split('=', 1)[1].strip().strip('"\'')
    except OSError:
        pass
    return ''


def api(metodo, ruta, cuerpo=None, espera=20):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(WAHA + ruta, data=datos, method=metodo,
                                 headers={'X-Api-Key': clave(), 'Content-Type': 'application/json', 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=espera) as r:
            t = r.read().decode('utf-8', 'replace')
            return r.status, (json.loads(t) if t.strip().startswith(('{', '[')) else t)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')
    except Exception as e:  # noqa: BLE001
        return 0, str(e)


def eventos_nuevos(eventos, accion):
    """La lista de eventos después de aplicar/volver (sin repetir, conserva los demás)."""
    sin = [e for e in eventos if e not in ('message', 'message.any')]
    return (['message.any'] if accion == 'aplicar' else ['message']) + sin


def main(args):
    accion = args[0] if args else 'ver'
    if accion not in ('ver', 'aplicar', 'volver'):
        sys.exit(__doc__)
    c, ses = api('GET', '/api/sessions/%s' % SESION)
    if c != 200 or not isinstance(ses, dict):
        sys.exit('❌ No pude leer la sesión de WAHA (código %s): %s' % (c, str(ses)[:200]))
    config = ses.get('config') or {}
    hooks = config.get('webhooks') or []
    del_script = [h for h in hooks if 'script.google' in (h.get('url') or '')]
    if not del_script:
        sys.exit('❌ No hay webhook a script.google.com en la sesión. No cambio nada.')
    for h in del_script:
        ev = h.get('events') or []
        print('Webhook %s…\n  eventos: %s' % (h['url'][:60], ', '.join(ev) or '(ninguno)'))
        print('  tus mensajes: %s' % ('✅ llegan (message.any)' if 'message.any' in ev else '❌ no llegan'))
    if accion == 'ver':
        return
    cambio = False
    for h in del_script:
        nuevo = eventos_nuevos(h.get('events') or [], accion)
        if nuevo != (h.get('events') or []):
            h['events'] = nuevo
            cambio = True
    if not cambio:
        print('Ya estaba así: no cambio nada.')
        return
    c, r = api('PUT', '/api/sessions/%s' % SESION, {'name': SESION, 'config': config}, espera=60)
    if c not in (200, 201):
        sys.exit('❌ WAHA no aceptó el cambio (código %s): %s' % (c, str(r)[:300]))
    print('▶ Guardado. Esperando que la sesión vuelva…')
    for _ in range(30):
        time.sleep(2)
        c, ses = api('GET', '/api/sessions/%s' % SESION)
        if isinstance(ses, dict) and ses.get('status') == 'WORKING':
            ev = [h.get('events') for h in (ses.get('config') or {}).get('webhooks') or [] if 'script.google' in (h.get('url') or '')]
            print('✅ Sesión WORKING. Eventos: %s' % ev)
            return
    sys.exit('⚠️ La sesión no volvió a WORKING en 60 s: revisá con vps/diagnostico.py')


if __name__ == '__main__':
    main(sys.argv[1:])
