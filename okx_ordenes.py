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
# OKX abre en el inicio del Exchange (animado: ahí uiautomator a veces no responde). Por eso se cierra y se abre de
# cero, se toca el menú de arriba a la izquierda por posición, y desde ahí se sigue por los textos de la pantalla.
# La portada de P2P también tiene un carrusel animado: Órdenes (barra de abajo) y Completadas se tocan por posición.
MENU = (0.083, 0.0625)          # ícono de cuadritos, en fracción del ancho y alto de la pantalla
ORDENES = (0.328, 0.904)        # "Órdenes" en la barra de abajo de P2P
COMPLETADAS = (0.397, 0.123)    # pestaña "Completadas"
RUTA = ['Trading P2P']          # en el menú: se busca por el texto
DESCARGAS = os.path.expanduser('~/storage/downloads')


def adb(*args, salida=True, espera=60):
    r = subprocess.run(['adb'] + list(args), capture_output=True, text=True, timeout=espera)
    return r.stdout if salida else r.returncode


def adb_bytes(*args, espera=60):
    """Como adb(...) pero devuelve bytes (para la pantalla cruda)."""
    return subprocess.run(['adb'] + list(args), capture_output=True, timeout=espera).stdout


def tamano_pantalla():
    m = re.search(r'(\d+)x(\d+)', adb('shell', 'wm', 'size'))
    return (int(m.group(1)), int(m.group(2))) if m else (1080, 2400)


def conectar():
    """Se conecta y deja elegido UN solo dispositivo: si quedan dos conexiones (la vieja del puerto 5555 y la
    nueva de la depuración inalámbrica) adb no sabe a cuál hablarle y todo sale vacío."""
    os.environ.pop('ANDROID_SERIAL', None)
    if not _conectar():
        return False
    vivos = []
    for linea in adb('devices').splitlines()[1:]:
        partes = linea.split('\t')
        if len(partes) < 2:
            continue
        if partes[1].strip() == 'device':
            vivos.append(partes[0])
        else:                                   # offline / unauthorized: conexión muerta, se saca
            adb('disconnect', partes[0])
    if not vivos:
        return False
    os.environ['ANDROID_SERIAL'] = '127.0.0.1:5555' if '127.0.0.1:5555' in vivos else vivos[0]
    return True


def _conectar():
    """Se conecta a la depuración inalámbrica del propio teléfono. El puerto cambia cada vez que se activa."""
    if '\tdevice' in adb('devices'):
        return True
    # Puerto fijo 5555 (se activa una vez con "adb tcpip 5555" y dura hasta reiniciar el teléfono):
    # no depende de que la Depuración inalámbrica siga prendida ni del wifi.
    if 'connected' in adb('connect', '127.0.0.1:5555') and '\tdevice' in adb('devices'):
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
    """Los textos de la pantalla, en orden: [(texto, x, y, id)] (id = resource-id sin el paquete)."""
    for _ in range(3):   # con animaciones en pantalla, uiautomator puede tardar o colgarse
        try:
            xml = adb('exec-out', 'uiautomator', 'dump', '/dev/tty', espera=20)
            if '<hierarchy' in xml:
                break
        except subprocess.TimeoutExpired:
            adb('shell', 'pkill', '-f', 'uiautomator')   # si no, el siguiente intento espera al colgado
        time.sleep(2)
    else:
        return [], ''
    xml = xml[xml.find('<?xml'):xml.rfind('>') + 1]
    lista = []
    for n in ET.fromstring(xml).iter('node'):
        t = (n.get('text') or n.get('content-desc') or '').strip()
        b = re.findall(r'\d+', n.get('bounds') or '')
        if t and len(b) == 4:
            lista.append((t, (int(b[0]) + int(b[2])) // 2, (int(b[1]) + int(b[3])) // 2,
                          (n.get('resource-id') or '').split('/')[-1]))
    return lista, xml


def tocar(texto, intentos=10, parcial=False):
    """Toca el primer texto de la pantalla igual a `texto` (o que lo contenga, con parcial). False si no aparece."""
    for _ in range(intentos):
        for t, x, y, _ in textos()[0]:
            if t == texto or (parcial and texto.lower() in t.lower()):
                adb('shell', 'input', 'tap', str(x), str(y))
                time.sleep(2)
                return True
        time.sleep(1.5)
    return False


# Carteles que OKX a veces muestra al abrir (novedades, promociones): se cierran tocando uno de estos textos.
CERRAR = ('Cerrar', 'Omitir', 'Ahora no', 'Más tarde', 'Entendido', 'Saltar', 'No, gracias')


def cerrar_carteles():
    for t, x, y, _ in textos()[0]:
        if t in CERRAR:
            adb('shell', 'input', 'tap', str(x), str(y))
            time.sleep(2)
            return True
    return False


def guardar_fallo(motivo):
    """Guarda una captura y lo que había en pantalla en Descargas, para ver dónde se trabó. Termina con error."""
    hora = time.strftime('%H%M%S')
    adb('shell', 'screencap', '-p', '/sdcard/Download/okx_fallo_%s.png' % hora)
    with open(os.path.join(DESCARGAS, 'okx_fallo_%s.xml' % hora), 'w') as f:
        f.write(textos()[1])
    adb('shell', 'input', 'keyevent', 'KEYCODE_HOME')
    raise SystemExit('%s. Guardé una captura en Descargas (okx_fallo_%s.png)' % (motivo, hora))


def en_completadas():
    lista = textos()[0]
    return bool(leer_ordenes(lista)) or any(rid == 'tv_order_type' for _, _, _, rid in lista)


def llegar_a_completadas(paquete):
    """Abre OKX de cero y llega a P2P → Órdenes → Completadas. Busca los botones por su texto y, si no los ve,
    toca por posición. Si algo falla (un cartel nuevo, la app tardó), cierra OKX y prueba de nuevo, hasta 3 veces."""
    ancho, alto = tamano_pantalla()
    for intento in range(1, 4):
        adb('shell', 'am', 'force-stop', paquete)
        adb('shell', 'monkey', '-p', paquete, '-c', 'android.intent.category.LAUNCHER', '1')
        # El menú de arriba a la izquierda tarda en cargar y en el inicio (animado) leer la pantalla puede colgarse:
        # se toca por posición y se mira si apareció el menú (ahí sí se puede leer). Si no, se espera más y se repite.
        llego = False
        for espera in (8, 6, 8, 10):
            time.sleep(espera)
            adb('shell', 'input', 'tap', str(int(ancho * MENU[0])), str(int(alto * MENU[1])))
            time.sleep(3)
            if tocar('Trading P2P', intentos=2):
                llego = True
                break
            cerrar_carteles()
        if not llego:
            print('Intento %d: el menú no abrió o no tiene "Trading P2P"' % intento, file=sys.stderr, flush=True)
            continue
        time.sleep(3)
        # La portada de P2P tiene un carrusel animado: Órdenes y Completadas se tocan por posición, sin leer.
        for fx, fy in (ORDENES, COMPLETADAS):
            adb('shell', 'input', 'tap', str(int(ancho * fx)), str(int(alto * fy)))
            time.sleep(3)
        if en_completadas():
            return
        if tocar('Completadas', intentos=2) and en_completadas():   # por si la pestaña se movió de lugar
            return
        print('Intento %d: no quedé en Completadas' % intento, file=sys.stderr, flush=True)
    guardar_fallo('No pude llegar a Órdenes → Completadas en OKX')


def paquete_okx():
    for linea in adb('shell', 'pm', 'list', 'packages').splitlines():
        p = linea.replace('package:', '').strip()
        if 'okx' in p.lower() or 'okinc' in p.lower():
            return p
    raise SystemExit('No encontré la app de OKX instalada')


def numero(s):
    return float(s.replace('.', '').replace(',', '.'))


# Cada tarjeta de la lista Completadas (vista en la pantalla de john, 03/11/2026): id del texto → campo.
CAMPOS = {'tv_type': 'cripto', 'tv_status': 'estado', 'tv_tags': 'fecha', 'tv_price': 'precio',
          'tv_price_quote_symbol': 'moneda', 'tv_total': 'monto', 'tv_volume': 'cantidad', 'tv_username': 'contraparte'}
NUMEROS = ('precio', 'monto', 'cantidad')


def leer_ordenes(lista):
    """Arma las órdenes con los textos de la pantalla. Cada tarjeta empieza en tv_order_type (Comprar / Vender).
    Las tarjetas cortadas abajo de la pantalla se descartan: aparecen enteras al bajar."""
    ordenes, o = [], None
    for t, _, _, rid in lista + [('', 0, 0, 'tv_order_type')]:
        if rid == 'tv_order_type':
            if o and all(c in o for c in ('fecha', 'cantidad', 'monto', 'moneda', 'estado', 'precio', 'contraparte')):
                o['fecha'] = o['fecha'][:16]
                ordenes.append(o)
            o = {'tipo': t} if t in ('Comprar', 'Vender') else None
        elif o is not None and rid in CAMPOS:
            campo = CAMPOS[rid]
            o[campo] = numero(t) if campo in NUMEROS else t
    return ordenes


def fecha_ms(fecha):
    """'03/11/2026 15:43' (hora del teléfono) → milisegundos."""
    return int(time.mktime(time.strptime(fecha, '%d/%m/%Y %H:%M')) * 1000)


HASTA = os.path.expanduser('~/.okx_hasta')   # la orden más nueva que ya llegó a la planilla


def desde_ms(dias):
    """Desde cuándo leer: 1 hora antes de la última orden que ya llegó a la planilla, y nunca más de `dias` atrás."""
    tope = (time.time() - dias * 86400) * 1000
    try:
        with open(HASTA) as f:
            return max(tope, int(f.read().strip()) - 3600 * 1000)
    except (OSError, ValueError):
        return tope


def recorrer(max_pantallas, dias=3):
    """Lee la pantalla, baja un poco más de media pantalla (sin envión, para no saltear tarjetas) y repite.
    Para cuando una pantalla ya no trae nada nuevo (el final de la lista o lo ya visto)."""
    vistas = {}
    ancho, alto = tamano_pantalla()
    for n in range(1, max_pantallas + 1):
        lista = textos()[0]
        if not lista:
            lista = textos()[0]   # un intento más si la lectura falló
        nuevas = 0
        for o in leer_ordenes(lista):
            ref = (o['fecha'], o['tipo'], o['cripto'], o['cantidad'], o['monto'])
            if ref not in vistas:
                vistas[ref] = o
                nuevas += 1
        print('Pantalla %d: %s, %d órdenes nuevas' % (n, 'leída' if lista else 'NO se pudo leer', nuevas),
              file=sys.stderr, flush=True)
        if not nuevas:
            break
        desde = desde_ms(dias)
        if min(fecha_ms(o['fecha']) for o in vistas.values()) < desde:
            break   # ya llegó a órdenes de hace más de `dias` días: lo de antes ya está en la planilla
        x = str(ancho // 2)
        adb('shell', 'input', 'swipe', x, str(int(alto * 0.75)), x, str(int(alto * 0.35)), '1500')
        time.sleep(2)
    desde = desde_ms(dias)
    return [o for o in vistas.values() if fecha_ms(o['fecha']) >= desde]


def subir(cfg, lista):
    cuerpo = json.dumps({'ordenesOKX': lista, 'token': cfg['ORDENES_TOKEN']}).encode()
    req = urllib.request.Request(cfg['WEBAPP_URL'], data=cuerpo, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read().decode('utf-8', 'replace')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--pantalla', action='store_true')
    ap.add_argument('--probar', action='store_true')
    ap.add_argument('--enlaces', action='store_true', help='muestra los enlaces directos que acepta la app de OKX')
    ap.add_argument('--abrir', help='abre OKX con este enlace y muestra qué pantalla quedó')
    ap.add_argument('--actividad', action='store_true', help='muestra qué pantalla de OKX está abierta (tras --espera)')
    ap.add_argument('--espera', type=int, default=30, help='segundos antes de guardar la pantalla (--pantalla)')
    ap.add_argument('--pantallas', type=int, default=40, help='máximo de veces que baja en la lista')
    ap.add_argument('--dias', type=int, default=3, help='lee las órdenes de los últimos N días')
    args = ap.parse_args()
    if not conectar():
        raise SystemExit('Sin ADB: activá Depuración inalámbrica (Opciones de desarrollador) y que haya wifi')
    if args.enlaces:
        dump = adb('shell', 'dumpsys', 'package', paquete_okx())
        vistos = []
        for linea in dump.splitlines():
            linea = linea.strip()
            if re.match(r'(Scheme|Authority|Path|PathPrefix|PathPattern):', linea) and linea not in vistos:
                vistos.append(linea)
        ruta = os.path.join(DESCARGAS, 'okx_enlaces.txt')
        with open(ruta, 'w') as f:
            f.write('\n'.join(vistos))
        print('\n'.join(vistos[:80]))
        print('\n%d líneas, guardadas en %s' % (len(vistos), ruta))
        sys.exit(0)
    if args.abrir:
        paquete = paquete_okx()
        adb('shell', 'am', 'force-stop', paquete)
        print(adb('shell', 'am', 'start', '-a', 'android.intent.action.VIEW', '-d', args.abrir, paquete))
        time.sleep(12)
        print('\n'.join(t for t, _, _, _ in textos()[0][:40]))
        sys.exit(0)
    if args.actividad:
        print('En %d segundos miro qué pantalla está abierta: dejá OKX en Completadas y esperá a que vibre.'
              % args.espera, flush=True)
        time.sleep(args.espera)
        subprocess.run(['termux-vibrate'], check=False)
        for linea in adb('shell', 'dumpsys', 'activity', 'activities').splitlines():
            if 'ResumedActivity' in linea:
                print(linea.strip())
        sys.exit(0)
    if args.pantalla:
        print('Ya podés salir de Termux. En %d segundos guarda lo que haya en pantalla: '
              'dejá OKX en la pantalla que quieras y esperá a que vibre.' % args.espera, flush=True)
        time.sleep(args.espera)
        lista, xml = textos()
        subprocess.run(['termux-vibrate'], check=False)
        ruta = os.path.join(DESCARGAS, time.strftime('okx_pantalla_%H%M%S.xml'))
        with open(ruta, 'w') as f:
            f.write(xml)
        print('\n'.join(t for t, _, _, _ in lista))
        print('\nGuardado en', ruta)
        sys.exit(0)
    if bloqueado():
        raise SystemExit('Teléfono bloqueado: no leo OKX esta vez')
    cfg = leer_env()
    llegar_a_completadas(paquete_okx())
    lista = recorrer(args.pantallas, args.dias)
    adb('shell', 'input', 'keyevent', 'KEYCODE_HOME')
    if args.probar:
        for o in lista:
            print(o)
        print('Órdenes leídas:', len(lista))
    else:
        r = subir(cfg, lista)
        print(time.strftime('%Y-%m-%d %H:%M'), len(lista), 'órdenes OKX ->', r[:300], flush=True)
        if '"ok":true' in r.replace(' ', '') and lista:
            with open(HASTA, 'w') as f:
                f.write(str(max(fecha_ms(o['fecha']) for o in lista)))
