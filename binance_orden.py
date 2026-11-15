#!/usr/bin/env python3
"""Arma la orden P2P de la pre-orden en la app de Binance y se frena UN PASO ANTES de colocarla.

Recibe el link del anuncio que eligió la pre-orden (Apps Script, 9_P2P.gs):
  https://c2c.binance.com/es-LA/adv?code=<adNo>&monto=<Bs>&pago=<método>
y maneja el teléfono por ADB (como okx_ordenes.py):
  1. Pide a Binance el detalle de ESE anuncio (desde el teléfono Binance sí responde): apodo, precio, límites y
     métodos. Si el monto no entra en los límites o el método no está en el anuncio, no abre nada.
  2. Abre ese mismo anuncio en la app. Primero por enlace directo; si la app no acepta ninguno, por el camino
     largo: P2P → Vender → USDT → filtro de método y monto → busca el apodo en la lista.
     El método es obligatorio: con el mismo método y monto que usó la pre-orden, la app muestra la misma lista que
     leyó la API, así que el anuncio aparece arriba. Límites y "terceros" ya los validó la pre-orden sobre ese adNo:
     acá solo se confirma que es el mismo trader (apodo) y el precio.
  3. En la orden: elige VES, escribe los Bs y elige el método de pago. NO toca "Vender" ni nada que confirme:
     la orden la colocás vos, con tu huella.

  python binance_orden.py "LINK"              # el recorrido completo (lo corre telefono/binance_orden.sh)
  python binance_orden.py --enlaces "LINK"    # prueba qué enlaces directos abre la app y guarda lo que acepta
  python binance_orden.py --rastrear LINK     # abre un link en la app y busca en el registro a dónde lo llevó
  python binance_orden.py --pantalla NOMBRE   # en 8 s guarda la pantalla en Descargas (para ajustar los textos)

Lo que guarda (capturas y pantallas) queda en Descargas, con nombres binance_*.
"""
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
from okx_ordenes import adb, bloqueado, conectar, tamano_pantalla, textos  # noqa: E402

DESCARGAS = os.path.expanduser('~/storage/downloads')
LOG_DIR = DESCARGAS if os.path.isdir(DESCARGAS) else '.'
ENLACE_BUENO = os.path.expanduser('~/.binance_enlace')   # el enlace directo que funcionó la última vez
DETALLE = 'https://p2p.binance.com/bapi/c2c/v2/public/c2c/adv/selected-adv/'

# 15/11/2026: la app acepta https://app.binance.com y bnc://app.binance.com, pero NINGUNA dirección de anuncio
# (adv?code=, p2p/adv, c2c/adv, adDetail: todas "Este enlace no funciona") y ya no deja compartir anuncios.
# Se entra por el PERFIL del trader (eso sí se comparte) → pestaña Anuncios → su Vender. {u} = número de usuario.
# El que funciona queda en ~/.binance_enlace.
ENLACES = [
    'https://app.binance.com/es-LA/advertiserDetail?advertiserNo={u}',
    'https://app.binance.com/en/advertiserDetail?advertiserNo={u}',
    'https://app.binance.com/es-LA/p2p/advertiserDetail?advertiserNo={u}',
    'bnc://app.binance.com/c2c/advertiserDetail?advertiserNo={u}',
    'bnc://app.binance.com/p2p/advertiserDetail?advertiserNo={u}',
    'bnc://app.binance.com/c2c/userCenter?userNo={u}',
]

# Textos de la app (en español). Se comparan sin acentos ni mayúsculas. Ajustar con lo que muestre --pantalla.
P2P = ('P2P', 'Trading P2P', 'Comercio P2P')
VENDER_TAB = ('Vender',)
FILTRO_PAGO = re.compile(r'^(todos los )?(pagos?|metodos? de pago)$|^todos los metodos')
FILTRO_MONTO = re.compile(r'^(monto|importe|cantidad)$|ingresa.*monto')
ACEPTAR_FILTRO = ('Confirmar', 'Aplicar', 'Listo', 'Buscar')
SELECTOR_PAGO = re.compile(r'(seleccion|elegi|agrega).*(metodo|pago)|^metodo de pago$|^metodos? de pago$')
CERRAR = ('Cerrar', 'Omitir', 'Ahora no', 'Más tarde', 'Entendido', 'Saltar', 'No, gracias', 'Aceptar')
# Ya dentro de la orden, NUNCA se toca algo que diga esto: es lo que coloca la orden (eso lo hacés vos).
PROHIBIDO = re.compile(r'vender|sell|confirm|colocar|realizar|crear|pagar|enviar|continuar|siguiente|aceptar|place')


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


# ---------- 1. El anuncio ----------

def leer_link(link):
    q = urllib.parse.parse_qs(urllib.parse.urlparse(link.strip()).query)
    ad = (q.get('code') or q.get('advNo') or [''])[0]
    if not ad.isdigit():
        raise Frenado('El link no trae el número de anuncio (code=...)')
    monto = float((q.get('monto') or ['0'])[0] or 0)
    return ad, monto, (q.get('pago') or [''])[0]


def buscar(o, claves):
    """Primer valor de alguna de las claves, buscando en todo el JSON."""
    if isinstance(o, dict):
        for k in claves:
            if o.get(k) not in (None, '', []):
                return o[k]
        for v in o.values():
            r = buscar(v, claves)
            if r not in (None, '', []):
                return r
    elif isinstance(o, list):
        for v in o:
            r = buscar(v, claves)
            if r not in (None, '', []):
                return r
    return None


def detalle_anuncio(ad):
    req = urllib.request.Request(DETALLE + ad, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=15) as r:
        datos = json.load(r).get('data')
    if not datos:
        raise Frenado('Binance no devolvió el anuncio %s: puede que ya no exista' % ad)
    metodos = buscar(datos, ['tradeMethods']) or []
    return {
        'apodo': buscar(datos, ['nickName']) or '',
        'usuario': str(buscar(datos, ['userNo', 'advertiserNo']) or ''),   # para abrir su perfil en la app
        'precio': float(buscar(datos, ['price']) or 0),
        'min': float(buscar(datos, ['minSingleTransAmount']) or 0),
        'max': float(buscar(datos, ['dynamicMaxSingleTransAmount', 'maxSingleTransAmount']) or 0),
        'metodos': [{'id': m.get('identifier') or '', 'nombre': m.get('tradeMethodName') or m.get('identifier') or ''}
                    for m in metodos if isinstance(m, dict)],
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

PAQ = ''   # paquete de Binance: solo se miran sus textos (si no, el apodo que imprime Termux cuenta como "visto")


def nodos():
    """[(texto, x, y, clase, clickeable)] de la pantalla de Binance, con EditText aunque estén vacíos."""
    _, xml = textos()
    if not xml:
        return []
    lista = []
    for n in ET.fromstring(xml).iter('node'):
        if PAQ and n.get('package') != PAQ:
            continue
        b = re.findall(r'\d+', n.get('bounds') or '')
        if len(b) != 4:
            continue
        t = (n.get('text') or n.get('content-desc') or '').strip()
        clase = (n.get('class') or '').split('.')[-1]
        if t or clase == 'EditText':
            lista.append((t, (int(b[0]) + int(b[2])) // 2, (int(b[1]) + int(b[3])) // 2, clase,
                          n.get('clickable') == 'true'))
    return lista


def guardar(nombre):
    hora = time.strftime('%H%M%S')
    base = 'binance_%s_%s' % (nombre, hora)
    adb('shell', 'screencap', '-p', '/sdcard/Download/%s.png' % base)
    with open(os.path.join(LOG_DIR, base + '.xml'), 'w') as f:
        f.write(textos()[1])
    return base


def frenar(motivo, nombre='fallo'):
    base = guardar(nombre)
    raise Frenado('%s. Guardé la pantalla en Descargas (%s.png)' % (motivo, base))


class Toques:
    """Todos los toques pasan por acá. Desde que se abre la orden (en_orden), no se toca nada PROHIBIDO."""
    en_orden = False

    def xy(self, texto, x, y):
        if self.en_orden and PROHIBIDO.search(norm(texto)):
            raise Frenado('Por seguridad no toqué "%s"' % texto)
        paso('toco "%s"' % texto)
        adb('shell', 'input', 'tap', str(x), str(y))
        time.sleep(2)

    def texto(self, opciones, intentos=4, regex=None, parcial=False):
        """Toca el primer texto igual a alguna opción (que la contenga, con parcial; o que cumpla regex)."""
        for _ in range(intentos):
            for t, x, y, _, _ in nodos():
                if (regex and regex.search(norm(t))) or any(
                        compacto(t) == compacto(o) or (parcial and compacto(o) in compacto(t)) for o in opciones if o):
                    self.xy(t, x, y)
                    return True
            time.sleep(1.5)
        return False


T = Toques()


def cerrar_carteles():
    for t, x, y, _, _ in nodos():
        if t in CERRAR and not T.en_orden:
            T.xy(t, x, y)
            return True
    return False


def en_pantalla(texto):
    return any(compacto(texto) and compacto(texto) in compacto(t) for t, _, _, _, _ in nodos())


def escribir(numero):
    adb('shell', 'input', 'text', numero)
    time.sleep(1.5)


def fmt_monto(m):
    return ('%.2f' % m).rstrip('0').rstrip('.')


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
    """La app que está en pantalla (la ventana con el foco)."""
    for l in adb('shell', 'dumpsys', 'window').splitlines():
        if 'mCurrentFocus' in l or 'mFocusedApp' in l:
            return l.strip()
    return ''


def que_veo():
    return ' | '.join(t for t, _, _, _, _ in nodos()[:15])


def abrir_enlace(paquete, url):
    r = adb('shell', 'am', 'start', '-W', '-a', 'android.intent.action.VIEW', '-d', "'%s'" % url, paquete)
    paso('am start: ' + ' '.join(r.split())[:200])
    return 'Error' not in r and 'unable to resolve' not in r.lower()


def esperar_anuncio(apodo, segundos=30):
    """Espera a que Binance quede al frente mostrando el apodo. Cierra carteles mientras tanto."""
    fin = time.time() + segundos
    while time.time() < fin:
        time.sleep(3)
        if PAQ not in al_frente():
            continue
        ns = nodos()
        if any('enlace no funciona' in norm(t) for t, _, _, _, _ in ns):   # la app no conoce ese enlace
            for t, x, y, _, _ in ns:
                if norm(t) == 'ok':
                    adb('shell', 'input', 'tap', str(x), str(y))
            paso('la app dice "Este enlace no funciona"')
            return False
        cerrar_carteles()
        if en_pantalla(apodo):
            return True
    paso('al frente: %s' % al_frente())
    paso('veo: %s' % que_veo())
    return False


def entrar_a_anuncios():
    """En el perfil: pestaña "Anuncios (n)" y el Vender de su anuncio. Desde ahí ya es la orden."""
    if not T.texto(('Anuncios',), intentos=3, parcial=True):
        frenar('Abrí el perfil pero no encontré la pestaña Anuncios', 'perfil')
    time.sleep(2)
    botones = sorted((n for n in nodos() if norm(n[0]) in ('vender', 'vender usdt')), key=lambda n: n[2])
    if not botones:
        paso('veo: %s' % que_veo())
        frenar('En sus anuncios no hay uno para venderle USDT', 'anuncios')
    T.xy(botones[0][0], botones[0][1], botones[0][2])
    T.en_orden = True


def plantillas():
    lista = ENLACES[:]
    if os.path.exists(ENLACE_BUENO):
        bueno = open(ENLACE_BUENO).read().strip()
        if bueno in lista:
            lista = [bueno] + [e for e in lista if e != bueno]
    return lista


def por_perfil(paquete, det):
    if not det['usuario']:
        paso('el anuncio no trae el número de usuario del trader')
        return False
    lista = plantillas()
    if not os.path.exists(ENLACE_BUENO) or lista[0] != open(ENLACE_BUENO).read().strip():
        return False   # ningún link de perfil funcionó todavía (probarlos con --enlaces): directo a la lista
    for plantilla in lista[:1]:
        if not abrir_enlace(paquete, plantilla.format(u=det['usuario'])):
            continue
        if esperar_anuncio(det['apodo']):
            paso('abrió el perfil con %s' % plantilla)
            with open(ENLACE_BUENO, 'w') as f:
                f.write(plantilla)
            entrar_a_anuncios()
            return True
    return False


# Links a la portada de P2P (con el filtro de método, si la app lo toma). Se prueban antes de ir por el inicio.
LINKS_P2P = [
    'https://app.binance.com/es-LA/p2p/trade/sell/USDT?fiat=VES&payment={pago}',
    'https://app.binance.com/es-LA/trade/sell/USDT?fiat=VES&payment={pago}',
    'bnc://app.binance.com/c2c/home',
    'bnc://app.binance.com/p2p/home',
    'https://app.binance.com/es-LA/p2p',
]
BOTON_P2P = (0.152, 0.31)   # ícono P2P del inicio (captura del 15/11), por si la pantalla animada no se deja leer


def en_p2p():
    ns = nodos()
    return any(norm(n[0]) == 'vender' for n in ns) and any(norm(n[0]) == 'comprar' for n in ns)


def abrir_p2p(paquete, metodo):
    """Llega a la portada de P2P: primero por link; si no, abre Binance y toca P2P (por texto o por posición)."""
    for plantilla in LINKS_P2P:
        if not abrir_enlace(paquete, plantilla.format(pago=metodo['id'])):
            continue
        for _ in range(4):
            time.sleep(3)
            ns = nodos()
            if any('enlace no funciona' in norm(t) for t, _, _, _, _ in ns):
                T.texto(('Ok',), intentos=1)
                break
            if en_p2p():
                paso('P2P abrió con %s' % plantilla)
                return
    adb('shell', 'am', 'start', '-W', '-a', 'android.intent.action.MAIN', '-c', 'android.intent.category.LAUNCHER',
        paquete)
    for _ in range(8):
        time.sleep(3)
        if PAQ in al_frente():
            break
    else:
        frenar('Binance no se abrió (al frente: %s)' % al_frente(), 'inicio')
    time.sleep(4)
    cerrar_carteles()
    if not T.texto(P2P, intentos=3):
        ancho, alto = tamano_pantalla()
        paso('no leí el botón P2P: lo toco por posición')
        adb('shell', 'input', 'tap', str(int(ancho * BOTON_P2P[0])), str(int(alto * BOTON_P2P[1])))
    for _ in range(4):
        time.sleep(3)
        cerrar_carteles()
        if en_p2p():
            return
    frenar('No llegué a P2P desde el inicio de Binance', 'inicio')


def por_lista(paquete, apodo, metodo, monto):
    """Camino largo: P2P → Vender → USDT → filtros de método y monto → buscar el apodo y tocar su Vender."""
    abrir_p2p(paquete, metodo)
    tabs = sorted((n for n in nodos() if norm(n[0]) in [norm(v) for v in VENDER_TAB]), key=lambda n: n[2])
    if not tabs:   # la pestaña es el "Vender" de más arriba (los de abajo son los botones de cada anuncio)
        frenar('No encontré la pestaña Vender en P2P', 'p2p')
    T.xy(tabs[0][0], tabs[0][1], tabs[0][2])
    T.texto(('USDT',), intentos=2)
    if not en_pantalla('VES'):
        frenar('P2P no está en VES: elegí VES arriba una vez a mano y probá de nuevo', 'moneda')
    # Método (obligatorio): el mismo filtro que usó la pre-orden
    if not T.texto((), regex=FILTRO_PAGO):
        frenar('No encontré el filtro de método de pago', 'filtro_pago')
    if not T.texto((metodo['nombre'], metodo['id']), intentos=3, parcial=True):
        frenar('No encontré "%s" en la lista de métodos' % metodo['nombre'], 'lista_metodos')
    T.texto(ACEPTAR_FILTRO, intentos=1)
    # Monto en Bs
    if T.texto((), regex=FILTRO_MONTO, intentos=2):
        escribir(fmt_monto(monto))
        T.texto(ACEPTAR_FILTRO, intentos=2)
    else:
        paso('no encontré el filtro de monto: sigo solo con el método')
    # Buscar el apodo en la lista y tocar el Vender de su tarjeta
    ancho, alto = tamano_pantalla()
    for _ in range(8):
        time.sleep(2)
        ns = nodos()
        fila = [n for n in ns if compacto(apodo) == compacto(n[0])]
        if fila:
            _, _, ya, _, _ = fila[0]
            botones = sorted((n for n in ns if norm(n[0]) in ('vender', 'vender usdt') and n[2] > ya - 50),
                             key=lambda n: n[2])
            if botones:
                T.xy(botones[0][0], botones[0][1], botones[0][2])
                T.en_orden = True
                return True
        adb('shell', 'input', 'swipe', str(ancho // 2), str(int(alto * .75)), str(ancho // 2), str(int(alto * .35)), '400')
    frenar('No encontré a %s en la lista (¿lo tomó otro o cambió de precio?)' % apodo, 'lista')


# ---------- 3. Completar la orden (sin colocarla) ----------

def completar_orden(det, metodo, monto):
    """Pantalla "Vender USDT" (vista el 15/11/2026): pestaña "En VES", el monto (0), "VES Todo", Límite, Vendes,
    la fila de TU método de pago (ej. "Banesco 0000000 >"), Info. del anunciante, la casilla de términos y el botón
    "Realizar Orden". Se completa monto y método. La casilla y "Realizar Orden" quedan para vos."""
    T.en_orden = True
    time.sleep(3)
    ns = nodos()
    if not any(norm(n[0]) in ('vendes', 'vender usdt') for n in ns):
        paso('veo: %s' % que_veo())
        frenar('No llegué a la pantalla "Vender USDT"', 'orden')
    for n in ns:                       # monto en Bs: pestaña "En VES" (si hay otra en USDT)
        if norm(n[0]) == 'en ves':
            T.xy(n[0], n[1], n[2])
            ns = nodos()
            break
    campos = [n for n in ns if n[3] == 'EditText']
    if not campos:                     # sin EditText: el "0" grande debajo de "En VES"
        y_ves = min([n[2] for n in ns if norm(n[0]) == 'en ves'] or [0])
        campos = sorted([n for n in ns if re.fullmatch(r'[\d.,]+', n[0]) and n[2] > y_ves], key=lambda n: n[2])
    if not campos:
        paso('veo: %s' % que_veo())
        frenar('No encontré dónde escribir el monto', 'monto')
    T.xy('campo de monto', campos[0][1], campos[0][2])
    adb('shell', 'input', 'keyevent', 'KEYCODE_MOVE_END')
    for _ in range(12):                # borra el 0 (o lo que hubiera)
        adb('shell', 'input', 'keyevent', 'KEYCODE_DEL')
    escribir(fmt_monto(monto))
    adb('shell', 'input', 'keyevent', 'KEYCODE_BACK')   # baja el teclado
    time.sleep(2)
    ns = nodos()
    if not any(norm(n[0]) == 'vendes' for n in ns):
        frenar('Al bajar el teclado se cerró la orden', 'teclado')
    # Método: la fila entre "Vendes" y "Info. del anunciante". Si ya muestra el tuyo, no se toca.
    y_desde = max(n[2] for n in ns if norm(n[0]) == 'vendes')
    y_hasta = min([n[2] for n in ns if norm(n[0]).startswith('info del anunciante')] or [10 ** 5])
    fila = [n for n in ns if y_desde + 40 < n[2] < y_hasta and n[0]]
    paso('fila de método: %s' % ' | '.join(n[0] for n in fila))
    elegido = lambda: any(compacto(metodo['nombre']) in compacto(n[0]) or compacto(metodo['id']) in compacto(n[0])
                          for n in fila)
    if fila and not elegido():
        T.xy(fila[0][0], fila[0][1], fila[0][2])
        time.sleep(2)
        if not T.texto((metodo['nombre'], metodo['id']), intentos=3, parcial=True):
            frenar('No tenés "%s" entre tus métodos de pago (o se llama distinto)' % metodo['nombre'], 'metodos')
        time.sleep(2)
        ns = nodos()
        fila = [n for n in ns if y_desde + 40 < n[2] < y_hasta and n[0]]
    metodo_ok = bool(fila) and elegido()
    digitos = re.sub(r'\D', '', fmt_monto(monto).split('.')[0])
    monto_ok = any(digitos and digitos == re.sub(r'\D', '', t.split('.')[0]) for t, _, _, _, _ in nodos())
    return monto_ok, metodo_ok


def recorrido(link):
    ad, monto, pago = leer_link(link)
    det = detalle_anuncio(ad)
    metodo = elegir_metodo(det, pago)
    paso('anuncio %s: %s, precio %s, límites %s-%s, %s' % (ad, det['apodo'], det['precio'], det['min'], det['max'],
                                                          metodo['nombre']))
    if not monto:
        raise Frenado('El link no trae el monto: subí el Apps Script nuevo y buscá el anuncio de nuevo')
    if det['min'] and monto < det['min'] or det['max'] and monto > det['max']:
        raise Frenado('%s Bs no entra en los límites del anuncio (%s - %s): buscá otro anuncio' %
                      (fmt_monto(monto), fmt_monto(det['min']), fmt_monto(det['max'])))
    if not conectar():
        raise Frenado('No hay ADB. Tocá RECONECTAR en la notificación de ADB y probá de nuevo')
    if bloqueado():
        raise Frenado('El teléfono está bloqueado: desbloquealo y probá de nuevo')
    avisar('Binance: armando la orden…', '%s · %s Bs · %s. No toques la pantalla' %
           (det['apodo'], fmt_monto(monto), metodo['nombre']))
    paquete = paquete_binance()
    if not por_perfil(paquete, det):
        paso('ningún enlace abrió el perfil: voy por la lista')
        por_lista(paquete, det['apodo'], metodo, monto)
    monto_ok, metodo_ok = completar_orden(det, metodo, monto)
    base = guardar('listo')
    faltan = [x for x, ok in (('el monto', monto_ok), ('el método', metodo_ok)) if not ok]
    return '%s · %s Bs · %s · precio %s.%s Revisá y tocá Vender vos. (%s.png)' % (
        det['apodo'], fmt_monto(monto), metodo['nombre'], det['precio'],
        (' ⚠️ No pude confirmar ' + ' ni '.join(faltan) + '.') if faltan else '', base)


def probar_enlaces(link):
    """Muestra qué enlaces de Binance declara la app y prueba abrir el anuncio con cada uno."""
    ad, _, _ = leer_link(link)
    det = detalle_anuncio(ad)
    if not conectar():
        raise Frenado('No hay ADB')
    paquete = paquete_binance()
    filtros = [l.strip() for l in adb('shell', 'dumpsys', 'package', paquete).splitlines()
               if re.search(r'Scheme: "|Authority: "|Path: "|PathPrefix|PathPattern', l)]
    archivo = os.path.join(LOG_DIR, 'binance_enlaces.txt')
    with open(archivo, 'w') as f:
        f.write('\n'.join(filtros))
    print('Enlaces que declara %s (%d líneas, todo en %s):' % (paquete, len(filtros), archivo))
    for l in sorted(set(filtros)):
        if 'binance' in l or 'Scheme' in l:
            print('  ' + l)
    print('\nAnuncio %s de %s (usuario %s). Probando enlaces al perfil:' % (ad, det['apodo'], det['usuario'] or '?'))
    if not det['usuario']:
        print('  El detalle del anuncio no trae el número de usuario. Lo guardé en binance_detalle.json')
        req = urllib.request.Request(DETALLE + ad, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as r, open(os.path.join(LOG_DIR, 'binance_detalle.json'), 'wb') as f:
            f.write(r.read())
        return
    for n, plantilla in enumerate(ENLACES):
        url = plantilla.format(u=det['usuario'])
        if not abrir_enlace(paquete, url):
            print('  ✗ la app no lo acepta: ' + url)
            continue
        ok = esperar_anuncio(det['apodo'], 25)
        print('  %s %s' % ('✓ ABRE EL PERFIL:' if ok else '· no abre el perfil:', url))
        if ok:
            with open(ENLACE_BUENO, 'w') as f:
                f.write(plantilla)
            T.texto(('Anuncios',), intentos=3, parcial=True)
            time.sleep(2)
            print('  Guardé la pestaña Anuncios: %s.png' % guardar('anuncios'))
            break
    adb('shell', 'input', 'keyevent', 'KEYCODE_HOME')


def rastrear(url):
    """Abre un link en la app (ej. el link corto de un perfil compartido) y busca en el registro de Android
    la dirección interna a la que la app lo convirtió. Guarda todo en Descargas/binance_rastreo.txt."""
    if not conectar():
        raise Frenado('No hay ADB')
    paquete = paquete_binance()
    adb('logcat', '-c')
    if not abrir_enlace(paquete, url) and '://www.binance.com/' in url:
        abrir_enlace(paquete, url.replace('://www.binance.com/', '://app.binance.com/'))   # la app solo toma app.
    time.sleep(12)
    registro = adb('logcat', '-d', '-v', 'brief', espera=60)
    pistas = [l for l in registro.splitlines()
              if re.search(r'bnc://|app\.binance\.com|binance\.com/|dplk|advertiser|userNo|deeplink|DeepLink|schema|router',
                           l, re.I)]
    with open(os.path.join(LOG_DIR, 'binance_rastreo.txt'), 'w') as f:
        f.write('\n'.join(pistas))
    print('%d líneas con pistas (todas en Descargas/binance_rastreo.txt). Las primeras:' % len(pistas))
    for l in pistas[:40]:
        print('  ' + l[:300])
    print('Pantalla: %s.png' % guardar('rastreo'))


if __name__ == '__main__':
    args = sys.argv[1:]
    try:
        if args[:1] == ['--pantalla']:
            if not conectar():
                raise Frenado('No hay ADB')
            time.sleep(8)
            print('Guardé %s.png y .xml en Descargas' % guardar(args[1] if len(args) > 1 else 'pantalla'))
        elif args[:1] == ['--rastrear'] and len(args) > 1:
            rastrear(args[1])
        elif args[:1] == ['--enlaces'] and len(args) > 1:
            probar_enlaces(args[1])
        elif len(args) == 1:
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
