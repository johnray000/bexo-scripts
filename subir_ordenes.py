#!/usr/bin/env python3
"""Sube tus órdenes P2P de Binance a la planilla (solo lectura en Binance).

Corre en una VM FUERA de EE.UU.: api.binance.com responde 451 al VPS de WAHA (us-central1).
No abre ningún puerto: solo llama a Binance y después manda las órdenes al Apps Script (doPost).

  python3 subir_ordenes.py --probar        # no sube nada: muestra cuántas órdenes hay y un apodo
  python3 subir_ordenes.py --dias 180      # primera carga (lo máximo que da Binance)
  python3 subir_ordenes.py                 # lo de todas las noches: últimos 3 días

Lee /etc/subir-ordenes.env (VM) o ~/.subir-ordenes.env (teléfono, Termux): BINANCE_KEY, BINANCE_SECRET, WEBAPP_URL, ORDENES_TOKEN.
"""
import argparse
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

ENV = '/etc/subir-ordenes.env'
if not os.path.exists(ENV):
    ENV = os.path.expanduser('~/.subir-ordenes.env')
HISTORIAL = 'https://api.binance.com/sapi/v1/c2c/orderMatch/listUserOrderHistory'
DIA_MS = 24 * 3600 * 1000


def leer_env():
    cfg = {}
    with open(ENV) as f:
        for linea in f:
            if '=' in linea and not linea.startswith('#'):
                k, v = linea.strip().split('=', 1)
                cfg[k] = v
    return cfg


_desfase_ms = None
_desfase_cuando = 0
RESINCRONIZAR_S = 10 * 60


def hora_binance_ms(forzar=False):
    """Hora según Binance: si el reloj del teléfono está adelantado, Binance rechaza la firma (-1021).
    La diferencia se vuelve a medir cada 10 min: el reloj del teléfono se corre (o Android lo corrige de golpe al
    despertar) y la alarma, que corre días seguidos, quedaba con la diferencia vieja y daba -1021 sin parar."""
    global _desfase_ms, _desfase_cuando
    if forzar or _desfase_ms is None or time.time() - _desfase_cuando > RESINCRONIZAR_S:
        with urllib.request.urlopen('https://api.binance.com/api/v3/time', timeout=10) as r:
            _desfase_ms = json.load(r)['serverTime'] - int(time.time() * 1000)
        _desfase_cuando = time.time()
    # 2 s de margen hacia atrás: Binance acepta hasta 10 s de atraso (recvWindow) pero ni 1 s de adelanto.
    return int(time.time() * 1000) + _desfase_ms - 2000


def firmar_y_pedir(cfg, params, _reintento=True):
    base = params
    params = dict(params, recvWindow=10000, timestamp=hora_binance_ms())
    query = urllib.parse.urlencode(params)
    firma = hmac.new(cfg['BINANCE_SECRET'].encode(), query.encode(), hashlib.sha256).hexdigest()
    req = urllib.request.Request(HISTORIAL + '?' + query + '&signature=' + firma,
                                 headers={'X-MBX-APIKEY': cfg['BINANCE_KEY']})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        # Binance explica el error en el cuerpo (code y msg); sin esto solo se ve "400".
        cuerpo = e.read()[:300].decode('utf-8', 'replace')
        if '-1021' in cuerpo and _reintento:   # hora corrida: medir de nuevo y probar una vez más
            hora_binance_ms(forzar=True)
            return firmar_y_pedir(cfg, base, _reintento=False)
        raise SystemExit('Binance %s: %s' % (e.code, cuerpo))


def ordenes(cfg, dias):
    """Órdenes de los últimos `dias` (máx. 180), en ventanas de 30 días, compras y ventas."""
    lista, fin = [], hora_binance_ms()
    inicio_total = fin - min(dias, 180) * DIA_MS
    while fin > inicio_total:
        ini = max(fin - 30 * DIA_MS + 1, inicio_total)
        for tipo in ('BUY', 'SELL'):
            pagina = 1
            while True:
                r = firmar_y_pedir(cfg, {'tradeType': tipo, 'startTimestamp': ini,
                                         'endTimestamp': fin, 'page': pagina, 'rows': 100})
                datos = r.get('data') or []
                lista.extend(datos)
                if not datos:
                    break
                pagina += 1
                time.sleep(0.3)
        fin = ini - 1
    return [{
        'numero': str(o.get('orderNumber')),
        'tipo': o.get('tradeType'),
        'activo': o.get('asset'),
        'fiat': o.get('fiat'),
        'total': float(o.get('totalPrice') or 0),
        'precio': float(o.get('unitPrice') or 0),
        'cantidad': float(o.get('amount') or 0),
        'contraparte': o.get('counterPartNickName') or '',
        'estado': o.get('orderStatus'),
        'hora': int(o.get('createTime') or 0),
        'anuncio': str(o.get('advNo') or ''),
        'comision': o.get('commission') if o.get('commission') not in (None, '') else o.get('takerCommission', ''),
        'rol': o.get('advertisementRole') or '',
    } for o in lista]


def subir(cfg, lista, desde):
    cuerpo = json.dumps({'ordenesP2P': lista, 'desde': desde, 'token': cfg['ORDENES_TOKEN']}).encode()
    req = urllib.request.Request(cfg['WEBAPP_URL'], data=cuerpo,
                                 headers={'Content-Type': 'application/json'})
    # Apps Script responde con un 302; urllib lo sigue con GET y ahí está la respuesta.
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read().decode('utf-8', 'replace')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--dias', type=int, default=3)
    ap.add_argument('--probar', action='store_true')
    args = ap.parse_args()
    cfg = leer_env()
    dias = 30 if args.probar else args.dias
    desde = hora_binance_ms() - min(dias, 180) * DIA_MS
    lista = ordenes(cfg, dias)
    if args.probar:
        ves = [o for o in lista if o['fiat'] == 'VES' and o['tipo'] == 'SELL']
        print('Compras:', sum(o['tipo'] == 'BUY' for o in lista), '| Ventas:', sum(o['tipo'] == 'SELL' for o in lista))
        print('Órdenes últimos 30 días: %d (ventas VES: %d)' % (len(lista), len(ves)))
        print('Apodos de ejemplo:', [o['contraparte'] for o in ves[:5]])
    else:
        print(time.strftime('%Y-%m-%d %H:%M'), len(lista), 'órdenes ->', subir(cfg, lista, desde)[:300], flush=True)
