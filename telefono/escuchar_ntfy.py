#!/usr/bin/env python3
"""Escucha los comandos de ntfy (tema ~/.bexo-ntfy + '-cmd') y corre lo que llega. Dejalo corriendo en una sesión
de Termux (con termux-wake-lock para que Android no lo duerma):

  python ~/bexo-scripts/telefono/escuchar_ntfy.py

Entiende dos comandos:
- el link de un anuncio de Binance (lo manda el botón "Armar en Binance" de la pre-orden en ntfy, apps-script/21_Ntfy.gs)
  → binance_orden.py arma la orden en la app (nunca la coloca);
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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bexo_ntfy import NTFY_URL, publicar, tema  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.expanduser('~/binance_orden.log')
MAX_EDAD_S = 120
LINK_BINANCE = re.compile(r'^https://c2c\.binance\.com/\S*[?&]code=\d+\S*$')


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
