#!/usr/bin/env python3
"""Pasa WAHA del motor NOWEB al motor GOWS, con vuelta atrás.

  python3 pasar_a_gows.py            hace el cambio y te da el código para vincular
  python3 pasar_a_gows.py volver     vuelve al WAHA anterior (NOWEB), tal como quedó

Qué hace (nada se borra):
  1. Copia la configuración de la sesión actual (webhook, ignorar estados/grupos, etc.).
  2. Frena el contenedor `waha` y lo renombra `waha-noweb` (queda guardado para volver).
  3. Levanta un `waha` nuevo con la MISMA imagen, puertos, clave y carpeta de fotos, pero con el motor GOWS
     y su propia carpeta de sesión (volumen `waha_sessions_gows`), así no pisa la sesión vieja.
  4. Crea la sesión `default` con la misma configuración y pide el código de vinculación para tu número.
  5. Espera a que la vincules y confirma que quedó WORKING.
Python 3.8, sin librerías extra. Usa sudo docker.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

WAHA = 'http://localhost:8080'
SESION = 'default'
TELEFONO = '5491123913064'
VOL_GOWS = 'waha_sessions_gows'


def sh(*args, check=True):
    r = subprocess.run(['sudo', '-n', 'docker'] + list(args), capture_output=True, text=True)
    if check and r.returncode != 0:
        sys.exit('❌ docker %s falló: %s' % (' '.join(args[:2]), (r.stderr or r.stdout).strip()[:300]))
    return r.stdout.strip()


def clave():
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
    except Exception as e:
        return 0, str(e)


def esperar_api(seg=120):
    fin = time.time() + seg
    while time.time() < fin:
        c, _ = api('GET', '/api/sessions')
        if c == 200:
            return True
        time.sleep(3)
    return False


def volver():
    nombres = sh('ps', '-a', '--format', '{{.Names}}').split()
    if 'waha-noweb' not in nombres:
        sys.exit('❌ No existe waha-noweb: no hay a dónde volver.')
    print('▶ Frenando el WAHA con GOWS y volviendo al anterior…')
    sh('stop', 'waha', check=False)
    sh('rm', '-f', 'waha-gows', check=False)
    sh('rename', 'waha', 'waha-gows', check=False)
    sh('rename', 'waha-noweb', 'waha')
    sh('start', 'waha')
    print('✅ Volvió el WAHA anterior (NOWEB). Si estaba sordo, sigue sordo: hay que re-vincularlo con código.')


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'volver':
        return volver()

    nombres = sh('ps', '-a', '--format', '{{.Names}}').split()
    if 'waha-noweb' in nombres:
        sys.exit('❌ Ya existe waha-noweb: parece que el cambio ya se hizo. Para deshacerlo: python3 pasar_a_gows.py volver')
    if 'waha' not in nombres:
        sys.exit('❌ No encuentro el contenedor waha.')
    if not clave():
        sys.exit('❌ No encuentro la API key en ~/waha.env')

    # 1. Configuración actual
    c, ses = api('GET', '/api/sessions/%s' % SESION)
    config = (ses.get('config') if isinstance(ses, dict) else None) or {}
    config.pop('noweb', None)   # solo vale para NOWEB
    if not config.get('webhooks'):
        sys.exit('❌ No pude leer el webhook de la sesión actual (código %s). No cambio nada.' % c)
    print('▶ Configuración actual copiada: webhook %s' % config['webhooks'][0].get('url', '')[:60] + '…')

    ins = json.loads(sh('inspect', 'waha'))[0]
    imagen = ins['Config']['Image']
    env = [e for e in ins['Config']['Env'] if not e.startswith('WHATSAPP_DEFAULT_ENGINE=')]
    env.append('WHATSAPP_DEFAULT_ENGINE=GOWS')
    puertos = ins['HostConfig'].get('PortBindings') or {}
    reinicio = (ins['HostConfig'].get('RestartPolicy') or {}).get('Name') or 'unless-stopped'
    montajes = ins.get('Mounts') or []

    args = ['run', '-d', '--name', 'waha', '--restart', reinicio]
    for e in env:
        args += ['-e', e]
    for cont, binds in puertos.items():
        for b in binds or []:
            args += ['-p', '%s%s:%s' % ((b.get('HostIp') + ':') if b.get('HostIp') else '', b.get('HostPort'), cont.split('/')[0])]
    sesiones_ok = False
    for m in montajes:
        destino = m['Destination']
        if '.sessions' in destino:
            args += ['-v', '%s:%s' % (VOL_GOWS, destino)]   # sesión nueva aparte: la vieja queda intacta
            sesiones_ok = True
        elif m.get('Type') == 'volume':
            args += ['-v', '%s:%s' % (m['Name'], destino)]
        else:
            args += ['-v', '%s:%s' % (m['Source'], destino)]
    if not sesiones_ok:
        args += ['-v', '%s:/app/.sessions' % VOL_GOWS]
    args.append(imagen)

    # 2-3. Cambio de contenedor
    print('▶ Frenando el WAHA actual (queda guardado como waha-noweb)…')
    sh('stop', 'waha')
    sh('rename', 'waha', 'waha-noweb')
    print('▶ Levantando WAHA con GOWS (%s)…' % imagen)
    r = subprocess.run(['sudo', '-n', 'docker'] + args, capture_output=True, text=True)
    if r.returncode != 0:
        print('❌ No pudo arrancar: %s' % r.stderr.strip()[:300])
        sh('rename', 'waha-noweb', 'waha')
        sh('start', 'waha')
        sys.exit('Volví al WAHA anterior. No cambió nada.')
    if not esperar_api():
        sys.exit('❌ WAHA con GOWS no responde. Para volver: python3 pasar_a_gows.py volver')

    # 4. Sesión con la misma configuración
    c, t = api('POST', '/api/sessions', {'name': SESION, 'start': True, 'config': config})
    if c not in (200, 201):
        api('PUT', '/api/sessions/%s' % SESION, {'name': SESION, 'config': config})
        api('POST', '/api/sessions/%s/start' % SESION)
    c, ses = api('GET', '/api/sessions/%s' % SESION)
    print('▶ Sesión creada: %s' % (json.dumps((ses or {}).get('engine'), ensure_ascii=False)[:80] if isinstance(ses, dict) else ses))

    codigo = None
    for _ in range(20):
        c, ses = api('GET', '/api/sessions/%s' % SESION)
        estado = ses.get('status') if isinstance(ses, dict) else None
        if estado == 'WORKING':
            break
        if estado == 'SCAN_QR_CODE':
            c, t = api('POST', '/api/%s/auth/request-code' % SESION, {'phoneNumber': TELEFONO})
            if isinstance(t, dict) and t.get('code'):
                codigo = t['code']
                break
        time.sleep(3)
    if codigo:
        print()
        print('=' * 44)
        print('  CÓDIGO PARA VINCULAR:   %s' % codigo)
        print('=' * 44)
        print('En el teléfono: WhatsApp → Dispositivos vinculados → Vincular un dispositivo →')
        print('"Vincular con número de teléfono" → escribí el código. Tenés unos minutos.')
        print()

    # 5. Esperar a que quede WORKING
    print('▶ Esperando que vincules… (hasta 5 min)')
    fin = time.time() + 300
    while time.time() < fin:
        c, ses = api('GET', '/api/sessions/%s' % SESION)
        if isinstance(ses, dict) and ses.get('status') == 'WORKING':
            print('✅ WAHA con GOWS quedó WORKING como %s' % ((ses.get('me') or {}).get('id', '?')))
            print('Ahora mandá un "prueba" desde otro número y tocá DIAGNÓSTICO en el teléfono.')
            print('En Dispositivos vinculados podés cerrar el dispositivo viejo (el de NOWEB).')
            return
        time.sleep(5)
    print('⚠️ No quedó WORKING en 5 min. Si el código venció, corré de nuevo solo esto para pedir otro:')
    print('   python3 pasar_a_gows.py codigo')


def otro_codigo():
    c, t = api('POST', '/api/%s/auth/request-code' % SESION, {'phoneNumber': TELEFONO})
    print('Código: %s' % (t.get('code') if isinstance(t, dict) else t))


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'codigo':
        otro_codigo()
    else:
        main()
