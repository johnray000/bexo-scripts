#!/usr/bin/env python3
"""Escucha los comandos de ntfy (tema ~/.bexo-ntfy + '-cmd') y corre lo que llega. Dejalo corriendo en una sesión
de Termux (con termux-wake-lock para que Android no lo duerma):

  python ~/bexo-scripts/telefono/escuchar_ntfy.py

Entiende tres comandos:
- el link de un anuncio de Binance (lo manda el botón "Armar en Binance" de la pre-orden en ntfy, apps-script/21_Ntfy.gs)
  → binance_orden.py arma la orden en la app (nunca la coloca);
- "mercantil <id>" (botón "📲 Mercantil" de la tarjeta) → le pide al Apps Script los datos del Pago Móvil de ese
  comprobante (con WEBAPP_URL y ORDENES_TOKEN de ~/.subir-ordenes.env; por ntfy no viaja ningún dato del cliente) y
  corre mercantil_pago.py, que llega hasta tu huella. Un comprobante ya pagado no se vuelve a pagar;
- "subir-ordenes" (lo manda el botón "Actualizar ahora" de la Brújula P2P) → telefono/subir.sh sube ya las órdenes.
Comandos de hace más de MAX_EDAD_S se ignoran: una orden vieja ya no sirve. De a uno: mientras arma una orden, los
que llegan esperan su turno (y si para entonces son viejos, se ignoran).
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # bexo_ntfy, mercantil_pago
from bexo_ntfy import NTFY_URL, publicar, tema  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.expanduser('~/binance_orden.log')
MAX_EDAD_S = 120
LINK_BINANCE = re.compile(r'^https://c2c\.binance\.com/\S*[?&]code=\d+\S*$')
CMD_MERCANTIL = re.compile(r'^mercantil ([\w.:-]{1,80})$')
LOG_MERCANTIL = os.path.expanduser('~/mercantil_pago.log')
ENV = os.path.expanduser('~/.subir-ordenes.env')


def hora():
    return time.strftime('%H:%M:%S')


def correr_binance(link):
    print('%s armo la orden: %s' % (hora(), link), flush=True)
    with open(LOG, 'a') as log:
        log.write(time.strftime('--- %d/%m %H:%M (ntfy)\n'))
        log.flush()
        r = subprocess.run([sys.executable, os.path.join(RAIZ, 'binance_orden.py'), link],
                           stdout=log, stderr=subprocess.STDOUT)
    print('%s terminó (código %d); detalle en %s' % (hora(), r.returncode, LOG), flush=True)


def leer_env(ruta=ENV):
    cfg = {}
    try:
        with open(ruta) as f:
            for linea in f:
                if '=' in linea and not linea.startswith('#'):
                    k, v = linea.strip().split('=', 1)
                    cfg[k] = v
    except OSError:
        pass
    return cfg


def pedir_datos_pm(mov, cfg=None):
    """Los datos del Pago Móvil del comprobante, del Apps Script (doPost {pagoMovil}). Devuelve el dict o lanza
    ValueError con un motivo que se entiende."""
    cfg = cfg if cfg is not None else leer_env()
    if not cfg.get('WEBAPP_URL') or not cfg.get('ORDENES_TOKEN'):
        raise ValueError('Falta WEBAPP_URL u ORDENES_TOKEN en ~/.subir-ordenes.env')
    cuerpo = json.dumps({'pagoMovil': mov, 'token': cfg['ORDENES_TOKEN']}).encode()
    req = urllib.request.Request(cfg['WEBAPP_URL'], data=cuerpo, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read().decode())
    except (OSError, ValueError) as e:
        raise ValueError('No pude hablar con la planilla (%s). Revisá la conexión y tocá Mercantil otra vez' % e)
    if d.get('error') or not d.get('ok'):
        raise ValueError(d.get('error') or 'La planilla no mandó los datos')
    return d


def correr_mercantil(mov, pedir=pedir_datos_pm, correr=subprocess.run):
    import mercantil_pago
    if mercantil_pago.ya_pagado(mov):
        print('%s %s ya está pagado: no lo pago de nuevo' % (hora(), mov), flush=True)
        publicar('Mercantil: ese ya lo pagaste', 'El comprobante %s ya tiene un pago hecho desde acá. '
                 'No armo otro.' % mov, 4)
        return 'ya pagado'
    try:
        d = pedir(mov)
    except ValueError as e:
        publicar('Mercantil: no pude leer los datos', str(e)[:200], 4)
        return 'sin datos'
    print('%s pago móvil de %s Bs (%s)' % (hora(), d['monto'], mov), flush=True)
    with open(LOG_MERCANTIL, 'a') as log:
        log.write(time.strftime('--- %d/%m %H:%M (ntfy) ') + mov + '\n')
        log.flush()
        r = correr([sys.executable, os.path.join(RAIZ, 'mercantil_pago.py'), '--telefono', str(d['telefono']),
                    '--cedula', str(d['cedula']), '--banco', str(d['banco']), '--monto', str(d['monto']),
                    '--mov', mov, '--fin', str(d.get('fin') or '')], stdout=log, stderr=subprocess.STDOUT)
    print('%s terminó (código %d); detalle en %s' % (hora(), r.returncode, LOG_MERCANTIL), flush=True)
    return 'mercantil'


ULTIMA_SUBIDA = [0]


def correr_subir():
    """Sube ya las órdenes de Binance y Bybit (lo mismo que corre cada 4 h). Como mucho una vez por minuto."""
    if time.time() - ULTIMA_SUBIDA[0] < 60:
        print('%s subir-ordenes: ya subí hace menos de 1 min' % hora(), flush=True)
        return
    ULTIMA_SUBIDA[0] = time.time()
    print('%s subo las órdenes (pedido de la Brújula)' % hora(), flush=True)
    r = subprocess.run(['sh', os.path.join(RAIZ, 'telefono', 'subir.sh')])
    print('%s subida terminada (código %d); detalle en ~/subir.log' % (hora(), r.returncode), flush=True)


def procesar(ev, ahora=None):
    """Un mensaje del tema de comandos. Devuelve qué hizo (para las pruebas)."""
    texto = (ev.get('message') or '').strip()
    edad = (ahora or time.time()) - float(ev.get('time') or 0)
    if edad > MAX_EDAD_S:
        print('%s ignoro un comando de hace %d s: %s' % (hora(), edad, texto[:60]), flush=True)
        publicar('Comando viejo ignorado', 'Llegó con %d s de atraso: no armo una orden vieja.' % edad, 2)
        return 'viejo'
    if LINK_BINANCE.match(texto):
        correr_binance(texto)
        return 'binance'
    m = CMD_MERCANTIL.match(texto)
    if m:
        correr_mercantil(m.group(1))
        return 'mercantil'
    if texto == 'subir-ordenes':           # botón "Actualizar ahora" de la Brújula P2P (vps/dashboard_p2p.py)
        correr_subir()
        return 'subir'
    print('%s no sé qué hacer con: %s' % (hora(), texto[:80]), flush=True)
    publicar('Comando desconocido', texto[:200], 2)
    return 'desconocido'


def escuchar():
    t = tema()
    if not t:
        sys.exit('Falta ~/.bexo-ntfy (el nombre del tema de ntfy).')
    ultimo, espera = None, 2
    print('%s escuchando %s-cmd (Ctrl+C para parar)' % (hora(), t[:9] + '…'), flush=True)
    publicar('Teléfono listo', 'Escuchando los botones de ntfy.', 2, ('ear',))
    while True:
        url = '%s/%s-cmd/json' % (NTFY_URL, t) + ('?since=%s' % ultimo if ultimo else '')
        try:
            with urllib.request.urlopen(url, timeout=120) as r:   # ntfy manda un "keepalive" cada ~45 s
                espera = 2
                for linea in r:
                    ev = json.loads(linea)
                    if ev.get('event') != 'message':
                        continue
                    ultimo = ev.get('id')
                    procesar(ev)
        except KeyboardInterrupt:
            print('chau', flush=True)
            return
        except (OSError, ValueError) as e:
            print('%s se cortó la conexión con ntfy (%s): reintento en %d s' % (hora(), e, espera), flush=True)
            time.sleep(espera)
            espera = min(espera * 2, 60)


if __name__ == '__main__':
    escuchar()
