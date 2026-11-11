#!/usr/bin/env python3
"""Cazar oportunidades P2P (OKX, Bybit, Binance) desde el teléfono. PASO 1: grabar el recorrido a mano.

Antes de automatizar la toma de una orden hay que conocer cada pantalla de cada app. Este modo NO toca nada:
mientras vos hacés el recorrido con el dedo, el script mira la pantalla (por ADB, igual que okx_ordenes.py) y anota
cada pantalla nueva, cada toque tuyo y cuánto tardó cada paso. Con eso se arma después el recorrido automático.

  python cazar_p2p.py --grabar okx        # abre OKX de cero y graba hasta que toques TERMINÉ (o 3 minutos)
  python cazar_p2p.py --grabar bybit
  python cazar_p2p.py --grabar binance
  python cazar_p2p.py --grabar okx --sin-abrir   # no abre la app: graba desde donde estés
  python cazar_p2p.py --enlaces bybit     # lista los enlaces directos que acepta la app (para saltear pantallas)
  python cazar_p2p.py --radar             # muestra las oportunidades que ve el radar (OKX, Bybit, Binance)
  python cazar_p2p.py --ensayo            # abre en la app el anuncio de la última oportunidad y graba lo que hacés
  python cazar_p2p.py --grabar binance --link URL   # abre ese link en la app y graba desde ahí

⚠️ Llegá hasta la pantalla donde está el botón final de Comprar / Vender, con el monto puesto, y AHÍ tocá TERMINÉ
   en la notificación. El último toque no lo hagas: el script nunca lo hace por vos.

Deja en Descargas una carpeta cazar_<app>_<hora>/ con una captura y el XML de cada pantalla, el archivo
recorrido.txt (paso a paso con los tiempos) y todo junto en cazar_<app>_<hora>.zip para mandarlo al chat.
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from okx_ordenes import adb, adb_bytes, conectar, tamano_pantalla  # noqa: E402
from subir_ordenes import leer_env  # noqa: E402

HOME = os.path.expanduser('~')
DESCARGAS = os.path.join(HOME, 'storage', 'downloads')
PARAR = os.path.join(HOME, '.cazar_parar')
# Cómo reconocer el paquete de cada app entre los instalados (pm list packages).
APPS = {'okx': ('okx', 'okinc'), 'bybit': ('bybit',), 'binance': ('binance',)}
# Cómo nombra el radar a cada exchange (radar-p2p, /api/movil) → app del teléfono.
APP_DE = {'OKX': 'okx', 'Bybit': 'bybit', 'Binance': 'binance'}
RADAR_URL = 'http://100.116.121.75:8095'   # el radar en el VPS, por Tailscale


def leer_radar(cfg):
    """Lo que muestra la página /movil del radar (oportunidades, rutas, tus anuncios). Solo lee."""
    url = cfg.get('RADAR_URL', RADAR_URL).rstrip('/') + '/api/movil'
    req = urllib.request.Request(url)
    if cfg.get('RADAR_CLAVE'):
        par = '%s:%s' % (cfg.get('RADAR_USUARIO', 'admin'), cfg['RADAR_CLAVE'])
        req.add_header('Authorization', 'Basic ' + base64.b64encode(par.encode()).decode())
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def oportunidades(datos):
    """Las oportunidades del radar (de la más nueva a la más vieja) con una punta en OKX, Bybit o Binance.
    Para cada una, la punta a tomar primero: la compra (tomás un anuncio de venta), salvo que esa punta sea de otro
    exchange. abierta = el radar la sigue viendo (último ciclo hace menos de 2,5 vueltas)."""
    ahora, vuelta = datos.get('ahora') or time.time(), datos.get('intervalo') or 120
    lista = []
    for e in datos.get('episodios') or []:
        puntas = [('compra', e.get('ae'), e.get('ac'), e.get('an'), e.get('al')),
                  ('venta', e.get('be'), e.get('bc'), e.get('bn'), e.get('bl'))]
        for lado, ex, coin, quien, link in puntas:
            if ex in APP_DE and link:
                lista.append({'app': APP_DE[ex], 'lado': lado, 'coin': coin, 'fiat': e.get('f'), 'quien': quien,
                              'link': link, 'spread': e.get('max'), 'abierta': ahora - e['fin'] <= vuelta * 2.5,
                              'hace_min': int((ahora - e['fin']) / 60),
                              'ruta': '%s %s → %s %s' % (e.get('ae'), e.get('ac'), e.get('be'), e.get('bc'))})
                break
    return lista


def abrir_link(app, link):
    """Abre el link dentro de la app (sin pasar por el navegador). False si la app no acepta ese link."""
    pkg = paquete(app)
    adb('shell', 'am', 'force-stop', pkg)
    r = adb('shell', 'am', 'start', '-W', '-a', 'android.intent.action.VIEW', '-d', link, pkg)
    return 'Error' not in r and 'unable to resolve' not in r.lower()


def paquete(app):
    claves = APPS[app]
    for linea in adb('shell', 'pm', 'list', 'packages').splitlines():
        p = linea.replace('package:', '').strip()
        if any(c in p.lower() for c in claves):
            return p
    raise SystemExit('No encontré la app de %s instalada' % app)


def notificar(titulo, texto, botones=True):
    cmd = ['termux-notification', '--id', 'cazar-grabar', '--ongoing', '--priority', 'max',
           '--title', titulo, '--content', texto]
    if botones:
        cmd += ['--button1', 'TERMINÉ', '--button1-action', 'touch %s' % PARAR]
    subprocess.run(cmd, check=False)


def pantalla_actual():
    """La pantalla como lista de elementos: dict(texto, id, x1, y1, x2, y2, clic). Vacía si uiautomator no respondió
    (pasa con animaciones). Rápido: un solo intento, el bucle vuelve a probar enseguida."""
    try:
        xml = adb('exec-out', 'uiautomator', 'dump', '/dev/tty', espera=12)
    except subprocess.TimeoutExpired:
        adb('shell', 'pkill', '-f', 'uiautomator')
        return [], ''
    if '<hierarchy' not in xml:
        return [], ''
    xml = xml[xml.find('<?xml'):xml.rfind('>') + 1]
    elementos = []
    try:
        nodos = list(ET.fromstring(xml).iter('node'))
    except ET.ParseError:
        return [], ''
    for n in nodos:
        b = [int(v) for v in re.findall(r'\d+', n.get('bounds') or '')]
        if len(b) != 4:
            continue
        t = (n.get('text') or n.get('content-desc') or '').strip()
        elementos.append({'texto': t, 'id': (n.get('resource-id') or '').split('/')[-1],
                          'x1': b[0], 'y1': b[1], 'x2': b[2], 'y2': b[3],
                          'clic': n.get('clickable') == 'true'})
    return elementos, xml


def firma(elementos):
    """Lo que identifica una pantalla: sus textos (sin números que cambian solos, como precios o relojes)."""
    return tuple(sorted({re.sub(r'[\d.,:%]+', '#', e['texto']) for e in elementos if e['texto']}))


def foco():
    m = re.search(r'mCurrentFocus=\S+ \S+ (\S+)\}', adb('shell', 'dumpsys', 'window'))
    return m.group(1) if m else '?'


def que_toco(elementos, x, y):
    """El elemento más chico con texto que contiene el punto (lo que el dedo tocó). Si no hay texto, el id."""
    dentro = [e for e in elementos if e['x1'] <= x <= e['x2'] and e['y1'] <= y <= e['y2']]
    dentro.sort(key=lambda e: (e['x2'] - e['x1']) * (e['y2'] - e['y1']))
    for e in dentro:
        if e['texto']:
            return '"%s"' % e['texto'][:40]
    for e in dentro:
        if e['id']:
            return 'id=%s' % e['id']
    return 'sin texto'


class Toques(threading.Thread):
    """Lee los toques del dedo con `getevent` (no toca nada, solo escucha) y los pasa a píxeles de pantalla."""

    def __init__(self, t0, ancho, alto):
        super().__init__(daemon=True)
        self.t0, self.ancho, self.alto = t0, ancho, alto
        self.toques = []          # (segundos, x, y, x_fin, y_fin)
        self.maximos = {}         # dispositivo -> (max_x, max_y)
        self.proc = None

    def leer_maximos(self):
        disp, mx = None, {}
        for linea in adb('shell', 'getevent', '-lp', espera=20).splitlines():
            m = re.match(r'add device \d+: (\S+)', linea)
            if m:
                disp = m.group(1)
            m = re.search(r'(ABS_MT_POSITION_[XY])\s*:.*max (\d+)', linea)
            if m and disp:
                mx.setdefault(disp, {})[m.group(1)[-1]] = int(m.group(2))
        self.maximos = {d: (v.get('X', self.ancho - 1), v.get('Y', self.alto - 1)) for d, v in mx.items()}

    def run(self):
        try:
            self.leer_maximos()
            self.proc = subprocess.Popen(['adb', 'shell', 'getevent', '-l'], stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL, text=True)
        except Exception as e:  # sin getevent igual se graban las pantallas
            print('No pude leer los toques:', e, file=sys.stderr, flush=True)
            return
        x = y = None
        abajo = None              # (t, x, y) del inicio del toque; 'esperando' hasta el primer SYN_REPORT
        for linea in self.proc.stdout:
            m = re.match(r'(\S+): (EV_\w+)\s+(\w+)\s+([0-9a-f]+)', linea.strip())
            if not m or m.group(1) not in self.maximos:
                continue
            disp, tipo, codigo, valor = m.group(1), m.group(2), m.group(3), int(m.group(4), 16)
            mx, my = self.maximos[disp]
            if codigo == 'ABS_MT_POSITION_X':
                x = int(valor * (self.ancho - 1) / max(mx, 1))
            elif codigo == 'ABS_MT_POSITION_Y':
                y = int(valor * (self.alto - 1) / max(my, 1))
            elif codigo == 'ABS_MT_TRACKING_ID':
                if valor == 0xffffffff:        # dedo arriba
                    if isinstance(abajo, tuple) and x is not None:
                        self.toques.append((abajo[0], abajo[1], abajo[2], x, y))
                    abajo = None
                elif abajo is None:            # dedo abajo: la posición termina de llegar con el SYN_REPORT
                    abajo = 'esperando'
            elif tipo == 'EV_SYN' and abajo == 'esperando' and x is not None and y is not None:
                abajo = (time.time() - self.t0, x, y)

    def parar(self):
        if self.proc:
            self.proc.terminate()


def grabar(app, segundos, abrir, link=None):
    pkg = paquete(app)
    ancho, alto = tamano_pantalla()
    hora = time.strftime('%H%M%S')
    nombre = 'cazar_%s_%s' % (app, hora)
    carpeta = os.path.join(DESCARGAS, nombre)
    os.makedirs(carpeta, exist_ok=True)
    if os.path.exists(PARAR):
        os.remove(PARAR)
    notificar('🔴 Grabando %s' % app.upper(),
              'Hacé el recorrido hasta el botón final, SIN tocarlo. Después tocá TERMINÉ.')
    if abrir:
        adb('shell', 'am', 'force-stop', pkg)
    t0 = time.time()
    toques = Toques(t0, ancho, alto)
    toques.start()
    if link:
        if not abrir_link(app, link):
            print('La app no abrió el link: la abro desde el inicio', flush=True)
            adb('shell', 'monkey', '-p', pkg, '-c', 'android.intent.category.LAUNCHER', '1')
    elif abrir:
        adb('shell', 'monkey', '-p', pkg, '-c', 'android.intent.category.LAUNCHER', '1')
    pantallas = []            # (segundos, n, firma, foco, elementos)
    ultima = None
    while time.time() - t0 < segundos and not os.path.exists(PARAR):
        t = time.time() - t0
        elementos, xml = pantalla_actual()
        if not elementos:
            time.sleep(0.3)
            continue
        f = firma(elementos)
        if f != ultima:
            ultima = f
            n = len(pantallas) + 1
            act = foco()
            png = adb_bytes('exec-out', 'screencap', '-p', espera=20)
            with open(os.path.join(carpeta, '%02d.png' % n), 'wb') as fh:
                fh.write(png)
            with open(os.path.join(carpeta, '%02d.xml' % n), 'w') as fh:
                fh.write(xml)
            pantallas.append((t, n, f, act, elementos))
            print('%6.1f s  pantalla %d  %s' % (t, n, act.split('/')[-1][:50]), flush=True)
    t_fin = time.time() - t0
    toques.parar()
    subprocess.run(['termux-notification-remove', 'cazar-grabar'], check=False)
    subprocess.run(['termux-vibrate'], check=False)

    # El recorrido paso a paso: pantallas y toques mezclados por tiempo. Cada toque se cruza con la última pantalla
    # vista antes de él, para saber qué botón fue.
    eventos = [(t, 'p', p) for p in pantallas for t in [p[0]]] + [(tq[0], 't', tq) for tq in toques.toques]
    eventos.sort(key=lambda e: e[0])
    lineas = ['Recorrido %s · %s · pantalla %dx%d · %s' % (app.upper(), pkg, ancho, alto,
                                                            time.strftime('%d/%m/%Y %H:%M')),
              'Abrió: %s' % (link or ('app desde el inicio' if abrir else 'pantalla actual')),
              'Total: %.1f s, %d pantallas, %d toques' % (t_fin, len(pantallas), len(toques.toques)), '']
    vista = []
    for t, tipo, e in eventos:
        if tipo == 'p':
            _, n, _, act, vista = e
            textos = [x['texto'] for x in vista if x['texto']][:25]
            lineas.append('%6.1f s  PANTALLA %02d  %s' % (t, n, act))
            lineas.append('          textos: %s' % ' | '.join(s[:30] for s in textos))
        else:
            _, x, y, xf, yf = e
            arrastre = abs(xf - x) > 40 or abs(yf - y) > 40
            accion = 'DESLIZA' if arrastre else 'TOCA'
            lineas.append('%6.1f s  %s (%.3f, %.3f) %s%s' % (
                t, accion, x / ancho, y / alto, que_toco(vista, x, y),
                ' → (%.3f, %.3f)' % (xf / ancho, yf / alto) if arrastre else ''))
    with open(os.path.join(carpeta, 'recorrido.txt'), 'w') as fh:
        fh.write('\n'.join(lineas) + '\n')
    zip_ruta = os.path.join(DESCARGAS, nombre + '.zip')
    with zipfile.ZipFile(zip_ruta, 'w', zipfile.ZIP_DEFLATED) as z:
        for archivo in sorted(os.listdir(carpeta)):
            z.write(os.path.join(carpeta, archivo), os.path.join(nombre, archivo))
    print('\n'.join(lineas))
    print('\nListo. Mandá al chat el archivo de Descargas: %s.zip' % nombre)


def enlaces(app):
    """Los enlaces (esquemas y rutas) que la app dice aceptar: sirven para abrir directo una pantalla."""
    vistos = []
    for linea in adb('shell', 'dumpsys', 'package', paquete(app)).splitlines():
        linea = linea.strip()
        if re.match(r'(Scheme|Authority|Path|PathPrefix|PathPattern):', linea) and linea not in vistos:
            vistos.append(linea)
    ruta = os.path.join(DESCARGAS, 'cazar_enlaces_%s.txt' % app)
    with open(ruta, 'w') as fh:
        fh.write('\n'.join(vistos) + '\n')
    print('\n'.join(vistos[:60]))
    print('\n%d líneas, guardadas en %s' % (len(vistos), ruta))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--grabar', choices=sorted(APPS), help='graba el recorrido que hacés a mano en esa app')
    ap.add_argument('--enlaces', choices=sorted(APPS), help='lista los enlaces directos que acepta la app')
    ap.add_argument('--sin-abrir', action='store_true', help='no abre la app: graba desde la pantalla actual')
    ap.add_argument('--link', help='con --grabar: abre este link en la app en vez del inicio')
    ap.add_argument('--radar', action='store_true', help='muestra las oportunidades del radar (solo lee)')
    ap.add_argument('--ensayo', action='store_true',
                    help='abre en la app el anuncio de la última oportunidad del radar y graba tu recorrido')
    ap.add_argument('--segundos', type=int, default=180, help='tiempo máximo de grabación')
    args = ap.parse_args()
    if not (args.grabar or args.enlaces or args.radar or args.ensayo):
        ap.print_help()
        sys.exit(0)
    elegida = None
    if args.radar or args.ensayo:
        try:
            ops = oportunidades(leer_radar(leer_env()))
        except Exception as e:
            raise SystemExit('No pude leer el radar (%s). ¿Tailscale prendido en el teléfono? '
                             '¿RADAR_CLAVE en ~/.subir-ordenes.env?' % e)
        for o in ops:
            print('%s %-7s %5.2f%%  %s %s %s · %s · tomar %s de %s\n         %s' % (
                '🟢' if o['abierta'] else '⚪', o['app'], o['spread'] or 0, o['fiat'], o['ruta'],
                'ABIERTA' if o['abierta'] else 'hace %d min' % o['hace_min'], o['coin'], o['lado'],
                o['quien'] or '?', o['link']), flush=True)
        if not ops:
            print('El radar no tiene oportunidades recientes con OKX, Bybit o Binance.')
        if args.radar or not ops:
            sys.exit(0)
        elegida = ops[0]
        print('\nEnsayo con: %s en %s (%s)' % (elegida['quien'], elegida['app'], elegida['ruta']), flush=True)
    if not conectar():
        raise SystemExit('Sin ADB: activá Depuración inalámbrica (Opciones de desarrollador) y que haya wifi')
    if args.enlaces:
        enlaces(args.enlaces)
    elif elegida:
        grabar(elegida['app'], args.segundos, True, elegida['link'])
    else:
        grabar(args.grabar, args.segundos, not args.sin_abrir, args.link)
