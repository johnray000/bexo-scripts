#!/usr/bin/env python3
"""Prueba la API key de Bybit (solo lectura, P2P): pide tus últimas órdenes P2P y muestra lo que devuelve.

Corre en el teléfono (Bybit bloquea las IP de EE.UU., así que el VPS y Apps Script no sirven).
Usa BYBIT_KEY y BYBIT_SECRET de ~/.subir-ordenes.env.

  python bybit_probar.py
"""
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from subir_ordenes import leer_env  # noqa: E402

BASE = 'https://api.bybit.com'
RECV = '20000'


def hora_bybit_ms():
    with urllib.request.urlopen(BASE + '/v5/market/time', timeout=20) as r:
        return int(json.loads(r.read())['time'])


def pedir(cfg, ruta, cuerpo):
    datos = json.dumps(cuerpo, separators=(',', ':'))
    ts = str(hora_bybit_ms())
    firma = hmac.new(cfg['BYBIT_SECRET'].encode(), (ts + cfg['BYBIT_KEY'] + RECV + datos).encode(),
                     hashlib.sha256).hexdigest()
    req = urllib.request.Request(BASE + ruta, data=datos.encode(), method='POST', headers={
        'Content-Type': 'application/json', 'X-BAPI-API-KEY': cfg['BYBIT_KEY'], 'X-BAPI-SIGN': firma,
        'X-BAPI-SIGN-TYPE': '2', 'X-BAPI-TIMESTAMP': ts, 'X-BAPI-RECV-WINDOW': RECV})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')


if __name__ == '__main__':
    cfg = leer_env()
    if not cfg.get('BYBIT_KEY') or not cfg.get('BYBIT_SECRET'):
        raise SystemExit('Falta BYBIT_KEY o BYBIT_SECRET en ~/.subir-ordenes.env')
    estado, texto = pedir(cfg, '/v5/p2p/order/simplifyList', {'page': 1, 'size': 5})
    print('HTTP', estado)
    try:
        r = json.loads(texto)
    except ValueError:
        print(texto[:1000])
        sys.exit(1)
    print('retCode:', r.get('retCode'), r.get('retMsg'))
    items = (r.get('result') or {}).get('items') or []
    print('Órdenes en la respuesta:', len(items), '| total:', (r.get('result') or {}).get('count'))
    for o in items[:2]:
        print(json.dumps(o, ensure_ascii=False, indent=1))
