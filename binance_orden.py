#!/usr/bin/env python3
"""Arma la orden P2P de la pre-orden en la app de Binance y se frena UN PASO ANTES de colocarla.

  python binance_orden.py "LINK"            # el recorrido completo (lo corre telefono/binance_orden.sh)
  python binance_orden.py --grabar          # 150 s guardando cada pantalla mientras hacés el camino a mano
  python binance_orden.py --pantalla NOMBRE # en 8 s guarda la pantalla en Descargas

LINK es el del anuncio que eligió la pre-orden (Apps Script, 9_P2P.gs):
  https://c2c.binance.com/es-LA/adv?code=<adNo>&monto=<Bs>&pago=<método>

Cómo trabaja: en cada vuelta lee la pantalla, decide CUÁL es (solo conoce las grabadas, ver PANTALLAS) y hace la
única acción que corresponde. Si la pantalla no es ninguna conocida, o repite la misma acción 3 veces sin avanzar,
se frena y guarda captura + xml en Descargas (binance_*). No adivina: lo que no está grabado no se toca.

En la pantalla "Vender USDT" solo toca "En VES" y el campo del monto. NUNCA la casilla ni "Realizar Orden".
Los links directos a anuncios/perfiles/P2P no sirven (probados 25 el 15/11/2026): se va siempre por la lista.
"""
import collections
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from okx_ordenes import adb, bloqueado, conectar, tamano_pantalla  # noqa: E402

DESCARGAS = os.path.expanduser('~/storage/downloads')
LOG_DIR = DESCARGAS if os.path.isdir(DESCARGAS) else '.'
DETALLE = 'https://p2p.binance.com/bapi/c2c/v2/public/c2c/adv/selected-adv/'
PAQUETES = ('com.binance.dev', 'com.binance.android', 'com.binance.app')
INICIO_ACT = 'com.eaas.launcher.activities.main.MainActivity'
BOTON_P2P = (0.152, 0.305)   # ícono P2P del inicio (captura del 15/11): el inicio es animado y no se deja leer
CERRAR = ('cerrar', 'omitir', 'ahora no', 'mas tarde', 'entendido', 'saltar', 'no gracias', 'ok')
# Segunda barrera: dentro de la orden, aunque el toque esté permitido, nada que diga esto.
PROHIBIDO = re.compile(r'vender|sell|confirm|colocar|realizar|crear|pagar|enviar|continuar|siguiente|aceptar|'
                       r'haz clic|place|todo')
MAX_VUELTAS = 30


class Frenado(Exception):
    """El recorrido se frenó: motivo para la notificación."""


# ---------- utilidades ----------

def norm(s):
    s = unicodedata.normalize('NFD', str(s or '')).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', s)).strip()


def compacto(s):
    """Para comparar textos: sin acentos, espacios ni signos. Si no queda nada (apodo en chino), el texto tal cual."""
    return norm(s).replace(' ', '') or str(s or '').strip()


def numero(s):
    """'5,000' -> 5000.0, '5000' -> 5000.0, 'Monto' -> None (Binance usa coma de miles y punto decimal)."""
    s = re.sub(r'[^\d.,]', '', str(s or '')).replace(',', '')
    try:
        return float(s)
    except ValueError:
        return None


def fmt_monto(m):
    return ('%.2f' % m).rstrip('0').rstrip('.')


def paso(texto):
    print(time.strftime('%H:%M:%S ') + texto, flush=True)


def avisar(titulo, texto):
    subprocess.run(['termux-notification', '--id', 'binance-orden', '--title', titulo, '--content', texto],
                   check=False)


# ---------- 1. El anuncio ----------

def leer_link(link):
    q = urllib.parse.parse_qs(urllib.parse.urlparse(link.strip()).query)
    ad = (q.get('code') or q.get('advNo') or [''])[0]
    if not ad.isdigit():
        raise Frenado('El link no trae el número de anuncio (code=...)')
    return ad, float((q.get('monto') or ['0'])[0] or 0), (q.get('pago') or [''])[0]


def buscar(o, claves):
    """Primer valor de alguna de las claves, buscando en todo el JSON."""
    if isinstance(o, dict):
        for k in claves:
            if o.get(k) not in (None, '', []):
                return o[k]
        o = list(o.values())
    if isinstance(o, list):
        for v in o:
            r = buscar(v, claves) if isinstance(v, (dict, list)) else None
            if r not in (None, '', []):
                return r
    return None


def detalle_anuncio(ad):
    req = urllib.request.Request(DETALLE + ad, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=15) as r:
        datos = json.load(r).get('data')
    if not datos:
        raise Frenado('Binance no devolvió el anuncio %s: puede que ya no exista' % ad)
    return {
        'apodo': buscar(datos, ['nickName']) or '',
        'precio': float(buscar(datos, ['price']) or 0),
        'min': float(buscar(datos, ['minSingleTransAmount']) or 0),
        'max': float(buscar(datos, ['dynamicMaxSingleTransAmount', 'maxSingleTransAmount']) or 0),
        'metodos': [{'id': m.get('identifier') or '', 'nombre': m.get('tradeMethodName') or m.get('identifier') or ''}
                    for m in buscar(datos, ['tradeMethods']) or [] if isinstance(m, dict)],
    }


def elegir_metodo(det, pago):
    """El método de pago es obligatorio: tiene que estar en el anuncio. Sin pago en el link, solo si hay uno."""
    ids = [m['id'] for m in det['metodos']]
    if pago:
        for m in det['metodos']:
            if compacto(m['id']) == compacto(pago) or compacto(m['nombre']) == compacto(pago):
                return m
        raise Frenado('El anuncio ya no acepta %s (acepta %s)' % (pago, ', '.join(ids) or 'nada'))
    if len(det['metodos']) == 1:
        return det['metodos'][0]
    raise Frenado('El link no dice el método y el anuncio tiene varios (%s): subí el Apps Script nuevo' % ', '.join(ids))


def es_metodo(texto, metodo):
    t = compacto(texto)
    return bool(t) and t in (compacto(metodo['nombre']), compacto(metodo['id']))


# ---------- 2. Leer la pantalla ----------

PAQ = ''   # paquete de Binance: solo se miran sus nodos (si no, lo que imprime Termux da falsos positivos)
N = collections.namedtuple('N', 't x y clase rid')


def paquete_binance():
    global PAQ
    for linea in adb('shell', 'pm', 'list', 'packages').splitlines():
        p = linea.replace('package:', '').strip()
        if p in PAQUETES:
            PAQ = p
            return p
    raise Frenado('No encuentro la app de Binance instalada')


def volcar(espera=20, intentos=3):
    """El XML de la pantalla. Con animaciones uiautomator se cuelga: se corta y se reintenta. '' si no se pudo."""
    for _ in range(intentos):
        try:
            xml = adb('exec-out', 'uiautomator', 'dump', '/dev/tty', espera=espera)
            if '<hierarchy' in xml:
                return xml[xml.find('<?xml'):xml.rfind('>') + 1]
        except subprocess.TimeoutExpired:
            adb('shell', 'pkill', '-f', 'uiautomator')
        time.sleep(1)
    return ''


def leer_nodos(xml):
    lista = []
    if not xml:
        return lista
    for n in ET.fromstring(xml.encode()).iter('node'):
        if PAQ and n.get('package') != PAQ:
            continue
        b = [int(v) for v in re.findall(r'\d+', n.get('bounds') or '')]
        if len(b) != 4:
            continue
        t = (n.get('text') or n.get('content-desc') or '').strip()
        clase = (n.get('class') or '').split('.')[-1]
        if t or clase == 'EditText':
            lista.append(N(t, (b[0] + b[2]) // 2, (b[1] + b[3]) // 2, clase,
                           (n.get('resource-id') or '').split('/')[-1]))
    return lista


def nodos(espera=20, intentos=3):
    return leer_nodos(volcar(espera, intentos))


def con(ns, *textos):
    """Nodos cuyo texto es igual (sin acentos ni mayúsculas) a alguno de los textos."""
    c = [compacto(t) for t in textos]
    return [n for n in ns if compacto(n.t) in c]


def que_veo(ns):
    return ' | '.join(n.t for n in ns if n.t)[:300]


def al_frente():
    for linea in adb('shell', 'dumpsys', 'window').splitlines():
        if 'mCurrentFocus' in linea:
            return linea.strip()
    return ''


def guardar(nombre):
    base = 'binance_%s_%s' % (nombre, time.strftime('%H%M%S'))
    adb('shell', 'screencap', '-p', '/sdcard/Download/%s.png' % base)
    with open(os.path.join(LOG_DIR, base + '.xml'), 'w') as f:
        f.write(volcar(15, 1))
    return base


def frenar(motivo, nombre='fallo', ns=None):
    paso('al frente: %s' % al_frente())
    if ns is not None:
        paso('veo: %s' % (que_veo(ns) or '(nada de Binance)'))
    raise Frenado('%s. Guardé la pantalla en Descargas (%s.png)' % (motivo, guardar(nombre)))


# Las pantallas que se conocen (todas grabadas). Lo demás es "desconocida" y frena.
PANTALLAS = {
    'orden':   'Vender USDT: monto, "Vendes", tu método, términos y Realizar Orden (grabación 05/06)',
    'monto':   'hoja "Quiero vender" (chip Monto, 15/11 02:13) o panel "Filtrar" (embudo, grabación 02/03)',
    'divisa':  'Seleccionar divisa (grabación 01)',
    'activo':  'Seleccionar activo (se abrió por error el 15/11 02:08)',
    'p2p':     'lista de P2P: Comprar / Vender arriba, barra P2P · Órdenes · Anuncios (grabación 04)',
    'inicio':  'inicio de Binance: animado, uiautomator no lo lee (o se lee P2P / Depositar)',
    'cartel':  'un cartel con Cerrar / Omitir / OK…',
}


def que_es(ns):
    if con(ns, 'Vendes') and (con(ns, 'Realizar Orden') or any(norm(n.t).startswith('info del anunciante')
                                                                 for n in ns)):
        return 'orden'
    if con(ns, 'Confirmar') and con(ns, 'Restablecer') and any(n.clase == 'EditText' for n in ns):
        return 'monto'
    if con(ns, 'Seleccionar divisa'):
        return 'divisa'
    if con(ns, 'Seleccionar activo'):
        return 'activo'
    if con(ns, 'Comprar') and con(ns, 'Vender') and con(ns, 'Anuncios'):
        return 'p2p'
    if not ns or con(ns, 'P2P', 'Depositar', 'Exchange'):
        return 'inicio'
    if any(norm(n.t) in CERRAR for n in ns):
        return 'cartel'
    return 'desconocida'


# ---------- Toques ----------

EN_ORDEN = False   # desde que se toca el Vender del anunciante: solo toques marcados como permitidos


def tocar(que, x, y, en_orden_ok=False):
    if EN_ORDEN and (not en_orden_ok or PROHIBIDO.search(norm(que))):
        raise Frenado('Por seguridad no toqué "%s"' % que)
    paso('toco %s' % que)
    adb('shell', 'input', 'tap', str(x), str(y))
    time.sleep(1.5)


def tecla(nombre):
    paso('tecla %s' % nombre)
    adb('shell', 'input', 'keyevent', 'KEYCODE_' + nombre)
    time.sleep(1.5)


def teclado_visible():
    return 'mInputShown=true' in adb('shell', 'dumpsys', 'input_method')


def escribir(campo, valor, en_orden_ok=False):
    """Toca el campo, borra lo que tenga y escribe el valor."""
    tocar('el campo del monto (%s)' % (campo.t or 'vacío'), campo.x, campo.y, en_orden_ok)
    adb('shell', 'input', 'keyevent', 'KEYCODE_MOVE_END')
    for _ in range(14):
        adb('shell', 'input', 'keyevent', 'KEYCODE_DEL')
    paso('escribo %s' % valor)
    adb('shell', 'input', 'text', valor)
    time.sleep(1.5)


# ---------- 3. Traer Binance ----------

def traer_binance():
    """Pone Binance al frente: actividad de inicio, monkey y, si nada anduvo, el link de app.binance.com (el 15/11
    abrió la app las 25 veces, con un cartel "Este enlace no funciona" que se cierra con OK)."""
    formas = (
        ('actividad de inicio', ('shell', 'am', 'start', '-n', '%s/%s' % (PAQ, INICIO_ACT))),
        ('monkey', ('shell', 'monkey', '-p', PAQ, '-c', 'android.intent.category.LAUNCHER', '1')),
        ('link app.binance.com', ('shell', 'am', 'start', '-a', 'android.intent.action.VIEW',
                                  '-d', 'https://app.binance.com/es-LA', PAQ)),
    )
    for nombre, cmd in formas:
        adb('shell', 'cmd', 'statusbar', 'collapse')     # si corrió desde la notificación, la cortina está abierta
        salida = ' '.join(adb(*cmd).split())
        paso('abro Binance (%s): %s' % (nombre, salida[-100:] or 'sin salida'))
        for _ in range(6):
            time.sleep(2)
            f = al_frente()
            if PAQ in f:
                return True
            if 'NotificationShade' in f:
                adb('shell', 'cmd', 'statusbar', 'collapse')
        paso('al frente sigue: %s' % al_frente())
    return False


# ---------- 4. Qué hacer en cada pantalla ----------

def fila_filtros(ns):
    """La pestaña Vender, la moneda (arriba a la derecha) y la fila de filtros [activo, monto, pago] de la lista."""
    tab = sorted(con(ns, 'Vender'), key=lambda n: n.y)[0]
    moneda = [n for n in ns if abs(n.y - tab.y) < 45 and n.x > 700 and re.fullmatch(r'[A-Z]{3}', n.t)]
    fila = sorted((n for n in ns if tab.y + 50 < n.y < tab.y + 180 and n.x < 1000 and n.t), key=lambda n: n.x)
    return tab, (moneda[0] if moneda else None), fila


def en_p2p(ns, metodo, monto, estado):
    """Lista de P2P: deja Vender · USDT · VES · monto · método, en ese orden, de a un toque por vuelta.
    Devuelve el nombre de lo que hizo (para contar repeticiones) o 'listo' si los filtros ya están."""
    tab, moneda, fila = fila_filtros(ns)
    if not estado.get('pestaña'):
        estado['pestaña'] = True
        tocar('la pestaña Vender', tab.x, tab.y)
        return 'pestaña'
    if moneda is None:
        frenar('No encontré la moneda arriba a la derecha', 'moneda', ns)
    if len(fila) < 3:
        frenar('No encontré la fila de filtros (USDT · Monto · Pago)', 'filtros', ns)
    activo, chip_monto, chip_pago = fila[:3]
    if activo.t != 'USDT':
        frenar('El activo dice %s: ponelo en USDT a mano y probá de nuevo' % activo.t, 'activo', ns)
    if moneda.t != 'VES':
        tocar('la moneda (%s)' % moneda.t, moneda.x, moneda.y)
        return 'moneda'
    if numero(chip_monto.t) != monto:
        tocar('el filtro de monto (%s)' % chip_monto.t, chip_monto.x, chip_monto.y)
        return 'filtro de monto'
    if not es_metodo(chip_pago.t, metodo):
        tocar('el filtro de método (%s)' % chip_pago.t, chip_pago.x, chip_pago.y)
        return 'filtro de método'
    paso('filtros: Vender · USDT · VES · %s · %s' % (chip_monto.t, chip_pago.t))
    return 'listo'


def en_monto(ns, monto):
    """Hoja "Quiero vender" / panel "Filtrar": escribe el monto y toca Confirmar."""
    campo = [n for n in ns if n.clase == 'EditText'][0]
    if numero(campo.t) != monto:
        escribir(campo, fmt_monto(monto))
        ns = nodos()
        if not con(ns, 'Confirmar') and teclado_visible():   # el teclado tapa Confirmar: se baja
            tecla('BACK')
            ns = nodos()
        if que_es(ns) != 'monto':
            frenar('Se cerró el panel del monto antes de confirmar', 'panel_monto', ns)
        campo = [n for n in ns if n.clase == 'EditText'][0]
        if numero(campo.t) != monto:
            frenar('Escribí %s pero el campo dice "%s"' % (fmt_monto(monto), campo.t), 'panel_monto', ns)
    ok = con(ns, 'Confirmar')[0]
    tocar('Confirmar (monto %s)' % campo.t, ok.x, ok.y)


def buscar_en_lista(apodo):
    """Busca el apodo bajando hasta 10 pantallas y toca el Vender de SU tarjeta (el primero debajo del apodo)."""
    global EN_ORDEN
    ancho, alto = tamano_pantalla()
    for _ in range(10):
        ns = nodos()
        for fila in (n for n in ns if compacto(n.t) == compacto(apodo)):
            debajo = sorted((n for n in con(ns, 'Vender') if fila.y < n.y < alto * 0.9), key=lambda n: n.y)
            if debajo:
                tocar('Vender de %s' % apodo, debajo[0].x, debajo[0].y)
                EN_ORDEN = True
                return
        adb('shell', 'input', 'swipe', str(ancho // 2), str(int(alto * .75)), str(ancho // 2),
            str(int(alto * .35)), '500')
        time.sleep(1.5)
    frenar('No encontré a %s en la lista (¿lo tomó otro, cambió el precio o se quedó sin USDT?)' % apodo, 'lista')


def llegar_a_la_orden(apodo, metodo, monto):
    """El bucle: lee, reconoce la pantalla, hace UNA acción. Termina en la pantalla "Vender USDT" del anunciante."""
    ancho, alto = tamano_pantalla()
    veces = collections.Counter()
    estado = {}
    for _ in range(MAX_VUELTAS):
        if PAQ not in al_frente():
            veces['traer'] += 1
            if veces['traer'] > 2 or not traer_binance():
                frenar('Binance no se abrió', 'inicio')
            time.sleep(3)
            continue
        ns = nodos(espera=8, intentos=1)   # corto: el inicio es animado y uiautomator se cuelga ahí
        p = que_es(ns)
        if EN_ORDEN and p != 'orden':      # ya tocó el Vender del anunciante: solo puede esperar la orden
            if estado.get('esperé orden'):
                frenar('Toqué Vender de %s pero no se abrió la orden' % apodo, 'orden', ns)
            estado['esperé orden'] = True
            time.sleep(2)
            continue
        if p == 'orden':
            if EN_ORDEN:
                return ns
            tecla('BACK')                   # quedó abierta una orden vieja (de otra vez): se sale sin tocar nada
            hecho = 'salir de una orden vieja'
        elif p == 'p2p':
            hecho = en_p2p(ns, metodo, monto, estado)
            if hecho == 'listo':
                buscar_en_lista(apodo)
                hecho = 'buscar a %s' % apodo
        elif p == 'monto':
            en_monto(ns, monto)
            hecho = 'monto'
        elif p == 'divisa':
            ves = sorted(con(ns, 'VES'), key=lambda n: n.y)
            if not ves:
                frenar('No encontré VES en Seleccionar divisa', 'divisa', ns)
            tocar('VES', ves[0].x, ves[0].y)
            hecho = 'VES'
        elif p == 'activo':
            tecla('BACK')                   # no hace falta: USDT es el que está; se cierra sin elegir
            hecho = 'cerrar Seleccionar activo'
        elif p == 'inicio':
            p2p = con(ns, 'P2P')
            if p2p:
                tocar('P2P', p2p[0].x, p2p[0].y)
            else:
                paso('no leo el inicio (animado): toco P2P por posición')
                adb('shell', 'input', 'tap', str(int(ancho * BOTON_P2P[0])), str(int(alto * BOTON_P2P[1])))
                time.sleep(4)
            hecho = 'P2P'
        elif p == 'cartel':
            n = [n for n in ns if norm(n.t) in CERRAR][0]
            tocar('"%s" del cartel' % n.t, n.x, n.y)
            hecho = 'cartel'
        else:
            if estado.get('esperé') or EN_ORDEN:
                frenar('Pantalla que no conozco (no está grabada): grabala con --grabar', 'desconocida', ns)
            estado['esperé'] = True         # una vuelta de gracia: puede que estuviera cargando
            time.sleep(2)
            continue
        paso('[%s] %s' % (p, hecho))
        veces[hecho] += 1
        if veces[hecho] > 3:
            frenar('Hice "%s" %d veces y la pantalla no avanza' % (hecho, veces[hecho] - 1), 'trabado', ns)
    frenar('Demasiadas vueltas sin llegar a la orden', 'trabado')


# ---------- 5. Completar la orden (sin colocarla) ----------

def completar_orden(ns, apodo, metodo, monto):
    """Pantalla "Vender USDT" (grabación 05): deja el monto en VES y revisa que el método sea el tuyo.
    Solo toca "En VES" y el campo. La fila del método NO se toca (la lista de tus métodos no está grabada):
    si no es el tuyo, avisa. La casilla y "Realizar Orden" quedan para vos."""
    if not con(ns, apodo):
        paso('ojo: no veo a %s en la orden' % apodo)
    campos = [n for n in ns if n.clase == 'EditText']
    if not campos:
        frenar('No encontré dónde escribir el monto', 'orden', ns)
    if not any(n.t == 'VES' and abs(n.y - campos[0].y) < 70 for n in ns):   # el campo está en USDT
        en_ves = con(ns, 'En VES')
        if not en_ves:
            frenar('El monto está en USDT y no encontré "En VES"', 'orden', ns)
        tocar('"En VES"', en_ves[0].x, en_ves[0].y, en_orden_ok=True)
        ns = nodos()
        campos = [n for n in ns if n.clase == 'EditText']
    if numero(campos[0].t) != monto:
        escribir(campos[0], fmt_monto(monto), en_orden_ok=True)
        if teclado_visible():
            tecla('BACK')                   # solo si el teclado está: si no, BACK saldría de la orden
        ns = nodos()
        if que_es(ns) != 'orden':
            frenar('Se cerró la orden al escribir el monto', 'orden', ns)
    campos = [n for n in ns if n.clase == 'EditText']
    desde = max(n.y for n in con(ns, 'Vendes'))
    hasta = min([n.y for n in ns if norm(n.t).startswith('info del anunciante')] or [10 ** 5])
    fila = [n for n in ns if desde + 40 < n.y < hasta and n.t]
    paso('fila de método: %s' % (' | '.join(n.t for n in fila) or '(vacía)'))
    monto_ok = bool(campos) and numero(campos[0].t) == monto
    metodo_ok = any(compacto(metodo['nombre']) in compacto(n.t) or compacto(metodo['id']) in compacto(n.t)
                    for n in fila)
    return monto_ok, metodo_ok


def recorrido(link):
    global EN_ORDEN
    EN_ORDEN = False
    ad, monto, pago = leer_link(link)
    det = detalle_anuncio(ad)
    metodo = elegir_metodo(det, pago)
    paso('anuncio %s: %s, precio %s, límites %s-%s, %s' % (ad, det['apodo'], det['precio'], fmt_monto(det['min']),
                                                          fmt_monto(det['max']), metodo['nombre']))
    if not monto:
        raise Frenado('El link no trae el monto: subí el Apps Script nuevo y buscá el anuncio de nuevo')
    if (det['min'] and monto < det['min']) or (det['max'] and monto > det['max']):
        raise Frenado('%s Bs no entra en los límites del anuncio (%s - %s): buscá otro anuncio' %
                      (fmt_monto(monto), fmt_monto(det['min']), fmt_monto(det['max'])))
    if not conectar():
        raise Frenado('No hay ADB. Tocá RECONECTAR en la notificación de ADB y probá de nuevo')
    if bloqueado():
        raise Frenado('El teléfono está bloqueado: desbloquealo y probá de nuevo')
    paquete_binance()
    avisar('Binance: armando la orden…', '%s · %s Bs · %s. No toques la pantalla' %
           (det['apodo'], fmt_monto(monto), metodo['nombre']))
    ns = llegar_a_la_orden(det['apodo'], metodo, monto)
    monto_ok, metodo_ok = completar_orden(ns, det['apodo'], metodo, monto)
    base = guardar('listo')
    faltan = [x for x, ok in (('el monto', monto_ok), ('el método', metodo_ok)) if not ok]
    return '%s · %s Bs · %s · precio %s.%s Revisá, tildá la casilla y tocá Realizar Orden vos. (%s.png)' % (
        det['apodo'], fmt_monto(monto), metodo['nombre'], det['precio'],
        (' ⚠️ No pude confirmar ' + ' ni '.join(faltan) + '.') if faltan else '', base)


# ---------- Herramientas ----------

def grabar(segundos=150):
    """Mientras hacés el camino A MANO, guarda cada pantalla nueva de Binance (xml + captura) en
    Descargas/binance_grabacion_HHMMSS/ (carpeta nueva cada vez: no pisa grabaciones anteriores)."""
    if not conectar():
        raise Frenado('No hay ADB')
    paquete_binance()
    nombre = 'binance_grabacion_' + time.strftime('%H%M%S')
    carpeta = os.path.join(LOG_DIR, nombre)
    os.makedirs(carpeta, exist_ok=True)
    adb('shell', 'mkdir', '-p', '/sdcard/Download/' + nombre)
    ultima, n, fin = None, 0, time.time() + segundos
    print('Grabando %d s en Descargas/%s. Hacé el camino a mano, despacio, sin tocar Realizar Orden.' %
          (segundos, nombre), flush=True)
    while time.time() < fin:
        xml = volcar(10, 1)
        ns = leer_nodos(xml)
        firma = que_veo(ns)
        if ns and firma != ultima:
            ultima, n = firma, n + 1
            with open(os.path.join(carpeta, '%02d.xml' % n), 'w') as f:
                f.write(xml)
            adb('shell', 'screencap', '-p', '/sdcard/Download/%s/%02d.png' % (nombre, n))
            print('  pantalla %d (%s): %s' % (n, que_es(ns), firma[:80]), flush=True)
        time.sleep(1)
    print('Listo: %d pantallas en Descargas/%s' % (n, nombre))


if __name__ == '__main__':
    args = sys.argv[1:]
    try:
        if args[:1] == ['--pantalla']:
            if not conectar():
                raise Frenado('No hay ADB')
            paquete_binance()
            time.sleep(8)
            print('Guardé %s.png y .xml en Descargas' % guardar(args[1] if len(args) > 1 else 'pantalla'))
        elif args[:1] == ['--grabar']:
            grabar()
        elif len(args) == 1 and not args[0].startswith('--'):
            r = recorrido(args[0])
            print(r)
            avisar('Binance: orden armada ✅', r)
            subprocess.run(['termux-vibrate', '-d', '600'], check=False)
        else:
            print(__doc__)
            sys.exit(2)
    except Frenado as e:
        print('FRENADO: %s' % e, flush=True)
        avisar('Binance: me frené ⚠️', str(e))
        sys.exit(1)
