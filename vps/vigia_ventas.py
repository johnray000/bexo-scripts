#!/usr/bin/env python3
"""Vigía de la alarma del teléfono, en el VPS.

Binance no deja leer órdenes desde EE.UU. (error 451), así que el que mira Binance sigue siendo el teléfono
(alerta_compras.py). Pero con la pantalla bloqueada Android lo puede dormir sin avisar. Por eso el teléfono le manda
un latido al relay cada minuto (/latido) y este vigía pregunta cada minuto hace cuánto llegó el último:
  - más de 5 min sin latido (de 1 a 10 de la mañana, hora UY, 20 min): notificación de ntfy de prioridad máxima
    "La alarma del teléfono no está mirando Binance". Una sola vez hasta que vuelva.
  - cuando vuelve: aviso normal "volvió".
El teléfono suena; esta notificación llega solo cuando el teléfono NO está mirando.

Config: NTFY_TOPIC en /etc/vigia-ventas.env; RELAY_TOKEN y RELAY_PUERTO de /etc/relay-binance.env.
  python3 vigia_ventas.py            # queda corriendo (servicio vigia-ventas)
  python3 vigia_ventas.py --probar   # muestra hace cuánto llegó el latido y manda un aviso de prueba
"""
import json
import os
import sys
import time
import urllib.request

NTFY = 'https://ntfy.sh'
CADA_S = 60
MAX_SIN_LATIDO_S, MAX_SIN_LATIDO_NOCHE_S = 5 * 60, 20 * 60
NOCHE = (1, 10)
UY_UTC = -3


def leer_env(*rutas):
    for ruta in rutas:
        try:
            with open(ruta) as f:
                for linea in f:
                    if '=' in linea and not linea.lstrip().startswith('#'):
                        k, v = linea.strip().split('=', 1)
                        os.environ.setdefault(k, v.strip().strip('"'))
        except OSError:
            pass


def limite(t=None):
    hora = time.gmtime((t or time.time()) + UY_UTC * 3600).tm_hour
    return MAX_SIN_LATIDO_NOCHE_S if NOCHE[0] <= hora < NOCHE[1] else MAX_SIN_LATIDO_S


def hace_cuanto():
    """Segundos desde el último latido del teléfono (None: no llegó ninguno desde que arrancó el relay)."""
    url = 'http://localhost:%s/latido?token=%s&ver=1' % (os.environ.get('RELAY_PUERTO', '8082'),
                                                          os.environ['RELAY_TOKEN'])
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.load(r).get('hace_s')


def publicar(titulo, texto, prioridad):
    cuerpo = {'topic': os.environ['NTFY_TOPIC'], 'title': titulo, 'message': texto, 'priority': prioridad,
              'tags': ['rotating_light' if prioridad >= 5 else 'white_check_mark']}
    req = urllib.request.Request(NTFY, data=json.dumps(cuerpo).encode(), headers={'Content-Type': 'application/json'})
    urllib.request.urlopen(req, timeout=15).read()


def revisar(estado, hace, ahora=None):
    """estado: {'alerta': bool}. Devuelve el aviso que corresponde mandar (o None)."""
    ahora = ahora or time.time()
    if hace is None:                       # relay recién arrancado: cuenta desde la primera vez que no hubo dato
        estado.setdefault('sin_dato', ahora)
        hace = ahora - estado['sin_dato']
    else:
        estado.pop('sin_dato', None)
    if hace > limite(ahora) and not estado['alerta']:
        estado['alerta'] = True
        return ('⚠️ La alarma del teléfono NO está mirando Binance',
                'Hace %d min que no da señales: si entra una venta no va a sonar. Abrí Termux o mirá Binance.'
                % (hace // 60), 5)
    if hace <= limite(ahora) and estado['alerta']:
        estado['alerta'] = False
        return ('✅ La alarma del teléfono volvió a mirar Binance', '', 3)
    return None


if __name__ == '__main__':
    leer_env('/etc/relay-binance.env', '/etc/vigia-ventas.env')
    if not os.environ.get('NTFY_TOPIC') or not os.environ.get('RELAY_TOKEN'):
        sys.exit('Falta NTFY_TOPIC (/etc/vigia-ventas.env) o RELAY_TOKEN (/etc/relay-binance.env)')
    if '--probar' in sys.argv:
        hace = hace_cuanto()
        print('Último latido del teléfono:', 'ninguno todavía' if hace is None else 'hace %d s' % hace)
        publicar('Vigía de la alarma: PRUEBA', 'Si ves esto, el VPS te puede avisar cuando el teléfono deje de mirar.', 3)
        print('Aviso de prueba enviado a ntfy')
        sys.exit(0)
    estado = {'alerta': False}
    print(time.strftime('%Y-%m-%d %H:%M'), 'vigía de la alarma arrancado', flush=True)
    while True:
        try:
            aviso = revisar(estado, hace_cuanto())
            if aviso:
                publicar(*aviso)
                print(time.strftime('%Y-%m-%d %H:%M:%S'), aviso[0], flush=True)
        except Exception as e:
            print(time.strftime('%Y-%m-%d %H:%M:%S'), 'error:', e, flush=True)
        time.sleep(CADA_S)
