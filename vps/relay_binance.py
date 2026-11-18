#!/usr/bin/env python3
"""Relay de solo lectura: Apps Script -> este VPS -> Binance P2P.

Binance bloquea las IPs de Apps Script; este VPS sí llega.
GET /anuncios?token=XXX&fiat=VES&tipo=SELL&pago=PagoMovil&filas=10&monto=50000   (público, sin clave)
GET /contrapartes?token=XXX&dias=180   (tu historial; usa BINANCE_KEY/BINANCE_SECRET de SOLO LECTURA)
La clave de Binance vive solo en /etc/relay-binance.env: nunca sale del VPS.
"""
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = os.environ['RELAY_TOKEN']
PUERTO = int(os.environ.get('RELAY_PUERTO', '8082'))
BINANCE = 'https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search'
HISTORIAL = 'https://api.binance.com/sapi/v1/c2c/orderMatch/listUserOrderHistory'
DIA_MS = 24 * 3600 * 1000


def buscar_anuncios(fiat, tipo, pago, filas, monto):
    cuerpo = {
        'asset': 'USDT', 'fiat': fiat, 'tradeType': tipo,
        'page': 1, 'rows': filas, 'payTypes': [pago] if pago else [],
    }
    if monto:
        cuerpo['transAmount'] = monto
    req = urllib.request.Request(
        BINANCE, data=json.dumps(cuerpo).encode(),
        headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=15) as r:
        datos = json.load(r).get('data') or []
    # Solo lo necesario; nada de datos personales del anunciante.
    return [{
        'precio': float(a['adv']['price']),
        'min': float(a['adv']['minSingleTransAmount']),
        'max': float(a['adv']['dynamicMaxSingleTransAmount']),
        'disponible': float(a['adv']['tradableQuantity']),
        'pagos': [m.get('identifier') for m in a['adv'].get('tradeMethods', [])],
        'adNo': a['adv']['advNo'],
        'apodo': a['advertiser']['nickName'],
        'ordenesMes': a['advertiser'].get('monthOrderCount'),
        'cumplimiento': a['advertiser'].get('monthFinishRate'),
        'descripcion': (a['adv'].get('remarks') or '')[:600],
    } for a in datos]


def firmar_y_pedir(url, params):
    key, secret = os.environ['BINANCE_KEY'], os.environ['BINANCE_SECRET']
    params = dict(params, recvWindow=10000, timestamp=int(time.time() * 1000))
    query = urllib.parse.urlencode(params)
    firma = hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()
    req = urllib.request.Request(url + '?' + query + '&signature=' + firma,
                                 headers={'X-MBX-APIKEY': key})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def historial(dias):
    """Órdenes P2P de los últimos `dias` (Binance da hasta 180, en ventanas de 30)."""
    ordenes, fin = [], int(time.time() * 1000)
    inicio_total = fin - min(dias, 180) * DIA_MS
    while fin > inicio_total:
        ini = max(fin - 30 * DIA_MS + 1, inicio_total)
        for tipo in ('BUY', 'SELL'):
            pagina = 1
            while True:
                r = firmar_y_pedir(HISTORIAL, {'tradeType': tipo, 'startTimestamp': ini,
                                               'endTimestamp': fin, 'page': pagina, 'rows': 100})
                datos = r.get('data') or []
                ordenes.extend(datos)
                if len(datos) < 100:
                    break
                pagina += 1
                time.sleep(0.3)
        fin = ini - 1
    return ordenes


def contrapartes(dias):
    """Agrupa las órdenes COMPLETADAS por apodo de la contraparte."""
    por_apodo = {}
    for o in historial(dias):
        if o.get('orderStatus') != 'COMPLETED':
            continue
        c = por_apodo.setdefault(o.get('counterPartNickName') or '?', {
            'apodo': o.get('counterPartNickName') or '?', 'ordenes': 0, 'usdt': 0.0,
            'ultima': 0, 'fiats': set(), 'tipos': set(), 'anuncios': set()})
        c['ordenes'] += 1
        c['usdt'] += float(o.get('amount') or 0)
        c['ultima'] = max(c['ultima'], int(o.get('createTime') or 0))
        c['fiats'].add(o.get('fiat'))
        c['tipos'].add(o.get('tradeType'))
        if o.get('advertisementRole') == 'TAKER':
            c['anuncios'].add(o.get('advNo'))   # el anuncio era de la contraparte
    lista = sorted(por_apodo.values(), key=lambda c: -c['ordenes'])
    for c in lista:
        for k in ('fiats', 'tipos', 'anuncios'):
            c[k] = sorted(x for x in c[k] if x)
        c['usdt'] = round(c['usdt'], 2)
    return lista

DETALLE = 'https://p2p.binance.com/bapi/c2c/v2/public/c2c/adv/selected-adv/'


def descripcion(adv_no):
    """Texto de condiciones del anuncio (remarks). La búsqueda no lo trae; el detalle sí."""
    if not adv_no.isdigit():
        raise ValueError('adNo inválido')
    req = urllib.request.Request(DETALLE + adv_no, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=15) as r:
        datos = json.load(r).get('data')

    def hallar(o):
        if isinstance(o, dict):
            if isinstance(o.get('remarks'), str):
                return o['remarks']
            for v in o.values():
                h = hallar(v)
                if h:
                    return h
        elif isinstance(o, list):
            for v in o:
                h = hallar(v)
                if h:
                    return h
        return ''
    return hallar(datos)[:1000]


class Relay(BaseHTTPRequestHandler):
    # Una conexión que se abre y no manda nada (bots que escanean puertos) se corta a los 30 s.
    # Antes no tenía límite y, como atendía de a uno, dejaba colgado al relay para todos.
    timeout = 30

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        if q.get('token') != TOKEN or url.path not in ('/anuncios', '/contrapartes', '/descripcion'):
            return self.responder(403, {'error': 'no autorizado'})
        if url.path == '/descripcion':
            try:
                return self.responder(200, {'descripcion': descripcion(q.get('adNo', ''))})
            except Exception as e:
                return self.responder(502, {'error': str(e)})
        if url.path == '/contrapartes':
            try:
                return self.responder(200, {'contrapartes': contrapartes(int(q.get('dias', '180')))})
            except urllib.error.HTTPError as e:
                return self.responder(502, {'error': 'Binance %s: %s' % (e.code, e.read()[:300].decode('utf-8', 'replace'))})
            except Exception as e:
                return self.responder(502, {'error': str(e)})
        try:
            anuncios = buscar_anuncios(
                fiat=q.get('fiat', 'VES').upper(),
                tipo=q.get('tipo', 'SELL').upper(),
                pago=q.get('pago', ''),
                filas=min(int(q.get('filas', '10')), 20),
                monto=q.get('monto', ''))
            self.responder(200, {'anuncios': anuncios})
        except Exception as e:
            self.responder(502, {'error': str(e)})

    def responder(self, codigo, obj):
        cuerpo = json.dumps(obj).encode()
        self.send_response(codigo)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def log_message(self, fmt, *args):
        # No loguear la URL: lleva el token.
        print('%s %s' % (self.address_string(), self.command), flush=True)


if __name__ == '__main__':
    # Atiende cada pedido en su propio hilo: uno lento (Binance tarda, o un bot) no frena a los demás.
    servidor = ThreadingHTTPServer(('0.0.0.0', PUERTO), Relay)
    servidor.daemon_threads = True
    servidor.serve_forever()
