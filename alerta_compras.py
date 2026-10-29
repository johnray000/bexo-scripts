#!/usr/bin/env python3
"""Alarma en el teléfono cuando alguien abre una orden en TU anuncio de compra (Binance P2P).

Binance no avisa bien de estas órdenes y, si no pagás a tiempo, se cancelan y te bloquean el anuncio.
Cada 30 s mira tus compras de las últimas 2 horas (key de solo lectura, la de ~/.subir-ordenes.env).
Si hay una orden en tu anuncio esperando tu pago: notificación con sonido y vibración + voz,
y repite cada 2 minutos mientras siga sin pagar.

  python alerta_compras.py            # queda corriendo (lo arranca telefono/alerta.sh)
  python alerta_compras.py --probar   # una sola vuelta, muestra lo que ve y suena una alarma de prueba
"""
import argparse
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from subir_ordenes import DIA_MS, firmar_y_pedir, hora_binance_ms, leer_env  # noqa: E402

CADA_S = 30
REPETIR_S = 120
ESPERANDO_PAGO = ('PENDING', 'TRADING')   # después de "Pagado" pasa a BUYER_PAYED y deja de sonar


def compras_abiertas(cfg):
    """Órdenes de compra en tus propios anuncios (MAKER) que esperan tu pago."""
    ahora = hora_binance_ms()
    r = firmar_y_pedir(cfg, {'tradeType': 'BUY', 'startTimestamp': ahora - 2 * 3600 * 1000,
                             'endTimestamp': ahora, 'page': 1, 'rows': 50})
    return [o for o in (r.get('data') or [])
            if o.get('orderStatus') in ESPERANDO_PAGO and o.get('advertisementRole') != 'TAKER']


def sonar(o):
    total = '%s %s' % (o.get('totalPrice'), o.get('fiat'))
    cant = '%s %s' % (o.get('amount'), o.get('asset'))
    minutos = int((hora_binance_ms() - int(o.get('createTime') or 0)) / 60000)
    subprocess.run(['termux-notification', '--id', str(o.get('orderNumber'))[-9:],
                    '--title', '🔔 COMPRA ABIERTA: pagá ' + total,
                    '--content', '%s · abierta hace %d min · orden …%s' % (cant, minutos, str(o.get('orderNumber'))[-6:]),
                    '--priority', 'max', '--sound', '--vibrate', '1000,500,1000,500,1000'], check=False)
    subprocess.run(['termux-tts-speak', 'Orden de compra abierta. Pagá %s' % total], check=False)


def vuelta(cfg, avisadas):
    abiertas = compras_abiertas(cfg)
    ahora = time.time()
    for o in abiertas:
        n = str(o.get('orderNumber'))
        if ahora - avisadas.get(n, 0) >= REPETIR_S:
            sonar(o)
            avisadas[n] = ahora
    vivas = {str(o.get('orderNumber')) for o in abiertas}
    for n in list(avisadas):
        if n not in vivas:
            del avisadas[n]
            subprocess.run(['termux-notification-remove', n[-9:]], check=False)
    return abiertas


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--probar', action='store_true')
    args = ap.parse_args()
    cfg = leer_env()
    if args.probar:
        abiertas = vuelta(cfg, {})
        print('Compras en tus anuncios esperando pago:', len(abiertas))
        sonar({'orderNumber': '000000000', 'totalPrice': 'PRUEBA', 'fiat': '', 'amount': '0',
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
