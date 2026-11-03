#!/usr/bin/env python3
"""Lee tus órdenes P2P de la app de OKX (Órdenes → Completadas) y las manda a la planilla (hoja Ordenes_P2P).

La API común de OKX solo da los USDT que entran y salen; los pesos, el precio y la contraparte están en la app.
Este script maneja el teléfono por ADB (depuración inalámbrica, al mismo teléfono): abre OKX, va a la lista,
lee lo que hay en pantalla, baja, y al terminar vuelve al inicio. Tarda unos 20 segundos.

  python okx_ordenes.py --pantalla    # guarda lo que hay en pantalla en Descargas (para ajustar el script)
  python okx_ordenes.py --probar      # lee la lista y muestra las órdenes, sin mandar nada
  python okx_ordenes.py               # lee y manda (lo corre telefono/okx.sh)

Usa WEBAPP_URL y ORDENES_TOKEN de ~/.subir-ordenes.env.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from subir_ordenes import leer_env  # noqa: E402

# Los toques para llegar a Órdenes → Completadas desde que se abre la app (textos que se ven en pantalla).
# Se completa con lo que muestre --pantalla en cada paso.
RUTA = ['Órdenes', 'Completadas']   # barra de abajo de P2P → pestaña Completadas
ESTADOS = ('Completada', 'Cancelada', 'En apelación', 'Apelación', 'Pendiente', 'En curso')
FECHA = re.compile(r'^\d{2}/\d{2}/\d{4} \d{2}:\d{2}')
NUMERO = r'[\d.]+(?:,\d+)?'
DESCARGAS = os.path.expanduser('~/storage/downloads')


def adb(*args, salida=True):
    r = subprocess.run(['adb'] + list(args), capture_output=True, text=True, timeout=60)
    return r.stdout if salida else r.returncode


def conectar():
    """Se conecta a la depuración inalámbrica del propio teléfono. El puerto cambia cada vez que se activa."""
    if '\tdevice' in adb('devices'):
        return True
    for linea in adb('mdns', 'services').splitlines():
        m = re.search(r'_adb-tls-connect\._tcp\.?\s+([\d.]+:\d+)', linea)
        if m and 'connected' in adb('connect', m.group(1)):
            return True
    # Si mdns no lo encuentra: probar los puertos que usa Android para la depuración inalámbrica.
    import socket
    for puerto in range(30000, 50000):
        with socket.socket() as so:
            so.settimeout(0.02)
            if so.connect_ex(('127.0.0.1', puerto)) == 0 and 'connected' in adb('connect', '127.0.0.1:%d' % puerto):
                return True
    return False


def bloqueado():
    w = adb('shell', 'dumpsys', 'window')
    return 'mDreamingLockscreen=true' in w or 'mShowingLockscreen=true' in w or 'isKeyguardShowing=true' in w


def textos():
    """Los textos de la pantalla, en orden, con su posición: [(texto, x, y)]."""
    xml = adb('exec-out', 'uiautomator', 'dump', '/dev/tty')
    xml = xml[xml.find('<?xml'):xml.rfind('>') + 1]
    lista = []
    for n in ET.fromstring(xml).iter('node'):
        t = (n.get('text') or n.get('content-desc') or '').strip()
        b = re.findall(r'\d+', n.get('bounds') or '')
        if t and len(b) == 4:
            lista.append((t, (int(b[0]) + int(b[2])) // 2, (int(b[1]) + int(b[3])) // 2))
    return lista, xml


def tocar(texto, intentos=10):
    for _ in range(intentos):
        for t, x, y in textos()[0]:
            if t == texto:
                adb('shell', 'input', 'tap', str(x), str(y))
                time.sleep(2)
                return True
        time.sleep(1.5)
    raise SystemExit('No encontré "%s" en la pantalla de OKX' % texto)


def paquete_okx():
    for linea in adb('shell', 'pm', 'list', 'packages').splitlines():
        p = linea.replace('package:', '').strip()
        if 'okx' in p.lower() or 'okinc' in p.lower():
            return p
    raise SystemExit('No encontré la app de OKX instalada')


def numero(s):
    return float(s.replace('.', '').replace(',', '.'))


def leer_ordenes(lista):
    """Arma las órdenes con los textos de la pantalla. Cada orden empieza en "Comprar USDT" / "Vender USDC"."""
    t = [x[0] for x in lista]
    ordenes, i = [], 0
    while i < len(t):
        m = re.match(r'^(Comprar|Vender)\s*(\w+)$', t[i])
        if not m and t[i] in ('Comprar', 'Vender') and i + 1 < len(t) and re.match(r'^[A-Z]{3,5}$', t[i + 1]):
            m = re.match(r'^(Comprar|Vender)\s*(\w+)$', t[i] + ' ' + t[i + 1])
            i += 1
        if not m:
            i += 1
            continue
        o = {'tipo': m.group(1), 'cripto': m.group(2)}
        j = i + 1
        resto = []
        while j < len(t) and not re.match(r'^(Comprar|Vender)\b', t[j]):
            resto.append(t[j])
            j += 1
        k = 0
        while k < len(resto):
            s = resto[k]
            sig = resto[k + 1] if k + 1 < len(resto) else ''
            if s in ESTADOS:
                o['estado'] = s
            elif FECHA.match(s):
                o['fecha'] = s[:16]
            elif s.startswith('Precio unitario'):
                v = s[len('Precio unitario'):].strip()
                if not v:
                    v, k = sig, k + 1
                p = re.match(r'(%s)\s*([A-Z]{3})' % NUMERO, v)
                if p:
                    o['precio'], o['moneda'] = numero(p.group(1)), p.group(2)
            elif s.startswith('Cantidad'):
                v = s[len('Cantidad'):].strip()
                if not v:
                    v, k = sig, k + 1
                p = re.match(r'(%s)' % NUMERO, v)
                if p:
                    o['cantidad'] = numero(p.group(1))
            elif re.match(r'^%s(\s*[A-Z]{3})?$' % NUMERO, s) and 'monto' not in o and 'cantidad' in o:
                if sig and re.match(r'^[A-Z]{3}$', sig) or re.search(r'[A-Z]{3}$', s):
                    o['monto'] = numero(re.match(NUMERO, s).group(0))
            elif ('@' in s or '***' in s or (re.search(r'[a-zA-Z]', s) and s not in ('Reseñado', 'UYU', 'ARS', 'VES', 'USD')
                  and not re.match(r'^[A-Z]{3}$', s) and 'contraparte' not in o and 'cantidad' in o
                  and not s.startswith(('Precio', 'Cantidad')))):
                o.setdefault('contraparte', s)
            k += 1
        if all(c in o for c in ('fecha', 'cantidad', 'monto', 'moneda', 'estado')):
            o.setdefault('precio', round(o['monto'] / o['cantidad'], 4) if o['cantidad'] else 0)
            o.setdefault('contraparte', '')
            ordenes.append(o)
        i = j
    return ordenes


def recorrer(max_pantallas):
    vistas = {}
    for _ in range(max_pantallas):
        nuevas = 0
        for o in leer_ordenes(textos()[0]):
            ref = (o['fecha'], o['tipo'], o['cripto'], o['cantidad'], o['monto'])
            if ref not in vistas:
                vistas[ref] = o
                nuevas += 1
        if not nuevas:
            break
        adb('shell', 'input', 'swipe', '500', '1700', '500', '600', '400')
        time.sleep(2)
    return list(vistas.values())


def subir(cfg, lista):
    cuerpo = json.dumps({'ordenesOKX': lista, 'token': cfg['ORDENES_TOKEN']}).encode()
    req = urllib.request.Request(cfg['WEBAPP_URL'], data=cuerpo, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read().decode('utf-8', 'replace')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--pantalla', action='store_true')
    ap.add_argument('--probar', action='store_true')
    ap.add_argument('--pantallas', type=int, default=8, help='cuántas veces baja en la lista (8 ≈ 2 días)')
    args = ap.parse_args()
    if not conectar():
        raise SystemExit('Sin ADB: activá Depuración inalámbrica (Opciones de desarrollador) y que haya wifi')
    if args.pantalla:
        print('Tenés 10 segundos: andá a la pantalla de OKX que quieras guardar. Vibra cuando termina.', flush=True)
        time.sleep(10)
        lista, xml = textos()
        subprocess.run(['termux-vibrate'], check=False)
        ruta = os.path.join(DESCARGAS, time.strftime('okx_pantalla_%H%M%S.xml'))
        with open(ruta, 'w') as f:
            f.write(xml)
        print('\n'.join(t for t, _, _ in lista))
        print('\nGuardado en', ruta)
        sys.exit(0)
    if bloqueado():
        raise SystemExit('Teléfono bloqueado: no leo OKX esta vez')
    cfg = leer_env()
    adb('shell', 'monkey', '-p', paquete_okx(), '-c', 'android.intent.category.LAUNCHER', '1')
    time.sleep(6)
    for paso in RUTA:
        tocar(paso)
    lista = recorrer(args.pantallas)
    adb('shell', 'input', 'keyevent', 'KEYCODE_HOME')
    if args.probar:
        for o in lista:
            print(o)
        print('Órdenes leídas:', len(lista))
    else:
        print(time.strftime('%Y-%m-%d %H:%M'), len(lista), 'órdenes OKX ->', subir(cfg, lista)[:300], flush=True)
