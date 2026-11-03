#!/usr/bin/env python3
"""Prueba: ¿la API común de OKX (key de solo lectura, sin ser merchant) muestra tus operaciones P2P?

Mira los movimientos de tu cuenta Funding (por donde pasa el P2P) de los últimos 3 meses y muestra
cuántos hay de cada tipo, con un ejemplo de cada uno. No sube nada a la planilla.

  python okx_probar.py

Lee de ~/.subir-ordenes.env: OKX_KEY, OKX_SECRET, OKX_PASSPHRASE.
"""
import base64
import collections
import datetime
import hashlib
import hmac
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from subir_ordenes import leer_env  # noqa: E402

BASE = 'https://www.okx.com'


def pedir(cfg, ruta, params):
    ruta = ruta + '?' + urllib.parse.urlencode(params)
    hora = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    firma = base64.b64encode(hmac.new(cfg['OKX_SECRET'].encode(), (hora + 'GET' + ruta).encode(),
                                      hashlib.sha256).digest()).decode()
    req = urllib.request.Request(BASE + ruta, headers={
        'OK-ACCESS-KEY': cfg['OKX_KEY'], 'OK-ACCESS-SIGN': firma,
        'OK-ACCESS-TIMESTAMP': hora, 'OK-ACCESS-PASSPHRASE': cfg['OKX_PASSPHRASE']})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            res = json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit('OKX %s: %s' % (e.code, e.read()[:300].decode('utf-8', 'replace')))
    if res.get('code') != '0':
        raise SystemExit('OKX: %s' % json.dumps(res)[:300])
    return res.get('data') or []


if __name__ == '__main__':
    cfg = leer_env()
    movs, despues = [], None
    for _ in range(30):                     # hasta 3.000 movimientos, de a 100
        p = {'limit': 100}
        if despues:
            p['after'] = despues
        datos = pedir(cfg, '/api/v5/asset/bills', p)
        movs += datos
        if len(datos) < 100:
            break
        despues = datos[-1]['billId']
    tipos = collections.defaultdict(list)
    for m in movs:
        tipos[m.get('type')].append(m)
    print('Movimientos en Funding:', len(movs))
    for t, lista in sorted(tipos.items(), key=lambda x: -len(x[1])):
        print('\nTipo %s: %d movimientos. Ejemplo:' % (t, len(lista)))
        print(json.dumps(lista[0], ensure_ascii=False))
