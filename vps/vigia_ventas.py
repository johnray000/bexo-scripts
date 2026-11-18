#!/usr/bin/env python3
"""Vigía de ventas P2P en el VPS: avisa por Telegram (y ntfy) cuando entra una venta en tu anuncio de Binance.

El teléfono también tiene alarma (alerta_compras.py), pero con la pantalla bloqueada Android puede dormir a Termux y
no pregunta a Binance. El VPS no duerme: pregunta cada 20 s con la key de SOLO LECTURA del relay
(/etc/relay-binance.env) y el aviso de Telegram/ntfy despierta al teléfono aunque esté bloqueado.

Por cada venta nueva (el comprador entró y espera): un mensaje "💰 VENTA NUEVA de 1.500 UYU por Prex".
Si a los 10 min sigue sin pagar, un recordatorio. Nada más (pagada o cancelada no avisa).

Config en /etc/vigia-ventas.env (no va a GitHub): TELEGRAM_TOKEN, TELEGRAM_CHAT y/o NTFY_TOPIC.
  python3 vigia_ventas.py            # queda corriendo (servicio vigia-ventas)
  python3 vigia_ventas.py --probar   # muestra lo que ve en Binance y manda un mensaje de prueba
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
CADA_S = 20
RECORDAR_S = 10 * 60
ESPERANDO = ('PENDING', 'TRADING')
BANCOS = (('prex', 'Prex'), ('itau', 'Itaú'), ('midinero', 'Mi Dinero'), ('redpagos', 'Mi Dinero'),
          ('mercado', 'Mercado Pago'), ('oca', 'OCA'))


def leer_env(*rutas):
    """Lee KEY=valor de los archivos (los del systemd ya vienen en el entorno; esto es para --probar a mano)."""
    for ruta in rutas:
        try:
            with open(ruta) as f:
                for linea in f:
                    if '=' in linea and not linea.lstrip().startswith('#'):
                        k, v = linea.strip().split('=', 1)
                        os.environ.setdefault(k, v.strip().strip('"'))
        except OSError:
            pass


_desfase_ms = None


def hora_binance_ms():
    """Hora según Binance (si el reloj del VPS se adelanta, Binance rechaza la firma)."""
    global _desfase_ms
    if _desfase_ms is None:
        with urllib.request.urlopen('https://api.binance.com/api/v3/time', timeout=10) as r:
            _desfase_ms = json.load(r)['serverTime'] - int(time.time() * 1000)
    return int(time.time() * 1000) + _desfase_ms - 2000


def ventas_esperando():
    """Ventas en TUS anuncios (MAKER) de las últimas 2 h donde el comprador entró y todavía no pagó."""
    ahora = hora_binance_ms()
    params = {'tradeType': 'SELL', 'startTimestamp': ahora - 2 * 3600 * 1000, 'endTimestamp': ahora,
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


def banco(o):
    crudo = str(o.get('payMethodName') or '')
    plano = crudo.lower().replace('ú', 'u').replace(' ', '').replace('_', '')
    return next((lindo for clave, lindo in BANCOS if clave in plano), crudo)


def texto(o, recordatorio=False):
    try:
        monto = '{:,}'.format(int(float(o.get('totalPrice')))).replace(',', '.')
    except (TypeError, ValueError):
        monto = str(o.get('totalPrice'))
    linea = '%s %s' % (monto, o.get('fiat') or '')
    if banco(o):
        linea += ' por ' + banco(o)
    titulo = ('⏰ SIGUE ESPERANDO: venta de ' if recordatorio else '💰 VENTA NUEVA de ') + linea
    minutos = int((hora_binance_ms() - int(o.get('createTime') or 0)) / 60000)
    detalle = '%s %s · abierta hace %d min · orden …%s' % (o.get('amount'), o.get('asset'), minutos,
                                                           str(o.get('orderNumber'))[-6:])
    return titulo, detalle


def enviar(titulo, detalle):
    """Manda a Telegram y a ntfy (los que estén configurados). Devuelve a cuántos llegó."""
    llegó = 0
    token, chat = os.environ.get('TELEGRAM_TOKEN'), os.environ.get('TELEGRAM_CHAT')
    if token and chat:
        try:
            datos = urllib.parse.urlencode({'chat_id': chat, 'text': '%s\n%s' % (titulo, detalle)}).encode()
            urllib.request.urlopen('https://api.telegram.org/bot%s/sendMessage' % token, data=datos, timeout=10).read()
            llegó += 1
        except (OSError, ValueError) as e:
            print('Telegram falló:', e, flush=True)
    tema = os.environ.get('NTFY_TOPIC')
    if tema:
        try:
            cuerpo = json.dumps({'topic': tema, 'title': titulo, 'message': detalle, 'priority': 5,
                                 'tags': ['moneybag']}).encode()
            urllib.request.urlopen(urllib.request.Request('https://ntfy.sh', data=cuerpo,
                                                          headers={'Content-Type': 'application/json'}),
                                   timeout=10).read()
            llegó += 1
        except (OSError, ValueError) as e:
            print('ntfy falló:', e, flush=True)
    return llegó


def vuelta(avisadas, ahora):
    """avisadas: orden → [cuándo avisó la primera vez, si ya mandó el recordatorio]."""
    esperando = ventas_esperando()
    for o in esperando:
        n = str(o.get('orderNumber'))
        if n not in avisadas:
            enviar(*texto(o))
            avisadas[n] = [ahora, False]
            print(time.strftime('%Y-%m-%d %H:%M:%S'), 'venta nueva …' + n[-6:], flush=True)
        elif not avisadas[n][1] and ahora - avisadas[n][0] >= RECORDAR_S:
            enviar(*texto(o, recordatorio=True))
            avisadas[n][1] = True
            print(time.strftime('%Y-%m-%d %H:%M:%S'), 'recordatorio …' + n[-6:], flush=True)
    vivas = {str(o.get('orderNumber')) for o in esperando}
    for n in list(avisadas):
        if n not in vivas:
            del avisadas[n]
    return esperando


if __name__ == '__main__':
    leer_env('/etc/relay-binance.env', '/etc/vigia-ventas.env')
    if '--probar' in sys.argv:
        print('Ventas esperando ahora:', len(ventas_esperando()))
        n = enviar('💰 VENTA NUEVA de 1.500 UYU por Prex', 'PRUEBA del vigía del VPS · no es una venta real')
        print('Mensaje de prueba enviado a %d destino(s)' % n)
        sys.exit(0 if n else 1)
    avisadas, errores = {}, 0
    print(time.strftime('%Y-%m-%d %H:%M'), 'vigía de ventas arrancado', flush=True)
    while True:
        try:
            vuelta(avisadas, time.time())
            if errores >= 10:
                enviar('✅ Vigía de ventas: Binance volvió a responder', '')
            errores = 0
        except Exception as e:     # sin internet o Binance caído: sigue intentando
            errores += 1
            print(time.strftime('%Y-%m-%d %H:%M:%S'), 'error:', e, flush=True)
            if errores == 10:      # ~3 min sin poder mirar: que lo sepas, porque no te va a avisar
                enviar('⚠️ Vigía de ventas: no puedo leer Binance', str(e)[:200])
        time.sleep(CADA_S)
