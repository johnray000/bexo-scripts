#!/usr/bin/env python3
"""Arma la orden P2P de la pre-orden en la app de Binance y se frena UN PASO ANTES de colocarla.

Recibe el link del anuncio que eligió la pre-orden (Apps Script, 9_P2P.gs):
  https://c2c.binance.com/es-LA/adv?code=<adNo>&monto=<Bs>&pago=<método>
y maneja el teléfono por ADB (como okx_ordenes.py):
  1. Pide a Binance el detalle de ESE anuncio (desde el teléfono Binance sí responde): apodo, precio, límites y
     métodos. Si el monto no entra en los límites o el método no está en el anuncio, no abre nada.
  2. Abre Binance → P2P → Vender → USDT → VES, pone el monto y el MÉTODO en los filtros (los mismos con los que
     buscó la pre-orden, así la app muestra la misma lista que leyó la API) y busca el apodo en la lista.
     Límites y "terceros" ya los validó la pre-orden sobre ese anuncio: acá solo se confirma que es el mismo trader.
  3. Toca su "Vender" y en la pantalla "Vender USDT" escribe los Bs y elige tu método de pago.
     NO toca la casilla de términos ni "Realizar Orden": la orden la colocás vos.

Los links directos no sirven: el 15/11/2026 se probaron 25 (anuncio, perfil, P2P) y la app no abre ninguno.
Las pantallas son las de la grabación de ese día (--grabar).

  python binance_orden.py "LINK"            # el recorrido completo (lo corre telefono/binance_orden.sh)
  python binance_orden.py --grabar          # 150 s guardando cada pantalla mientras hacés el recorrido a mano
  python binance_orden.py --pantalla NOMBRE # en 8 s guarda la pantalla en Descargas

Lo que guarda (capturas y pantallas) queda en Descargas, con nombres binance_*.
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

BOTON_P2P = (0.152, 0.305)   # ícono P2P del inicio (captura del 15/11): el inicio es animado y no se deja leer
CERRAR = ('Cerrar', 'Omitir', 'Ahora no', 'Más tarde', 'Entendido', 'Saltar', 'No, gracias')
# Ya dentro de la orden, NUNCA se toca algo que diga esto: es lo que coloca la orden (eso lo hacés vos).
PROHIBIDO = re.compile(r'vender|sell|confirm|colocar|realizar|crear|pagar|enviar|continuar|siguiente|aceptar|'
                       r'haz clic|place|todo')


class Frenado(Exception):
    """El recorrido se frenó: motivo para la notificación."""


def norm(s):
    s = unicodedata.normalize('NFD', str(s or '')).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9 ]', '', s).strip()


def compacto(s):
    """Para comparar textos: sin acentos, espacios ni signos. Si no queda nada (apodo en chino), el texto tal cual."""
    return norm(s).replace(' ', '') or str(s or '').strip()


def avisar(titulo, texto):
    subprocess.run(['termux-notification', '--id', 'binance-orden', '--title', titulo, '--content', texto],
                   check=False)


def paso(texto):
    print(time.strftime('%H:%M:%S ') + texto, flush=True)


def fmt_monto(m):
    return ('%.2f' % m).rstrip('0').rstrip('.')


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
            if compacto(m['id']) == compacto(pago):
                return m
        raise Frenado('El anuncio ya no acepta %s (acepta %s)' % (pago, ', '.join(ids) or 'nada'))
    if len(det['metodos']) == 1:
        return det['metodos'][0]
    raise Frenado('El link no dice el método y el anuncio tiene varios (%s): subí el Apps Script nuevo' % ', '.join(ids))


# ---------- Pantalla ----------

PAQ = ''   # paquete de Binance: solo se miran sus textos (si no, lo que imprime Termux cuenta como "visto")
N = collections.namedtuple('N', 't x y clase clic rid y1 y2')


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
    for n in ET.fromstring(xml).iter('node'):
        if PAQ and n.get('package') != PAQ:
            continue
        b = [int(v) for v in re.findall(r'\d+', n.get('bounds') or '')]
        if len(b) != 4:
            continue
        t = (n.get('text') or n.get('content-desc') or '').strip()
        clase = (n.get('class') or '').split('.')[-1]
        rid = (n.get('resource-id') or '').split('/')[-1]
        if t or clase == 'EditText' or rid:
            lista.append(N(t, (b[0] + b[2]) // 2, (b[1] + b[3]) // 2, clase, n.get('clickable') == 'true', rid,
                           b[1], b[3]))
    return lista


def nodos(espera=20, intentos=3):
    return leer_nodos(volcar(espera, intentos))


def hay(texto, ns=None):
    """¿Algún texto de la pantalla es igual a `texto` (sin acentos ni mayúsculas)?"""
    return any(compacto(n.t) == compacto(texto) for n in (ns if ns is not None else nodos()))


def que_veo(ns=None):
    return ' | '.join(n.t for n in (ns if ns is not None else nodos()) if n.t)[:400]


def guardar(nombre):
    base = 'binance_%s_%s' % (nombre, time.strftime('%H%M%S'))
    adb('shell', 'screencap', '-p', '/sdcard/Download/%s.png' % base)
    with open(os.path.join(LOG_DIR, base + '.xml'), 'w') as f:
        f.write(volcar(15, 1))
    return base


def frenar(motivo, nombre='fallo'):
    paso('veo: %s' % que_veo())
    raise Frenado('%s. Guardé la pantalla en Descargas (%s.png)' % (motivo, guardar(nombre)))


class Toques:
    """Todos los toques pasan por acá. Desde que se abre la orden (en_orden), no se toca nada PROHIBIDO."""
    en_orden = False

    def nodo(self, n, nombre=None):
        self.xy(nombre or n.t, n.x, n.y)

    def xy(self, texto, x, y):
        if self.en_orden and PROHIBIDO.search(norm(texto)):
            raise Frenado('Por seguridad no toqué "%s"' % texto)
        paso('toco "%s"' % texto)
        adb('shell', 'input', 'tap', str(x), str(y))
        time.sleep(2)

    def texto(self, opciones, intentos=3, parcial=False):
        """Toca el primer texto igual a alguna opción (o que la contenga, con parcial). False si no aparece."""
        for _ in range(intentos):
            for n in nodos():
                if any(compacto(n.t) == compacto(o) or (parcial and compacto(o) in compacto(n.t))
                       for o in opciones if o):
                    self.nodo(n)
                    return True
            time.sleep(1.5)
        return False


T = Toques()


def cerrar_carteles(ns):
    for n in ns:
        if n.t in CERRAR:
            T.nodo(n)
            return True
    return False


def teclado_visible():
    return 'mInputShown=true' in adb('shell', 'dumpsys', 'input_method')


def borrar_y_escribir(n, valor):
    """Toca un campo, borra lo que tenga y escribe el valor."""
    T.nodo(n, 'campo "%s"' % (n.t or 'vacío'))
    adb('shell', 'input', 'keyevent', 'KEYCODE_MOVE_END')
    for _ in range(14):
        adb('shell', 'input', 'keyevent', 'KEYCODE_DEL')
    adb('shell', 'input', 'text', valor)
    time.sleep(1.5)


# ---------- 2. Llegar al anuncio ----------

def paquete_binance():
    global PAQ
    for linea in adb('shell', 'pm', 'list', 'packages').splitlines():
        p = linea.replace('package:', '').strip()
        if p in ('com.binance.dev', 'com.binance.android', 'com.binance.app'):
            PAQ = p
            return p
    raise Frenado('No encuentro la app de Binance instalada')


def al_frente():
    for l in adb('shell', 'dumpsys', 'window').splitlines():
        if 'mCurrentFocus' in l:
            return l.strip()
    return ''


def en_p2p(ns):
    """Portada de P2P (grabación 04): pestañas Comprar / Vender arriba y la barra de abajo P2P · Órdenes · Anuncios."""
    return hay('Comprar', ns) and hay('Vender', ns) and hay('Anuncios', ns)


def abrir_p2p(paquete):
    """Abre Binance (donde haya quedado) y llega a la portada de P2P."""
    adb('shell', 'cmd', 'statusbar', 'collapse')   # si quedó abierta la cortina de notificaciones, tapa la app
    adb('shell', 'am', 'start', '-W', '-a', 'android.intent.action.MAIN', '-c', 'android.intent.category.LAUNCHER',
        paquete)
    for _ in range(10):
        time.sleep(2)
        if PAQ in al_frente():
            break
        if 'NotificationShade' in al_frente():
            adb('shell', 'cmd', 'statusbar', 'collapse')
    else:
        frenar('Binance no se abrió (al frente: %s)' % al_frente(), 'inicio')
    time.sleep(3)
    ancho, alto = tamano_pantalla()
    for intento in range(4):
        ns = nodos(espera=8, intentos=1)   # el inicio es animado: si no se deja leer en 8 s, es el inicio
        if en_p2p(ns):
            return
        if cerrar_carteles(ns):
            continue
        if not ns or hay('Depositar', ns) or hay('Exchange', ns) or hay('P2P', ns):
            p2p = [n for n in ns if n.t == 'P2P']
            if p2p:
                T.nodo(p2p[0])
            else:
                paso('no leí el inicio: toco P2P por posición')
                adb('shell', 'input', 'tap', str(int(ancho * BOTON_P2P[0])), str(int(alto * BOTON_P2P[1])))
            time.sleep(4)
        else:                              # quedó en otra pantalla de Binance: atrás hasta el inicio
            paso('estoy en otra pantalla (%s): atrás' % que_veo(ns)[:80])
            adb('shell', 'input', 'keyevent', 'KEYCODE_BACK')
            time.sleep(2)
    if not en_p2p(nodos()):
        frenar('No llegué a la portada de P2P', 'inicio')


def preparar_lista(metodo, monto):
    """En P2P: Vender, USDT, VES, monto y método en los filtros (pantallas 01 a 04 de la grabación)."""
    ns = nodos()
    vender = sorted((n for n in ns if norm(n.t) == 'vender'), key=lambda n: n.y)
    T.nodo(vender[0])                      # la pestaña: el "Vender" de más arriba (los otros son de cada anuncio)
    ns = nodos()
    usdt = [n for n in ns if n.t == 'USDT' and n.y < 600]
    if usdt:
        T.nodo(usdt[0])
        ns = nodos()
    # Moneda: arriba a la derecha. Si no es VES, se abre "Seleccionar divisa" y se toca VES.
    fiat = [n for n in ns if n.y < 360 and n.x > 800 and re.fullmatch(r'[A-Z]{3}', n.t)]
    if not fiat:
        frenar('No encontré la moneda (VES) arriba a la derecha', 'moneda')
    if fiat[0].t != 'VES':
        T.nodo(fiat[0])
        if not T.texto(('VES',)):
            frenar('No pude elegir VES', 'moneda')
        ns = nodos()
    # Monto: el filtro (tv_amount) abre el panel "Filtrar": campo "Ingresa el monto total" y Confirmar.
    chip = [n for n in ns if n.rid == 'tv_amount']
    if not chip:
        frenar('No encontré el filtro de monto', 'filtro_monto')
    T.nodo(chip[0], 'filtro de monto')
    ns = nodos()
    campo = [n for n in ns if n.clase == 'EditText']
    if not campo or not hay('Filtrar', ns):
        frenar('No se abrió el panel Filtrar', 'panel_filtrar')
    borrar_y_escribir(campo[0], fmt_monto(monto))
    if teclado_visible():
        adb('shell', 'input', 'keyevent', 'KEYCODE_BACK')
        time.sleep(1.5)
    if not T.texto(('Confirmar',)):
        frenar('No encontré Confirmar en el panel Filtrar', 'panel_filtrar')
    # Método: el filtro a la derecha del monto (dice "Pago" o el método elegido antes).
    ns = nodos()
    chip = [n for n in ns if n.rid == 'tv_amount']
    if not chip:
        frenar('Después del monto no volví a la lista', 'lista')
    pago = sorted((n for n in ns if n.t and abs(n.y - chip[0].y) < 30 and chip[0].x < n.x < 900 and n.t != chip[0].t),
                  key=lambda n: n.x)
    if not pago:
        frenar('No encontré el filtro de método (Pago)', 'filtro_pago')
    if compacto(metodo['nombre']) != compacto(pago[0].t) and compacto(metodo['id']) != compacto(pago[0].t):
        T.nodo(pago[0], 'filtro de método (%s)' % pago[0].t)
        time.sleep(1)
        if not T.texto((metodo['nombre'], metodo['id']), parcial=True):
            frenar('No encontré "%s" en la lista de métodos' % metodo['nombre'], 'lista_metodos')
        ns = nodos()
        if not any(n.rid == 'tv_amount' for n in ns):   # si la lista de métodos pide confirmar
            for n in ns:
                if norm(n.t) in ('confirmar', 'aplicar', 'listo'):
                    T.nodo(n)
                    break
    ns = nodos()
    filtros = [n.t for n in ns if n.y < 460 and (n.rid == 'tv_amount' or compacto(n.t) in (
        compacto(metodo['nombre']), compacto(metodo['id'])))]
    paso('filtros: %s' % ' | '.join(filtros))


def buscar_en_lista(apodo):
    """Busca el apodo en la lista (bajando hasta 10 pantallas) y toca el Vender de su tarjeta."""
    ancho, alto = tamano_pantalla()
    for _ in range(10):
        ns = nodos()
        fila = [n for n in ns if compacto(n.t) == compacto(apodo)]
        if fila:
            debajo = sorted((n for n in ns if norm(n.t) == 'vender' and n.y > fila[0].y and n.y < 2160),
                            key=lambda n: n.y)
            if debajo:
                T.nodo(debajo[0], 'Vender de %s' % apodo)
                T.en_orden = True
                return
        adb('shell', 'input', 'swipe', str(ancho // 2), str(int(alto * .75)), str(ancho // 2),
            str(int(alto * .35)), '500')
        time.sleep(1.5)
    frenar('No encontré a %s en la lista (¿lo tomó otro, cambió el precio o se quedó sin USDT?)' % apodo, 'lista')


# ---------- 3. Completar la orden (sin colocarla) ----------

def completar_orden(det, metodo, monto):
    """Pantalla "Vender USDT" (grabación 05): En VES / En USDT, el monto (EditText), VES Todo, Límite, Vendes,
    la fila de TU método (ej. "Pago Movil 00000000"), Info. del anunciante, la casilla y "Realizar Orden".
    Se completa monto y método. La casilla y "Realizar Orden" quedan para vos."""
    T.en_orden = True
    time.sleep(2)
    ns = nodos()
    if not hay('Vender USDT', ns) or not hay('Vendes', ns):
        frenar('No llegué a la pantalla "Vender USDT"', 'orden')
    if not hay(det['apodo'], ns):
        paso('ojo: no veo a %s en la orden' % det['apodo'])
    en_ves = [n for n in ns if norm(n.t) == 'en ves']
    if en_ves:
        T.nodo(en_ves[0])
        ns = nodos()
    campo = [n for n in ns if n.clase == 'EditText']
    if not campo:
        frenar('No encontré dónde escribir el monto', 'monto')
    if re.sub(r'\D', '', campo[0].t.split('.')[0]) != re.sub(r'\D', '', fmt_monto(monto).split('.')[0]):
        borrar_y_escribir(campo[0], fmt_monto(monto))
    if teclado_visible():
        adb('shell', 'input', 'keyevent', 'KEYCODE_BACK')   # baja el teclado (solo si está, si no saldría de la orden)
        time.sleep(1.5)
    ns = nodos()
    if not hay('Vendes', ns):
        frenar('Se cerró la orden al bajar el teclado', 'teclado')
    # Método: la fila entre "Vendes" y "Info. del anunciante". Si ya muestra el tuyo, no se toca.
    desde = max(n.y for n in ns if norm(n.t) == 'vendes')
    hasta = min([n.y for n in ns if norm(n.t).startswith('info del anunciante')] or [10 ** 5])

    def fila_metodo(ns):
        return [n for n in ns if desde + 40 < n.y < hasta and n.t]

    def es_el_metodo(fila):
        return any(compacto(metodo['nombre']) in compacto(n.t) or compacto(metodo['id']) in compacto(n.t)
                   for n in fila)
    fila = fila_metodo(ns)
    if fila and not es_el_metodo(fila):
        T.nodo(fila[0], 'fila de método (%s)' % fila[0].t)
        if not T.texto((metodo['nombre'], metodo['id']), parcial=True):
            frenar('No tenés "%s" entre tus métodos de pago (o se llama distinto)' % metodo['nombre'], 'metodos')
        time.sleep(1.5)
        ns = nodos()
        fila = fila_metodo(ns)
    paso('fila de método: %s' % ' | '.join(n.t for n in fila))
    campo = [n for n in ns if n.clase == 'EditText']
    monto_ok = bool(campo) and re.sub(r'\D', '', campo[0].t.split('.')[0]) == \
        re.sub(r'\D', '', fmt_monto(monto).split('.')[0])
    return monto_ok, bool(fila) and es_el_metodo(fila)


def recorrido(link):
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
    avisar('Binance: armando la orden…', '%s · %s Bs · %s. No toques la pantalla' %
           (det['apodo'], fmt_monto(monto), metodo['nombre']))
    abrir_p2p(paquete_binance())
    preparar_lista(metodo, monto)
    buscar_en_lista(det['apodo'])
    monto_ok, metodo_ok = completar_orden(det, metodo, monto)
    base = guardar('listo')
    faltan = [x for x, ok in (('el monto', monto_ok), ('el método', metodo_ok)) if not ok]
    return '%s · %s Bs · %s · precio %s.%s Revisá, tildá la casilla y tocá Realizar Orden vos. (%s.png)' % (
        det['apodo'], fmt_monto(monto), metodo['nombre'], det['precio'],
        (' ⚠️ No pude confirmar ' + ' ni '.join(faltan) + '.') if faltan else '', base)


def grabar(segundos=150):
    """Mientras hacés el recorrido A MANO, guarda cada pantalla nueva de Binance (xml + captura) en
    Descargas/binance_grabacion/. Con eso se arman los toques exactos, sin adivinar."""
    if not conectar():
        raise Frenado('No hay ADB')
    paquete_binance()
    carpeta = os.path.join(LOG_DIR, 'binance_grabacion')
    os.makedirs(carpeta, exist_ok=True)
    ultima, n, fin = None, 0, time.time() + segundos
    print('Grabando %d s. Hacé el recorrido a mano, despacio, sin tocar Realizar Orden.' % segundos, flush=True)
    while time.time() < fin:
        xml = volcar(10, 1)
        ns = leer_nodos(xml)
        firma = que_veo(ns)
        if ns and firma != ultima:   # el xml y la firma salen de la misma lectura
            ultima, n = firma, n + 1
            with open(os.path.join(carpeta, '%02d.xml' % n), 'w') as f:
                f.write(xml)
            adb('shell', 'screencap', '-p', '/sdcard/Download/binance_grabacion/%02d.png' % n)
            print('  pantalla %d: %s' % (n, firma[:90]), flush=True)
        time.sleep(1)
    print('Listo: %d pantallas en Descargas/binance_grabacion' % n)


if __name__ == '__main__':
    args = sys.argv[1:]
    try:
        if args[:1] == ['--pantalla']:
            if not conectar():
                raise Frenado('No hay ADB')
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
