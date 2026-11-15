#!/usr/bin/env python3
"""Arma la orden P2P de la pre-orden en la app de Binance y se frena UN PASO ANTES de colocarla.

  python binance_orden.py "LINK"            # el recorrido completo (lo corre telefono/binance_orden.sh)
  python binance_orden.py --buscar [MONTO] [MÉTODO]          # lista los anuncios como la pre-orden (5000 PagoMovil)
  python binance_orden.py --prueba [MONTO] [MÉTODO] [PUESTO] # elige uno (1 = el primero) y corre el recorrido
  python binance_orden.py --grabar [SEG]    # (60 s) guarda cada pantalla mientras hacés el camino a mano
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
BUSCAR = 'https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search'   # la misma que usa el relay del VPS
LINK = 'https://c2c.binance.com/es-LA/adv?code=%s&monto=%s&pago=%s'      # el mismo formato que 9_P2P.gs
PAQUETES = ('com.binance.dev', 'com.binance.android', 'com.binance.app')
INICIO_ACT = 'com.eaas.launcher.activities.main.MainActivity'
BOTON_P2P = (0.152, 0.305)   # ícono P2P del inicio (captura del 15/11): el inicio es animado y no se deja leer
CERRAR = ('cerrar', 'omitir', 'ahora no', 'mas tarde', 'entendido', 'saltar', 'no gracias', 'ok')
# Segunda barrera: dentro de la orden, aunque el toque esté permitido, nada que diga esto.
PROHIBIDO = re.compile(r'vender|sell|confirm|colocar|realizar|crear|pagar|enviar|continuar|siguiente|aceptar|'
                       r'haz clic|place|todo')
MAX_VUELTAS = 40
# Panel "Filtrar" (embudo): cómo tienen que quedar los interruptores (john, 15/11: los tres apagados, para que la
# lista muestre los mismos anuncios que la API de la pre-orden).
INTERRUPTORES = {'Solo anuncios comerciables': False, 'Solo comerciantes Pro': False,
                 'Solo comerciantes Verificados': False}
# La primera vez que se confirma el filtro la app lo descarta: en esa primera apertura solo se apaga este y se
# confirma (así lo hace john); en la segunda se pone todo.
PRIMERA_VUELTA = 'Solo anuncios comerciables'
# Cuántas veces se puede repetir una acción sin avanzar. El embudo a veces no abre al primer toque.
LIMITE = {'embudo': 6}


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
    alts = [x for x in (q.get('alt') or [''])[0].split(',') if x.isdigit() and x != ad]   # reservas (Apps Script)
    return ad, float((q.get('monto') or ['0'])[0] or 0), (q.get('pago') or [''])[0], alts


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
N = collections.namedtuple('N', 't x y clase rid clic prendido')   # prendido: True/False en interruptores


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
        clic = n.get('clickable') == 'true'
        # con texto, campos, interruptores y botones-ícono (el embudo no tiene texto)
        if t or clase in ('EditText', 'Switch') or (clic and clase == 'ImageView'):
            lista.append(N(t, (b[0] + b[2]) // 2, (b[1] + b[3]) // 2, clase,
                           (n.get('resource-id') or '').split('/')[-1], clic,
                           n.get('checked') == 'true' if n.get('checkable') == 'true' else None))
    return lista


def nodos(espera=20, intentos=3):
    return leer_nodos(volcar(espera, intentos))


def con(ns, *textos):
    """Nodos cuyo texto es igual (sin acentos ni mayúsculas) a alguno de los textos."""
    c = [compacto(t) for t in textos]
    return [n for n in ns if compacto(n.t) in c]


def que_veo(ns):
    return ' | '.join(n.t for n in ns if n.t)[:300]


def firma(ns):
    """Lo que distingue una pantalla de otra: textos + estado de los interruptores (prender uno no cambia textos)."""
    return que_veo(ns) + ' ' + ''.join('1' if n.prendido else '0' for n in ns if n.clase == 'Switch')


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
    'filtrar': 'panel "Filtrar" del embudo: interruptores (Solo comerciantes Pro…), Monto, Confirmar (grabación 02/03)',
    'monto':   'hoja "Quiero vender" (la abre el chip Monto, 15/11 02:13)',
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
    if con(ns, 'Confirmar') and con(ns, 'Restablecer'):
        if con(ns, 'Filtrar'):              # el panel, aunque esté bajado hasta los métodos (sin el campo del monto)
            return 'filtrar'
        if any(n.clase == 'EditText' for n in ns):
            return 'monto'
    if con(ns, 'Seleccionar divisa'):
        return 'divisa'
    if con(ns, 'Seleccionar activo'):
        return 'activo'
    # la barra de abajo (Anuncios) no siempre sale en el xml (grabación 15/11 15:27, pantalla 08): se usan las de arriba
    if con(ns, 'Comprar') and con(ns, 'Vender') and con(ns, 'Rápido', 'Comercio por bloques', 'Anuncios'):
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
        time.sleep(1.5)                    # el menú sube animado: antes de eso el xml todavía muestra la lista
        return 'moneda'
    # Monto y método se ponen en el embudo; los chips de la lista (Monto, Pago) son la prueba de que agarró.
    if numero(chip_monto.t) != monto or not es_metodo(chip_pago.t, metodo) or not estado.get('filtro completo'):
        # Siempre por el embudo: 1ª apertura "de cebo" (la app descarta ese Confirmar), 2ª con todo. Si después los
        # chips no muestran monto y método, se vuelve a abrir. Si no abre al tocarlo, se toca de nuevo.
        embudo = [n for n in ns if n.clase == 'ImageView' and n.clic and not n.t and abs(n.y - activo.y) < 45
                  and n.x > 900]
        if not embudo:
            frenar('No encontré el embudo (filtro general) a la derecha de los filtros', 'filtros', ns)
        estado['filtro completo'] = False
        estado['pago antes'] = chip_pago.t          # el panel no muestra cuál método está elegido: se recuerda acá
        tocar('el embudo (filtro general)', embudo[0].x, embudo[0].y)
        return 'embudo'
    paso('filtros: Vender · USDT · VES · %s · %s' % (chip_monto.t, chip_pago.t))
    return 'listo'


def interruptor(ns, texto):
    fila = con(ns, texto)
    llave = [n for n in ns if n.clase == 'Switch' and fila and abs(n.y - fila[0].y) < 40]
    return llave[0] if llave else None


def poner_interruptor(ns, texto, quiero):
    """Deja el interruptor como se quiere, comprobando el toque. Devuelve la pantalla leída de nuevo."""
    llave = interruptor(ns, texto)
    if llave is None:
        frenar('En el panel Filtrar no veo el interruptor "%s"' % texto, 'filtrar', ns)
    if llave.prendido == quiero:
        return ns
    tocar('%s "%s"' % ('prender' if quiero else 'apagar', texto), llave.x, llave.y)
    ns = nodos()
    llave = interruptor(ns, texto)
    if llave is None or llave.prendido != quiero:
        frenar('Toqué "%s" y no cambió' % texto, 'filtrar', ns)
    return ns


def en_filtrar(ns, monto, metodo, estado):
    """Panel "Filtrar" (embudo). 1ª apertura: solo apaga PRIMERA_VUELTA y confirma (la app descarta ese Confirmar).
    Después: deja INTERRUPTORES como deben, escribe el monto y confirma."""
    if not estado.get('cebado'):
        ns = poner_interruptor(ns, PRIMERA_VUELTA, INTERRUPTORES[PRIMERA_VUELTA])
        ok = con(ns, 'Confirmar')[0]
        tocar('Confirmar (primera vuelta: la app la descarta)', ok.x, ok.y)
        estado['cebado'] = True
        return 'filtro (primera vuelta)'
    for texto, quiero in INTERRUPTORES.items():
        ns = poner_interruptor(ns, texto, quiero)
    ns = poner_monto(ns, monto, 'filtrar')
    ns = poner_metodo(ns, metodo, estado)
    ok = con(ns, 'Confirmar')
    if not ok:
        frenar('No encontré Confirmar en el panel Filtrar', 'filtrar', ns)
    tocar('Confirmar (filtro completo)', ok[0].x, ok[0].y)
    estado['filtro completo'] = True
    return 'filtro (completo)'


def seleccionados(ns):
    """El texto "(1 seleccionado/s)" junto a "Método de Pago": la única marca en el xml de que hay uno elegido
    (grabación 16:34; los botones no traen selected/checked). None si no hay ninguno elegido."""
    for n in ns:
        m = re.search(r'\((\d+) seleccionado', n.t)
        if m:
            return int(m.group(1))
    return None


def botones_metodo(ns):
    """Los botones de la sección "Método de Pago" (entre su título y "País/región")."""
    tit = con(ns, 'Método de Pago')
    if not tit:
        return []
    hasta = min([n.y for n in con(ns, 'País/región')] + [n.y - 30 for n in con(ns, 'Restablecer')] + [10 ** 5])
    return [n for n in ns if tit[0].y + 40 < n.y < hasta - 20 and n.clic and n.t]


def poner_metodo(ns, metodo, estado):
    """Baja hasta "Método de Pago" (abajo de todo en el panel) y deja elegido SOLO el método de la pre-orden."""
    ancho, alto = tamano_pantalla()
    for _ in range(4):
        if any(es_metodo(n.t, metodo) for n in botones_metodo(ns)):
            break
        adb('shell', 'input', 'swipe', str(ancho // 2), str(int(alto * .70)), str(ancho // 2), str(int(alto * .35)),
            '400')
        time.sleep(1.2)
        ns = nodos()
    else:
        frenar('No encontré "%s" en la sección Método de Pago del filtro' % metodo['nombre'], 'filtrar', ns)
    elegidos = seleccionados(ns)
    if elegidos:
        if elegidos == 1 and es_metodo(estado.get('pago antes', ''), metodo):
            paso('método: %s ya está elegido' % metodo['nombre'])
            return ns
        frenar('En el filtro hay %d método(s) elegido(s) y la lista decía "%s": dejalo en Todo a mano' %
               (elegidos, estado.get('pago antes', '')), 'filtrar', ns)
    boton = [n for n in botones_metodo(ns) if es_metodo(n.t, metodo)][0]
    tocar('el método %s' % boton.t, boton.x, boton.y)
    ns = nodos()
    if seleccionados(ns) != 1:
        frenar('Toqué %s y no quedó elegido' % boton.t, 'filtrar', ns)
    return ns


def en_monto(ns, monto):
    """Hoja "Quiero vender": escribe el monto y toca Confirmar."""
    ns = poner_monto(ns, monto, 'monto')
    ok = con(ns, 'Confirmar')[0]
    tocar('Confirmar (monto %s)' % fmt_monto(monto), ok.x, ok.y)


def poner_monto(ns, monto, tipo):
    """Escribe el monto en el campo del panel y baja el teclado. Devuelve la pantalla leída de nuevo."""
    campo = [n for n in ns if n.clase == 'EditText'][0]
    if numero(campo.t) != monto:
        escribir(campo, fmt_monto(monto))
        ns = nodos()
        if teclado_visible():              # se baja (tapa Confirmar y no deja bajar hasta los métodos)
            tecla('BACK')
            ns = nodos()
        if que_es(ns) != tipo:
            frenar('Se cerró el panel del monto antes de confirmar', 'panel_monto', ns)
        campo = [n for n in ns if n.clase == 'EditText']
        if campo and numero(campo[0].t) != monto:
            frenar('Escribí %s pero el campo dice "%s"' % (fmt_monto(monto), campo[0].t), 'panel_monto', ns)
    return ns


PRECIO = re.compile(r'^\d{1,3}(,\d{3})*\.\d{2,3}$')   # "1,058.000": el precio grande de cada tarjeta
PANTALLAS_LISTA = 15
TOLERANCIA_PRECIO = 0.003   # el precio del anuncio puede moverse un poco entre la API y la app


ELEGIDO = None   # el candidato cuyo Vender se tocó (el anuncio de la pre-orden o una reserva)
AVISO_RESERVA = 0.01   # si la reserva tiene un precio más de 1 % peor que el elegido, se avisa con ⚠️


def buscar_en_lista(candidatos):
    """candidatos: [{'apodo', 'precio', ...}] en orden de preferencia (el anuncio de la pre-orden primero, después las
    reservas). Baja DESPACIO (sin inercia: el 15/11 16:42 un gesto rápido se salteó tarjetas), anota a quién vio en
    cada pantalla y toca el Vender del mejor candidato que aparezca. Si aparece una reserva pero un preferido podría
    estar más abajo (precio menor), sigue bajando. La lista va de mayor a menor precio: cuando ya pasó el precio de
    todos los candidatos sin verlos, se frena."""
    global EN_ORDEN, ELEGIDO
    ancho, alto = tamano_pantalla()
    piso = min([c['precio'] for c in candidatos if c.get('precio')] or [0])
    vista = None                       # una reserva vista mientras se esperaba a un preferido
    for i in range(PANTALLAS_LISTA):
        ns = nodos()
        visibles = []
        for k, c in enumerate(candidatos):
            for fila in (n for n in ns if compacto(n.t) == compacto(c['apodo'])):
                debajo = sorted((n for n in con(ns, 'Vender') if fila.y < n.y < alto * 0.9), key=lambda n: n.y)
                if debajo:
                    visibles.append((k, c, debajo[0]))
                    break
        if visibles:
            k, c, boton = min(visibles, key=lambda v: v[0])
            pendientes = [p['apodo'] for p in candidatos[:k]
                          if p.get('precio') and c.get('precio') and p['precio'] < c['precio'] * (1 - TOLERANCIA_PRECIO)]
            if not pendientes:
                tocar('Vender de %s%s' % (c['apodo'], ' (reserva)' if k else ''), boton.x, boton.y)
                EN_ORDEN, ELEGIDO = True, c
                return c
            vista = vista or c['apodo']
            paso('veo a %s (reserva), pero %s puede estar más abajo: sigo' % (c['apodo'], ', '.join(pendientes)))
        precios = [numero(n.t) for n in ns if PRECIO.match(n.t)]
        vendedores = [n for n in con(ns, 'Vender') if n.x > 700]   # los de las tarjetas (la pestaña está a la izquierda)
        quienes = [n.t for n in ns if not n.rid and len(n.t) > 1 and n.clase == 'TextView' and n.t not in
                   ('Vender', 'Comprar') and any(0 < v.y - n.y < 520 for v in vendedores)]
        paso('lista %d: %s · precios %s' % (i + 1, ', '.join(quienes) or '(nadie)',
                                            '%s a %s' % (fmt_monto(max(precios)), fmt_monto(min(precios)))
                                            if precios else '-'))
        if piso and precios and max(precios) < piso * (1 - TOLERANCIA_PRECIO):
            nombres = ', '.join(c['apodo'] for c in candidatos)
            frenar('Pasé el precio de %s sin verlos: la lista ya va por %s. Los tomó otro o cambiaron%s' %
                   (nombres, fmt_monto(max(precios)), ' (vi a %s más arriba: corré de nuevo)' % vista if vista else ''),
                   'lista', ns)
        # despacio (1,5 s) y la mitad de la pantalla: sin inercia, cada pantalla se superpone con la anterior
        adb('shell', 'input', 'swipe', str(ancho // 2), str(int(alto * .80)), str(ancho // 2),
            str(int(alto * .30)), '1500')
        time.sleep(1.5)
    frenar('No encontré a %s en %d pantallas de la lista' %
           (', '.join(c['apodo'] for c in candidatos), PANTALLAS_LISTA), 'lista')


def llegar_a_la_orden(candidatos, metodo, monto):
    """El bucle: lee, reconoce la pantalla, hace UNA acción. Termina en la pantalla "Vender USDT" del anunciante
    (el de la pre-orden o una reserva: ELEGIDO). candidatos: ver buscar_en_lista."""
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
                frenar('Toqué Vender de %s pero no se abrió la orden' % ELEGIDO['apodo'], 'orden', ns)
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
                buscar_en_lista(candidatos)
                hecho = 'buscar a %s' % ELEGIDO['apodo']
        elif p == 'filtrar':
            hecho = en_filtrar(ns, monto, metodo, estado)
        elif p == 'monto':               # la hoja del chip Monto: no debería abrirse (se va por el embudo)
            en_monto(ns, monto)
            estado['filtro completo'] = False
            hecho = 'monto (hoja Quiero vender)'
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
        if veces[hecho] > LIMITE.get(hecho, 3):
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


def armar_candidatos(ad, alts, monto, pago):
    """El anuncio de la pre-orden y sus reservas, cada uno revisado contra Binance (desde el teléfono): solo quedan
    los que siguen existiendo, aceptan el monto y el método. Devuelve (candidatos, método, principal): principal es
    el anuncio de la pre-orden tal como lo eligió el Apps Script (apodo y precio; precio None si ya no existe)."""
    candidatos, metodo, problemas = [], None, []
    principal = {'apodo': 'el anuncio %s' % ad, 'precio': None}
    for i, adno in enumerate([ad] + alts):
        quien = 'anuncio' if i == 0 else 'reserva %d' % i
        try:
            d = detalle_anuncio(adno)
        except Frenado as e:
            problemas.append('%s: %s' % (quien, e))
            continue
        except (OSError, ValueError) as e:   # sin respuesta de Binance: no se sabe si sirve

            problemas.append('%s: Binance no respondió (%s)' % (quien, e))
            continue
        if i == 0:
            principal = {'apodo': d['apodo'], 'precio': d['precio']}
        try:
            m = elegir_metodo(d, pago)
        except Frenado as e:
            problemas.append('%s (%s): %s' % (quien, d['apodo'], e))
            continue
        if (d['min'] and monto < d['min']) or (d['max'] and monto > d['max']):
            problemas.append('%s (%s): %s Bs no entra en %s - %s' % (quien, d['apodo'], fmt_monto(monto),
                                                                     fmt_monto(d['min']), fmt_monto(d['max'])))
            continue
        metodo = metodo or m
        candidatos.append({'adNo': adno, 'apodo': d['apodo'], 'precio': d['precio'], 'reserva': i > 0})
        paso('%s %s: %s, precio %s, límites %s-%s, %s' % (quien, adno, d['apodo'], d['precio'], fmt_monto(d['min']),
                                                         fmt_monto(d['max']), m['nombre']))
    for p in problemas:
        paso('no sirve: %s' % p)
    if not candidatos:
        raise Frenado('Ni el anuncio ni las reservas sirven: ' + ' · '.join(problemas))
    return candidatos, metodo, principal


def resumen(principal, elegido, monto, metodo, faltan, base):
    """El mensaje final y si hay que avisar (⚠️): se usó una reserva con un precio más de AVISO_RESERVA peor que el
    anuncio de la pre-orden, o no se pudo saber su precio."""
    texto = '%s · %s Bs · %s · precio %s.' % (elegido['apodo'], fmt_monto(monto), metodo['nombre'], elegido['precio'])
    alerta = False
    if elegido['reserva']:
        if principal['precio']:
            dif = (principal['precio'] - elegido['precio']) / principal['precio']
            alerta = dif > AVISO_RESERVA
            nota = ' ⚠️ Precio %.1f%% peor que %s (%s).' % (dif * 100, principal['apodo'], principal['precio']) \
                if alerta else ''
        else:
            alerta, nota = True, ' ⚠️ No pude saber el precio del anuncio original para comparar.'
        texto = '🔁 RESERVA (no estaba %s): %s%s' % (principal['apodo'], texto, nota)
    if faltan:
        alerta = True
        texto += ' ⚠️ No pude confirmar ' + ' ni '.join(faltan) + '.'
    return texto + ' Revisá, tildá la casilla y tocá Realizar Orden vos. (%s.png)' % base, alerta


def recorrido(link):
    global EN_ORDEN, ELEGIDO
    EN_ORDEN, ELEGIDO = False, None
    ad, monto, pago, alts = leer_link(link)
    if not monto:
        raise Frenado('El link no trae el monto: subí el Apps Script nuevo y buscá el anuncio de nuevo')
    candidatos, metodo, principal = armar_candidatos(ad, alts, monto, pago)
    if not conectar():
        raise Frenado('No hay ADB. Tocá RECONECTAR en la notificación de ADB y probá de nuevo')
    if bloqueado():
        raise Frenado('El teléfono está bloqueado: desbloquealo y probá de nuevo')
    paquete_binance()
    avisar('Binance: armando la orden…', '%s · %s Bs · %s. No toques la pantalla' %
           (' / '.join(c['apodo'] for c in candidatos), fmt_monto(monto), metodo['nombre']))
    ns = llegar_a_la_orden(candidatos, metodo, monto)
    monto_ok, metodo_ok = completar_orden(ns, ELEGIDO['apodo'], metodo, monto)
    base = guardar('listo')
    faltan = [x for x, ok in (('el monto', monto_ok), ('el método', metodo_ok)) if not ok]
    texto, alerta = resumen(principal, ELEGIDO, monto, metodo, faltan, base)
    avisar('Binance: orden armada %s' % ('⚠️ REVISÁ' if alerta else '✅'), texto)
    subprocess.run(['termux-vibrate', '-d', '1500' if alerta else '600'], check=False)
    return texto


# ---------- Herramientas ----------

def buscar_anuncios(monto, pago, filas=20):
    """Los anuncios donde vendés USDT por VES con ese método y monto, en el orden de Binance (como la pre-orden)."""
    cuerpo = {'asset': 'USDT', 'fiat': 'VES', 'tradeType': 'SELL', 'page': 1, 'rows': filas,
              'payTypes': [pago] if pago else [], 'transAmount': fmt_monto(monto)}
    req = urllib.request.Request(BUSCAR, data=json.dumps(cuerpo).encode(),
                                 headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=15) as r:
        datos = json.load(r).get('data') or []
    ads = [{'adNo': a['adv']['advNo'], 'apodo': a['advertiser']['nickName'], 'precio': float(a['adv']['price']),
            'min': float(a['adv']['minSingleTransAmount']),
            'max': float(a['adv'].get('dynamicMaxSingleTransAmount') or a['adv'].get('maxSingleTransAmount') or 0),
            'pagos': [m.get('identifier') for m in a['adv'].get('tradeMethods', [])]} for a in datos]
    # Solo los que aceptan ese monto y ese método (lo mismo que valida el recorrido antes de abrir la app)
    return [a for a in ads if a['min'] <= monto <= a['max'] and (not pago or pago in a['pagos'])]


def prueba(monto, pago, puesto, arrancar=True):
    """Elige un anuncio de prueba como la pre-orden (Binance, vender USDT por VES, ese método y monto), muestra
    los primeros y, si arrancar, corre el recorrido con el del puesto pedido (1 = el primero de la lista)."""
    ads = buscar_anuncios(monto, pago)
    if not ads:
        raise Frenado('Binance no devolvió anuncios para %s Bs con %s' % (fmt_monto(monto), pago))
    print('Anuncios de Binance: vender USDT · VES · %s · %s Bs' % (pago, fmt_monto(monto)))
    for i, a in enumerate(ads[:10], 1):
        print('%s%2d. %-22s %10s  %s-%s  %s' % ('>' if i == puesto else ' ', i, a['apodo'][:22], a['precio'],
                                                fmt_monto(a['min']), fmt_monto(a['max']), ','.join(a['pagos'])))
    if puesto > len(ads):
        raise Frenado('Hay solo %d anuncios' % len(ads))
    a = ads[puesto - 1]
    # reservas: los 2 siguientes de OTRO trader (sin filtro de frases: esto es solo para probar la app; las de verdad
    # las elige el Apps Script con sus filtros)
    alts = []
    for x in ads[puesto:]:
        if len(alts) < 2 and x['apodo'] != a['apodo'] and x['apodo'] not in [y['apodo'] for y in alts]:
            alts.append(x)
    link = LINK % (a['adNo'], fmt_monto(monto), urllib.parse.quote(pago))
    if alts:
        link += '&alt=' + ','.join(x['adNo'] for x in alts)
    print('\nPRUEBA: usuario %s · %s Bs · %s · precio %s · puesto %d' %
          (a['apodo'], fmt_monto(monto), pago, a['precio'], puesto))
    print('RESERVAS: %s\n%s' % (' · '.join('%s %s' % (x['apodo'], x['precio']) for x in alts) or 'ninguna', link),
          flush=True)
    if not arrancar:
        return link
    for i in range(5, 0, -1):
        print('  arranco en %d… (Ctrl+C para cancelar)' % i, flush=True)
        time.sleep(1)
    return recorrido(link)


def vibrar(ms):
    """Vibración corta sin esperar a que termine (-f: aunque el teléfono esté en silencio)."""
    subprocess.Popen(['termux-vibrate', '-f', '-d', str(ms)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def grabar(segundos=60):
    """Mientras hacés el camino A MANO, guarda cada pantalla nueva de Binance (xml + captura) en
    Descargas/binance_grabacion_HHMMSS/ (carpeta nueva cada vez: no pisa grabaciones anteriores).
    Vibra largo al empezar, cortito con cada pantalla guardada y dos veces al terminar.
    Esperá la vibración cortita (2-3 s) antes del toque siguiente."""
    if not conectar():
        raise Frenado('No hay ADB')
    paquete_binance()
    nombre = 'binance_grabacion_' + time.strftime('%H%M%S')
    carpeta = os.path.join(LOG_DIR, nombre)
    os.makedirs(carpeta, exist_ok=True)
    adb('shell', 'mkdir', '-p', '/sdcard/Download/' + nombre)
    print('Grabando %d s en Descargas/%s. Andá a Binance; después de cada toque esperá la vibración cortita.' %
          (segundos, nombre), flush=True)
    for i in range(5, 0, -1):         # tiempo para pasar a Binance
        print('  empiezo en %d…' % i, flush=True)
        time.sleep(1)
    vibrar(400)
    ultima, n, fin = None, 0, time.time() + segundos
    while time.time() < fin:
        xml = volcar(10, 1)
        ns = leer_nodos(xml)
        f = firma(ns)
        if ns and f != ultima:
            ultima, n = f, n + 1
            with open(os.path.join(carpeta, '%02d.xml' % n), 'w') as fx:
                fx.write(xml)
            adb('shell', 'screencap', '-p', '/sdcard/Download/%s/%02d.png' % (nombre, n))
            vibrar(60)
            resto = int(fin - time.time())
            avisar('Grabando Binance: %d pantallas' % n, 'Quedan %d s. Última: %s' % (max(resto, 0), que_es(ns)))
            print('  pantalla %d (%s): %s' % (n, que_es(ns), que_veo(ns)[:80]), flush=True)
        time.sleep(0.5)
    vibrar(300)
    time.sleep(0.6)
    vibrar(300)
    avisar('Grabación terminada', '%d pantallas en Descargas/%s' % (n, nombre))
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
        elif args[:1] in (['--prueba'], ['--buscar']):
            # --prueba [MONTO] [MÉTODO] [PUESTO]   (5000 PagoMovil 1)
            monto = float(args[1]) if len(args) > 1 else 5000.0
            pago = args[2] if len(args) > 2 else 'PagoMovil'
            puesto = int(args[3]) if len(args) > 3 else 1
            r = prueba(monto, pago, puesto, arrancar=args[0] == '--prueba')
            if args[0] == '--prueba':
                print(r)
        elif args[:1] == ['--grabar']:
            grabar(int(args[1]) if len(args) > 1 and args[1].isdigit() else 60)
        elif len(args) == 1 and not args[0].startswith('--'):
            r = recorrido(args[0])
            print(r)
        else:
            print(__doc__)
            sys.exit(2)
    except Frenado as e:
        print('FRENADO: %s' % e, flush=True)
        avisar('Binance: me frené ⚠️', str(e))
        sys.exit(1)
