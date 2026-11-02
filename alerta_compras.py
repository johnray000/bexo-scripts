#!/usr/bin/env python3
"""Alarma en el teléfono cuando alguien abre una orden en TU anuncio de compra (Binance P2P).

Binance no avisa bien de estas órdenes y, si no pagás a tiempo, se cancelan y te bloquean el anuncio.
Cada 30 s mira tus compras de las últimas 2 horas (key de solo lectura, la de ~/.subir-ordenes.env).
Si hay una orden en tu anuncio esperando tu pago: notificación + pitidos agudos + voz, cada 5 minutos.
El botón "YA ME ENTERÉ" la calla 30 minutos; si después sigue sin pagar, vuelve con más pitidos.

  python alerta_compras.py            # queda corriendo (lo arranca telefono/alerta.sh)
  python alerta_compras.py --probar   # una sola vuelta, muestra lo que ve y suena una alarma de prueba
"""
import argparse
import json
import math
import os
import struct
import subprocess
import sys
import time
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from subir_ordenes import firmar_y_pedir, hora_binance_ms, leer_env  # noqa: E402

CADA_S = 30
REPETIR_S = 5 * 60
SILENCIO_S = 30 * 60                      # lo que calla el botón "YA ME ENTERÉ"
ESPERANDO_PAGO = ('PENDING', 'TRADING')   # después de "Pagado" pasa a BUYER_PAYED y deja de sonar
HOME = os.path.expanduser('~')
PITIDOS = {False: 3, True: 10}            # alarma normal / alarma después de "YA ME ENTERÉ"


def compras_abiertas(cfg):
    """Órdenes de compra en tus propios anuncios (MAKER) que esperan tu pago."""
    ahora = hora_binance_ms()
    r = firmar_y_pedir(cfg, {'tradeType': 'BUY', 'startTimestamp': ahora - 2 * 3600 * 1000,
                             'endTimestamp': ahora, 'page': 1, 'rows': 50})
    return [o for o in (r.get('data') or [])
            if o.get('orderStatus') in ESPERANDO_PAGO and o.get('advertisementRole') != 'TAKER']


def archivo_pitido(n):
    """WAV con n pitidos de 4000 Hz: bien agudo y todavía fuerte en el parlante de un teléfono."""
    ruta = os.path.join(HOME, '.alerta_pitido_%d.wav' % n)
    if not os.path.exists(ruta):
        tasa, tono, pausa = 44100, 0.25, 0.12
        muestras = []
        for _ in range(n):
            muestras += [int(32000 * math.sin(2 * math.pi * 4000 * i / tasa)) for i in range(int(tasa * tono))]
            muestras += [0] * int(tasa * pausa)
        with wave.open(ruta, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(tasa)
            w.writeframes(struct.pack('<%dh' % len(muestras), *muestras))
    return ruta, n * 0.37


def pitar(n):
    """Sube el volumen multimedia al máximo mientras pita y después lo deja como estaba."""
    ruta, dura = archivo_pitido(n)
    antes = None
    try:
        vols = json.loads(subprocess.run(['termux-volume'], capture_output=True, text=True).stdout or '[]')
        musica = next(v for v in vols if v.get('stream') == 'music')
        antes = musica['volume']
        subprocess.run(['termux-volume', 'music', str(musica['max_volume'])], check=False)
    except Exception:
        pass
    subprocess.run(['termux-media-player', 'play', ruta], check=False, capture_output=True)
    time.sleep(dura + 0.5)
    if antes is not None:
        subprocess.run(['termux-volume', 'music', str(antes)], check=False)


def marca_ya(n):
    return os.path.join(HOME, '.alerta_ya_' + n[-9:])


def sonar(o, insiste=False):
    n = str(o.get('orderNumber'))
    try:
        monto = '{:,}'.format(int(float(o.get('totalPrice')))).replace(',', '.')
        hablado = str(int(float(o.get('totalPrice'))))
    except (TypeError, ValueError):
        monto = hablado = str(o.get('totalPrice'))
    fiat = o.get('fiat') or ''
    cant = '%s %s' % (o.get('amount'), o.get('asset'))
    minutos = int((hora_binance_ms() - int(o.get('createTime') or 0)) / 60000)
    titulo = ('🚨🚨 SIGUE SIN PAGAR: ' if insiste else '🚨 COMPRA ABIERTA: pagá ') + '%s %s' % (monto, fiat)
    subprocess.run(['termux-notification', '--id', n[-9:],
                    '--title', titulo,
                    '--content', '%s · abierta hace %d min · orden …%s' % (cant, minutos, n[-6:]),
                    '--icon', 'warning', '--led-color', 'ff0000',
                    '--priority', 'max', '--vibrate', '1000,500,1000,500,1000',
                    '--button1', 'YA ME ENTERÉ',
                    '--button1-action', 'touch %s; termux-notification-remove %s' % (marca_ya(n), n[-9:])],
                   check=False)
    pitar(PITIDOS[insiste])
    frase = ('Todavía no pagaste la compra de %s' if insiste else 'Orden de compra abierta. Pagá %s') % hablado
    subprocess.run(['termux-tts-speak', '-s', 'ALARM', frase], check=False)


def vuelta(cfg, avisadas):
    abiertas = compras_abiertas(cfg)
    ahora = time.time()
    for o in abiertas:
        n = str(o.get('orderNumber'))
        ya = os.path.getmtime(marca_ya(n)) if os.path.exists(marca_ya(n)) else 0
        if ya and ahora - ya < SILENCIO_S:
            continue
        ultimo = avisadas.get(n, 0)
        # Al terminar los 30 min de silencio suena enseguida; después, cada 5 min hasta otro "YA ME ENTERÉ".
        if ahora - ultimo >= REPETIR_S or (ya and ultimo < ya + SILENCIO_S):
            sonar(o, insiste=bool(ya))
            avisadas[n] = ahora
    vivas = {str(o.get('orderNumber')) for o in abiertas}
    for n in list(avisadas):
        if n not in vivas:
            del avisadas[n]
            subprocess.run(['termux-notification-remove', n[-9:]], check=False)
            if os.path.exists(marca_ya(n)):
                os.remove(marca_ya(n))
    return abiertas


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--probar', action='store_true')
    args = ap.parse_args()
    cfg = leer_env()
    if args.probar:
        abiertas = vuelta(cfg, {})
        print('Compras en tus anuncios esperando pago:', len(abiertas))
        sonar({'orderNumber': '000000000', 'totalPrice': '34200.75', 'fiat': 'ARS', 'amount': '0',
               'asset': 'USDC', 'createTime': hora_binance_ms()})
        sys.exit(0)
    avisadas = {}
    print(time.strftime('%Y-%m-%d %H:%M'), 'alerta de compras arrancada', flush=True)
    while True:
        try:
            vuelta(cfg, avisadas)
        except (Exception, SystemExit) as e:   # sin internet o Binance caído: sigue intentando
            print(time.strftime('%Y-%m-%d %H:%M'), 'error:', e, flush=True)
        time.sleep(CADA_S)
