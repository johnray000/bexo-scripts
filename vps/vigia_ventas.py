#!/usr/bin/env python3
"""Vigía de órdenes P2P en el VPS: el que lee Binance es el VPS (no duerme), el teléfono solo suena.

Cada 5 min (de 1 a 10 de la mañana, hora UY, cada 15 min) mira tus órdenes con la key de SOLO LECTURA del relay
(/etc/relay-binance.env) y, si hay que avisar, le manda al teléfono la orden de sonar por ntfy (tema <T>-alarma;
lo escucha alerta_compras.py). El teléfono suena y contesta "sonó" (tema <T>-alarma-ok).
  - VENTA nueva en tu anuncio: suena al 75%; si a los 10 min sigue sin pagar, una vez más al máximo. Nada más.
  - COMPRA abierta en tu anuncio esperando tu pago: suena en cada vuelta hasta que pagues.
Si en 90 s el teléfono no contestó (bloqueado y dormido, sin internet…), recién ahí manda una notificación visible
de ntfy (tema <T>, prioridad máxima): esa sí despierta al teléfono.
Cada ~15 min deja una "señal de vida" en <T>-vigia, solo si pudo leer Binance. Si el teléfono no la ve en 35 min,
vuelve a leer Binance él solo (respaldo) hasta que el VPS vuelva.

Config: NTFY_TOPIC en /etc/vigia-ventas.env (el mismo de ~/.bexo-ntfy del teléfono).
  python3 vigia_ventas.py            # queda corriendo (servicio vigia-ventas)
  python3 vigia_ventas.py --probar   # lee Binance una vez, le pide al teléfono un sonido de prueba y espera el "sonó"
"""
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HISTORIAL = 'https://api.binance.com/sapi/v1/c2c/orderMatch/listUserOrderHistory'
NTFY = 'https://ntfy.sh'
CADA_S, CADA_NOCHE_S = 5 * 60, 15 * 60
NOCHE = (1, 10)                      # de 1:00 a 9:59 hora de Uruguay
UY_UTC = -3
RECORDAR_S = 10 * 60
ESPERA_OK_S = 90
VIDA_S = 14 * 60
ESPERANDO = ('PENDING', 'TRADING')
BANCOS = (('prex', 'Prex'), ('itau', 'Itaú'), ('midinero', 'Mi Dinero'), ('redpagos', 'Mi Dinero'),
          ('mercado', 'Mercado Pago'), ('oca', 'OCA'))


def leer_env(*rutas):
    """KEY=valor de los archivos (con systemd ya vienen en el entorno; esto es para correrlo a mano)."""
    for ruta in rutas:
        try:
            with open(ruta) as f:
                for linea in f:
                    if '=' in linea and not linea.lstrip().startswith('#'):
                        k, v = linea.strip().split('=', 1)
                        os.environ.setdefault(k, v.strip().strip('"'))
        except OSError:
            pass


def hora_uy(t=None):
    return time.gmtime((t or time.time()) + UY_UTC * 3600).tm_hour


def pausa(t=None):
    return CADA_NOCHE_S if NOCHE[0] <= hora_uy(t) < NOCHE[1] else CADA_S


_desfase_ms = None


def hora_binance_ms():
    global _desfase_ms
    if _desfase_ms is None:
        with urllib.request.urlopen('https://api.binance.com/api/v3/time', timeout=10) as r:
            _desfase_ms = json.load(r)['serverTime'] - int(time.time() * 1000)
    return int(time.time() * 1000) + _desfase_ms - 2000


def mis_ordenes(tipo):
    """Órdenes de TUS anuncios (MAKER) de las últimas 2 h, esperando pago."""
    ahora = hora_binance_ms()
    params = {'tradeType': tipo, 'startTimestamp': ahora - 2 * 3600 * 1000, 'endTimestamp': ahora,
              'page': 1, 'rows': 50, 'recvWindow': 10000, 'timestamp': ahora}
    query = urllib.parse.urlencode(params)
    firma = hmac.new(os.environ['BINANCE_SECRET'].encode(), query.encode(), hashlib.sha256).hexdigest()
    req = urllib.request.Request(HISTORIAL + '?' + query + '&signature=' + firma,
                                 headers={'X-MBX-APIKEY': os.environ['BINANCE_KEY']})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            datos = json.load(r).get('data') or []
    except urllib.error.HTTPError as e:
        raise RuntimeError('Binance %s: %s' % (e.code, e.read()[:200].decode('utf-8', 'replace')))
    return [o for o in datos if o.get('orderStatus') in ESPERANDO and o.get('advertisementRole') != 'TAKER']


def tema(sufijo=''):
    return os.environ['NTFY_TOPIC'] + sufijo


def publicar(topic, mensaje, titulo=None, prioridad=None, tags=()):
    cuerpo = {'topic': topic, 'message': mensaje}
    if titulo:
        cuerpo['title'] = titulo
    if prioridad:
        cuerpo['priority'] = prioridad
    if tags:
        cuerpo['tags'] = list(tags)
    req = urllib.request.Request(NTFY, data=json.dumps(cuerpo).encode(), headers={'Content-Type': 'application/json'})
    urllib.request.urlopen(req, timeout=15).read()


def oks_desde(desde):
    """Ids que el teléfono confirmó como "sonó" desde el segundo `desde`."""
    url = '%s/%s/json?poll=1&since=%d' % (NTFY, tema('-alarma-ok'), int(desde))
    with urllib.request.urlopen(url, timeout=15) as r:
        return {json.loads(l).get('message', '').strip() for l in r if l.strip()}


def banco(o):
    crudo = str(o.get('payMethodName') or '')
    plano = crudo.lower().replace('ú', 'u').replace(' ', '').replace('_', '')
    return next((lindo for clave, lindo in BANCOS if clave in plano), crudo)


def monto_txt(o):
    try:
        monto = '{:,}'.format(int(float(o.get('totalPrice')))).replace(',', '.')
    except (TypeError, ValueError):
        monto = str(o.get('totalPrice'))
    return '%s %s' % (monto, o.get('fiat') or '')


def comando(o, clase, fuerte):
    """Lo que viaja al teléfono: lo justo para sonar (sin apodos)."""
    return {'id': '%s-%s-%d' % (str(o.get('orderNumber'))[-9:], clase, int(time.time())), 'clase': clase,
            'fuerte': fuerte, 'orderNumber': str(o.get('orderNumber')), 'totalPrice': o.get('totalPrice'),
            'fiat': o.get('fiat'), 'amount': o.get('amount'), 'asset': o.get('asset'),
            'createTime': o.get('createTime'), 'payMethodName': o.get('payMethodName')}


def que_avisar(ordenes, avisadas, ahora):
    """ordenes: [(orden, 'venta'|'compra')]. avisadas: orden → [primera vez, veces]. Devuelve los comandos."""
    cmds = []
    for o, clase in ordenes:
        n = str(o.get('orderNumber'))
        primera, veces = avisadas.get(n, (ahora, 0))
        if clase == 'venta':
            if veces == 0:
                cmds.append(comando(o, clase, False))
            elif veces == 1 and ahora - primera >= RECORDAR_S:
                cmds.append(comando(o, clase, True))
            else:
                continue
        else:
            cmds.append(comando(o, clase, True))
        avisadas[n] = [primera, veces + 1]
    vivas = {str(o.get('orderNumber')) for o, _ in ordenes}
    for n in list(avisadas):
        if n not in vivas:
            del avisadas[n]
    return cmds


def avisar(cmds, espera=ESPERA_OK_S):
    """Manda los comandos al teléfono; a los que no contesta en `espera` s, notificación visible."""
    if not cmds:
        return []
    desde = time.time() - 5
    for c in cmds:
        publicar(tema('-alarma'), json.dumps(c))
    time.sleep(espera)
    try:
        oks = oks_desde(desde)
    except (OSError, ValueError):
        oks = set()
    sin_ok = [c for c in cmds if c['id'] not in oks]
    for c in sin_ok:
        extra = (' por ' + banco(c)) if banco(c) else ''
        titulo = ('💰 VENTA NUEVA de ' if c['clase'] == 'venta' else '🚨 COMPRA ABIERTA: pagá ') + monto_txt(c) + extra
        publicar(tema(), 'El teléfono no sonó · orden …%s' % c['orderNumber'][-6:], titulo, 5,
                 ('moneybag',) if c['clase'] == 'venta' else ('rotating_light',))
    for c in cmds:
        print(time.strftime('%Y-%m-%d %H:%M:%S'), c['clase'], monto_txt(c), '…' + c['orderNumber'][-6:],
              'sonó en el teléfono' if c not in sin_ok else 'NO sonó: notificación', flush=True)
    return sin_ok


def leer_binance():
    return [(o, 'venta') for o in mis_ordenes('SELL')] + [(o, 'compra') for o in mis_ordenes('BUY')]


if __name__ == '__main__':
    leer_env('/etc/relay-binance.env', '/etc/vigia-ventas.env')
    if not os.environ.get('NTFY_TOPIC'):
        sys.exit('Falta NTFY_TOPIC en /etc/vigia-ventas.env')
    if '--probar' in sys.argv:
        ords = leer_binance()
        print('Binance OK. Ventas esperando: %d · compras esperando: %d' % (
            sum(1 for _, c in ords if c == 'venta'), sum(1 for _, c in ords if c == 'compra')))
        publicar(tema('-vigia'), 'vivo')
        prueba = {'orderNumber': '000000000', 'totalPrice': '1500', 'fiat': 'UYU', 'amount': '34.48',
                  'asset': 'USDT', 'createTime': hora_binance_ms(), 'payMethodName': 'Prex'}
        print('Le pido al teléfono que suene una venta de prueba y espero %d s…' % ESPERA_OK_S, flush=True)
        sin_ok = avisar([dict(comando(prueba, 'venta', False), prueba=True)])
        sys.exit(1 if sin_ok else 0)
    avisadas, errores, ultima_vida = {}, 0, 0
    print(time.strftime('%Y-%m-%d %H:%M'), 'vigía de órdenes arrancado', flush=True)
    while True:
        try:
            ords = leer_binance()
            errores = 0
            if time.time() - ultima_vida >= VIDA_S:
                publicar(tema('-vigia'), 'vivo')
                ultima_vida = time.time()
            avisar(que_avisar(ords, avisadas, time.time()))
        except Exception as e:     # sin internet o Binance caído: sin señal de vida, el teléfono toma la posta
            errores += 1
            print(time.strftime('%Y-%m-%d %H:%M:%S'), 'error:', e, flush=True)
        time.sleep(pausa() if not errores else 60)
