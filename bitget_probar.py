#!/usr/bin/env python3
"""Prueba: ¿la API de Bitget (key de solo lectura, sin ser anunciante) muestra tu progreso P2P?

Pregunta tres cosas y muestra lo que contesta Bitget a cada una. No sube nada a la planilla.
  1) Tu perfil P2P (/api/v2/p2p/merchantInfo): órdenes y tasa de los últimos 30 días, fecha de alta, KYC.
  2) Tus órdenes P2P (/api/v2/p2p/orderList) de los últimos 6 meses: con eso salen usuarios distintos y volumen.
  3) Los anuncios públicos de compra de USDT con ARS (/api/v3/p2p/ad-list).
Al final arma los números de la tarjeta "Habilitar anuncios en Bitget".

  python bitget_probar.py

Lee de ~/.subir-ordenes.env: BITGET_KEY, BITGET_SECRET, BITGET_PASSPHRASE.
"""
import base64
import datetime
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from subir_ordenes import leer_env  # noqa: E402

BASE = 'https://api.bitget.com'
DIA_MS = 24 * 3600 * 1000


def pedir(cfg, ruta, params):
    """GET firmado. Devuelve (datos, None) si anduvo o (None, 'motivo') si Bitget dijo que no."""
    query = urllib.parse.urlencode(params)
    ruta_q = ruta + ('?' + query if query else '')
    hora = str(int(time.time() * 1000))
    firma = base64.b64encode(hmac.new(cfg['BITGET_SECRET'].encode(), (hora + 'GET' + ruta_q).encode(),
                                      hashlib.sha256).digest()).decode()
    req = urllib.request.Request(BASE + ruta_q, headers={
        'ACCESS-KEY': cfg['BITGET_KEY'], 'ACCESS-SIGN': firma, 'ACCESS-TIMESTAMP': hora,
        'ACCESS-PASSPHRASE': cfg['BITGET_PASSPHRASE'], 'Content-Type': 'application/json', 'locale': 'es-ES'})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            res = json.load(r)
    except urllib.error.HTTPError as e:
        return None, 'HTTP %s: %s' % (e.code, e.read()[:300].decode('utf-8', 'replace'))
    except urllib.error.URLError as e:
        return None, 'sin conexión: %s' % e.reason
    if str(res.get('code')) != '00000':
        return None, json.dumps(res, ensure_ascii=False)[:300]
    return res.get('data'), None


def titulo(t):
    print('\n=== ' + t + ' ===')


def ordenes(cfg, desde_ms, hasta_ms):
    """Todas las órdenes entre dos fechas, en tramos de 90 días (lo máximo que deja Bitget)."""
    todas, inicio = [], desde_ms
    while inicio < hasta_ms:
        fin = min(inicio + 90 * DIA_MS - 1, hasta_ms)
        menor = None
        for _ in range(30):
            p = {'startTime': inicio, 'endTime': fin, 'limit': 100}
            if menor:
                p['idLessThan'] = menor
            datos, error = pedir(cfg, '/api/v2/p2p/orderList', p)
            if error:
                return None, error
            lista = (datos or {}).get('orderList') or []
            todas += lista
            menor = (datos or {}).get('minOrderId')
            if len(lista) < 100 or not menor:
                break
        inicio = fin + 1
    return todas, None


if __name__ == '__main__':
    cfg = leer_env()
    faltan = [k for k in ('BITGET_KEY', 'BITGET_SECRET', 'BITGET_PASSPHRASE') if not cfg.get(k)]
    if faltan:
        raise SystemExit('Faltan en ~/.subir-ordenes.env: ' + ', '.join(faltan))
    ahora = int(time.time() * 1000)

    titulo('1) Tu perfil P2P')
    perfil, error = pedir(cfg, '/api/v2/p2p/merchantInfo', {})
    print(error and ('No: ' + error) or json.dumps(perfil, ensure_ascii=False))

    titulo('2) Tus órdenes P2P de los últimos 6 meses')
    lista, error = ordenes(cfg, ahora - 180 * DIA_MS, ahora)
    if error:
        print('No: ' + error)
    else:
        print('Órdenes:', len(lista))
        if lista:
            print('Ejemplo:', json.dumps(lista[0], ensure_ascii=False))

    titulo('3) Anuncios públicos: comprar USDT con ARS')
    ads, error = pedir(cfg, '/api/v3/p2p/ad-list',
                       {'token': 'USDT', 'fiat': 'ARS', 'side': 'sell', 'pageNum': 1, 'limit': 5})
    print(error and ('No: ' + error) or json.dumps(ads, ensure_ascii=False)[:1500])

    titulo('Números para la tarjeta')
    if lista is not None:
        hechas = [o for o in lista if str(o.get('status', '')).lower() == 'completed']
        h30 = [o for o in hechas if int(o.get('ctime') or 0) >= ahora - 30 * DIA_MS]
        contra = set()
        for o in h30:
            nombre = o.get('sellerRealName') if o.get('side') == 'buy' else o.get('buyerRealName')
            contra.add(nombre or '?')
        vol = sum(float(o.get('count') or 0) for o in hechas if o.get('coin') == 'USDT')
        print('Órdenes completadas (30 días): %d de 5' % len(h30))
        print('Usuarios distintos (30 días): %d de 5' % len(contra))
        print('Volumen USDT (6 meses): %.2f de 500' % vol)
    if perfil:
        print('Tasa de finalización (30 días): %s (pide 80 %%)' % perfil.get('completionRate30d'))
        alta = int(perfil.get('registerTime') or 0)
        if alta:
            dias = (ahora - alta) // DIA_MS
            print('Alta: %s, hace %d días (pide 30)' % (
                datetime.datetime.fromtimestamp(alta / 1000).strftime('%d/%m/%Y'), dias))
    print('\nMandale todo esto a Claude.')
