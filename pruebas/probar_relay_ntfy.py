#!/usr/bin/env python3
"""Prueba sin red la puerta POST /ntfy del relay del VPS:  python3 pruebas/probar_relay_ntfy.py"""
import json
import os
import sys
import threading
import urllib.error
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, 'vps'))
os.environ['RELAY_TOKEN'] = 'tok'
import relay_binance as rb  # noqa: E402

reenviados = []
abrir_real = urllib.request.urlopen


class Resp:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def falso(req, timeout=15):
    if getattr(req, 'full_url', '').startswith('https://ntfy.sh'):
        reenviados.append(json.loads(req.data))
        return Resp()
    return abrir_real(req, timeout=timeout)


rb.urllib.request.urlopen = falso
srv = rb.ThreadingHTTPServer(('127.0.0.1', 0), rb.Relay)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = 'http://127.0.0.1:%d' % srv.server_address[1]


def pedir(ruta, cuerpo=None, metodo='POST'):
    req = urllib.request.Request(base + ruta, data=None if cuerpo is None else json.dumps(cuerpo).encode(),
                                 method=metodo, headers={'Content-Type': 'application/json'})
    try:
        with abrir_real(req, timeout=5) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


bien = n = 0


def ver(nombre, ok, detalle=''):
    global bien, n
    n += 1
    bien += bool(ok)
    print('%s %s%s' % ('BIEN' if ok else 'MAL ', nombre, ' · %s' % (detalle,) if detalle else ''))


aviso = {'topic': 'bexo-abc', 'title': '💸 Juan P.', 'message': 'x', 'priority': 4,
         'actions': [{'action': 'http', 'label': 'Armar', 'url': 'https://s/exec?p2p=armar'}]}
c, r = pedir('/ntfy?token=tok', aviso)
ver('con token reenvía a ntfy.sh tal cual', c == 200 and r == {'ntfy': 200} and reenviados == [aviso], (c, r))
c, r = pedir('/ntfy?token=mal', aviso)
ver('token equivocado: 403 y no reenvía', c == 403 and len(reenviados) == 1, c)
c, r = pedir('/ntfy?token=tok', dict(aviso, topic='otro-tema'))
ver('tema que no es bexo-: 400 y no reenvía', c == 400 and len(reenviados) == 1, (c, r))
c, r = pedir('/ntfy?token=tok', {'topic': 'bexo-abc-cmd', 'message': 'https://c2c.binance.com/es-LA/adv?code=1'})
ver('comando al tema -cmd', c == 200 and reenviados[-1]['topic'] == 'bexo-abc-cmd', c)
c, r = pedir('/otra?token=tok', aviso)
ver('otra ruta por POST: 403', c == 403, c)
c, r = pedir('/anuncios?token=mal', metodo='GET')
ver('los GET siguen pidiendo token', c == 403, c)
srv.shutdown()
print('%d de %d bien' % (bien, n))
sys.exit(0 if bien == n else 1)
