#!/usr/bin/env python3
"""Sube tus órdenes P2P de Bybit a la planilla (hoja Ordenes_P2P, Exchange = Bybit). Solo lectura en Bybit.

Corre en el teléfono: Bybit bloquea las IP de EE.UU., así que el VPS y Apps Script no sirven.
Las órdenes se unen por número de orden con las que ya están (las del export no se repiten).

  python bybit_ordenes.py --probar        # no sube nada: muestra cuántas órdenes hay y las últimas 5
  python bybit_ordenes.py --dias 120      # primera carga (todo lo que haya)
  python bybit_ordenes.py                 # lo de cada 4 horas (telefono/subir.sh): últimos 7 días

Usa BYBIT_KEY, BYBIT_SECRET, WEBAPP_URL y ORDENES_TOKEN de ~/.subir-ordenes.env.
"""
import argparse
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
POR_PAGINA = 30
DIA_MS = 24 * 3600 * 1000
# Estados de Bybit (número) → los nombres que entiende estadoP2P_ del Apps Script. El resto queda "En curso".
ESTADOS = {50: 'COMPLETED', 40: 'CANCELLED', 80: 'CANCELLED', 30: 'IN_APPEAL', 100: 'IN_APPEAL'}

_desfase_ms = None
_desfase_cuando = 0


def hora_bybit_ms():
    """Hora según Bybit (si el reloj del teléfono está corrido, Bybit rechaza la firma). Se vuelve a medir cada
    10 min: la alarma corre días seguidos y el reloj del teléfono se corre."""
    global _desfase_ms, _desfase_cuando
    if _desfase_ms is None or time.time() - _desfase_cuando > 600:
        with urllib.request.urlopen(BASE + '/v5/market/time', timeout=20) as r:
            _desfase_ms = int(json.loads(r.read())['time']) - int(time.time() * 1000)
        _desfase_cuando = time.time()
    return int(time.time() * 1000) + _desfase_ms


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
            res = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit('Bybit %s: %s' % (e.code, e.read()[:300].decode('utf-8', 'replace')))
    # El P2P de Bybit responde ret_code/ret_msg (el resto de la API usa retCode/retMsg).
    codigo = res.get('ret_code', res.get('retCode'))
    if codigo not in (0, '0'):
        raise SystemExit('Bybit %s: %s' % (codigo, res.get('ret_msg') or res.get('retMsg')))
    return res.get('result') or {}


def ordenes(cfg, dias):
    """Órdenes creadas en los últimos `dias`. Bybit las da de la más nueva a la más vieja, de a páginas."""
    desde = hora_bybit_ms() - dias * DIA_MS
    lista, pagina = [], 1
    while True:
        r = pedir(cfg, '/v5/p2p/order/simplifyList', {'page': pagina, 'size': POR_PAGINA})
        items = r.get('items') or []
        lista.extend(o for o in items if int(o.get('createDate') or 0) >= desde)
        viejas = [o for o in items if int(o.get('createDate') or 0) < desde]
        if not items or viejas or pagina * POR_PAGINA >= int(r.get('count') or 0):
            break
        pagina += 1
        time.sleep(0.3)
    return [{
        'numero': str(o.get('id')),
        'tipo': 'BUY' if str(o.get('side')) == '0' else 'SELL',
        'activo': o.get('tokenId') or '',
        'fiat': o.get('currencyId') or '',
        'total': float(o.get('amount') or 0),
        'precio': float(o.get('price') or 0),
        'cantidad': float(o.get('notifyTokenQuantity') or 0),
        'contraparte': o.get('targetNickName') or '',
        'estado': ESTADOS.get(int(o.get('status') or 0), 'EN_CURSO'),
        'hora': int(o.get('createDate') or 0),
        'comision': float(o.get('fee') or 0),
    } for o in lista]


def _buscar(obj, clave):
    """Primer valor de `clave` en cualquier nivel de un JSON (Bybit anida el método de pago)."""
    if isinstance(obj, dict):
        if obj.get(clave):
            return obj[clave]
        obj = list(obj.values())
    if isinstance(obj, list):
        for v in obj:
            hallado = _buscar(v, clave)
            if hallado:
                return hallado
    return None


_detalles = {}


def pendientes(cfg):
    """Órdenes P2P de Bybit sin terminar, con la forma de las de Binance para que la alarma las trate igual.
    Estados de Bybit: 10 = esperando que pague el comprador, 20 = pagada (falta liberar). Si sos el anunciante
    (makerUserId) va advertisementRole=MAKER; el detalle se pide una sola vez por orden."""
    r = pedir(cfg, '/v5/p2p/order/pending/simplifyList', {'page': 1, 'size': POR_PAGINA})
    lista = []
    for o in r.get('items') or []:
        n = str(o.get('id'))
        if n not in _detalles:
            try:
                _detalles[n] = pedir(cfg, '/v5/p2p/order/info', {'orderId': n})
            except SystemExit:
                _detalles[n] = {}
        d = _detalles[n]
        if d.get('makerUserId') and d.get('userId'):
            rol = 'MAKER' if str(d['makerUserId']) == str(d['userId']) else 'TAKER'
        else:
            rol = 'MAKER'                  # sin dato: mejor que suene de más que de menos
        estado = {10: 'TRADING', 20: 'BUYER_PAYED'}.get(int(o.get('status') or 0), 'OTRO')
        lista.append({'orderNumber': n, 'tradeType': 'BUY' if str(o.get('side')) == '0' else 'SELL',
                      'orderStatus': estado, 'advertisementRole': rol, 'totalPrice': o.get('amount'),
                      'fiat': o.get('currencyId') or '', 'amount': o.get('notifyTokenQuantity'),
                      'asset': o.get('tokenId') or '', 'createTime': int(o.get('createDate') or 0),
                      'payMethodName': _buscar(d, 'paymentName') or '', 'exchange': 'Bybit'})
    vivas = {o['orderNumber'] for o in lista}
    for n in list(_detalles):
        if n not in vivas:
            del _detalles[n]
    return lista


def subir(cfg, lista):
    cuerpo = json.dumps({'ordenesBybit': lista, 'token': cfg['ORDENES_TOKEN']}).encode()
    req = urllib.request.Request(cfg['WEBAPP_URL'], data=cuerpo, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=120) as r:   # Apps Script responde 302; urllib lo sigue
        return r.read().decode('utf-8', 'replace')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--dias', type=int, default=7)
    ap.add_argument('--probar', action='store_true')
    args = ap.parse_args()
    cfg = leer_env()
    if not cfg.get('BYBIT_KEY') or not cfg.get('BYBIT_SECRET'):
        raise SystemExit('Falta BYBIT_KEY o BYBIT_SECRET en ~/.subir-ordenes.env')
    lista = ordenes(cfg, 120 if args.probar else args.dias)
    if args.probar:
        print('Bybit, últimos 120 días: %d órdenes (compras %d, ventas %d, completadas %d)' % (
            len(lista), sum(o['tipo'] == 'BUY' for o in lista), sum(o['tipo'] == 'SELL' for o in lista),
            sum(o['estado'] == 'COMPLETED' for o in lista)))
        for o in lista[:5]:
            print(time.strftime('%d/%m %H:%M', time.localtime(o['hora'] / 1000)), o['numero'], o['tipo'],
                  o['cantidad'], o['activo'], '=', o['total'], o['fiat'], '@', o['precio'], o['contraparte'], o['estado'])
    else:
        print(time.strftime('%Y-%m-%d %H:%M'), 'Bybit:', len(lista), 'órdenes ->', subir(cfg, lista)[:300], flush=True)
