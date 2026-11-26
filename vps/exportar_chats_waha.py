#!/usr/bin/env python3
"""Exporta de WAHA los chats de clientes (mensajes tuyos y de ellos, con citas) para armar las pruebas del intake.

Se corre desde el teléfono, sin copiar nada al VPS; el resultado vuelve por la misma conexión:
  ssh <vps> python3 - < ~/bexo-scripts/vps/exportar_chats_waha.py > ~/storage/downloads/chats_waha.json.gz

Opciones (después de `python3 -`):  --todos   también chats que no empiezan con "Bexo"
                                    --max N   mensajes por chat (por defecto 3000)
Salida: JSON comprimido por la salida estándar; el avance va a la salida de error.
Solo lee: no manda nada ni marca como leído. Python 3.8, sin librerías extra.
Trae lo que WAHA tenga guardado: si en algún momento se cambió de motor o se volvió a vincular, lo anterior puede no estar.
"""
import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

WAHA = os.environ.get('WAHA', 'http://localhost:8080')
SESION = 'default'
LOTE = 100


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


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def get(ruta, espera=60):
    req = urllib.request.Request(WAHA + ruta, headers={'X-Api-Key': clave(), 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=espera) as r:
            return r.status, json.loads(r.read().decode('utf-8', 'replace') or 'null')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')[:200]
    except Exception as e:  # noqa: BLE001
        return 0, str(e)[:200]


def es_persona(cid):
    return not (cid.endswith('@g.us') or cid.startswith('status@') or cid.endswith('@newsletter')
                or cid.endswith('@broadcast'))


def nombres_de_contactos():
    c, datos = get('/api/contacts/all?session=%s' % SESION)
    if c != 200 or not isinstance(datos, list):
        log('(no pude leer los contactos: %s)' % c)
        return {}
    return {str(x.get('id', '')): (x.get('name') or x.get('pushname') or '') for x in datos}


def corto(m):
    """Lo que sirve de cada mensaje, sin el crudo."""
    media = m.get('media') or {}
    cita = m.get('replyTo') or {}
    return {
        'id': m.get('id'), 'ts': m.get('timestamp'), 'yo': bool(m.get('fromMe')),
        'texto': m.get('body') or '', 'media': bool(m.get('hasMedia')),
        'tipo': media.get('mimetype') or m.get('type') or '',
        'cita': ({'id': cita.get('id'), 'texto': cita.get('body') or '', 'de': cita.get('participant')} if cita else None),
    }


def recortar(x, n=600):
    s = json.dumps(x, ensure_ascii=False, default=str)
    return json.loads(s) if len(s) <= n * 10 else s[:n * 10]


def mensajes(cid, maximo):
    vistos, salida, offset = set(), [], 0
    while len(salida) < maximo:
        c, lote = get('/api/%s/chats/%s/messages?limit=%d&offset=%d&downloadMedia=false'
                      % (SESION, urllib.parse.quote(cid), LOTE, offset))
        if c != 200 or not isinstance(lote, list) or not lote:
            if c != 200:
                log('   %s: error %s %s' % (cid[-6:], c, str(lote)[:80]))
            break
        nuevos = [m for m in lote if m.get('id') not in vistos]
        if not nuevos:   # el motor ignora offset: se pide todo de una vez
            c, todo = get('/api/%s/chats/%s/messages?limit=%d&downloadMedia=false'
                          % (SESION, urllib.parse.quote(cid), maximo), espera=180)
            if c == 200 and isinstance(todo, list) and len(todo) > len(salida):
                salida = todo
            break
        for m in nuevos:
            vistos.add(m.get('id'))
        salida.extend(nuevos)
        offset += len(lote)
        if len(lote) < LOTE:
            break
    return salida


def main():
    todos = '--todos' in sys.argv
    maximo = int(sys.argv[sys.argv.index('--max') + 1]) if '--max' in sys.argv else 3000
    if sys.stdout.isatty():
        sys.exit('Mandá la salida a un archivo (> ~/storage/downloads/chats_waha.json.gz)')
    c, chats = get('/api/%s/chats?limit=5000' % SESION, espera=90)
    if c != 200 or not isinstance(chats, list):
        sys.exit('No pude listar los chats de WAHA: %s %s' % (c, str(chats)[:200]))
    agenda = nombres_de_contactos()
    elegidos = []
    for ch in chats:
        cid = str(ch.get('id', ''))
        if not es_persona(cid):
            continue
        nombre = agenda.get(cid) or ch.get('name') or ''
        if todos or nombre.lower().startswith('bexo'):
            elegidos.append((cid, nombre))
    log('%d chats en WAHA, %d de clientes (Bexo)%s' % (len(chats), len(elegidos), ' + todos' if todos else ''))

    salida, crudos, por_mes, total = [], [], {}, 0
    for i, (cid, nombre) in enumerate(elegidos, 1):
        ms = mensajes(cid, maximo)
        for m in ms:
            if len(crudos) < 12 and (m.get('replyTo') or m.get('fromMe') or m.get('hasMedia')):
                crudos.append(recortar(m))   # para ver qué campos trae este WAHA (citas, tuyos, fotos)
        cortos = sorted((corto(m) for m in ms), key=lambda x: x['ts'] or 0)
        for m in cortos:
            if m['ts']:
                mes = time.strftime('%Y-%m', time.gmtime(int(m['ts'])))
                por_mes[mes] = por_mes.get(mes, 0) + 1
        total += len(cortos)
        salida.append({'chat': cid, 'nombre': nombre, 'mensajes': cortos})
        log('%3d/%d %-28s %5d mensajes' % (i, len(elegidos), nombre[:28], len(cortos)))

    log('Total %d mensajes. Por mes: %s' % (total, ', '.join('%s %d' % kv for kv in sorted(por_mes.items()))))
    datos = json.dumps({'chats': salida, 'muestra_cruda': crudos}, ensure_ascii=False, default=str).encode()
    sys.stdout.buffer.write(gzip.compress(datos))


if __name__ == '__main__':
    main()
