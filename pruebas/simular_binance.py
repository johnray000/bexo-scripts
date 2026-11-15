#!/usr/bin/env python3
"""Prueba binance_orden.py SIN teléfono, contra pantallas grabadas de verdad.

  python3 pruebas/simular_binance.py CARPETA

CARPETA (en los archivos del proyecto, p2p/binance_app/grabacion/; no va al repo porque muestra saldos) tiene:
  01.xml  Seleccionar divisa   02.xml / 03.xml  panel Filtrar (embudo), arriba / desplazado   04.xml  lista P2P
  05.xml  Vender USDT (la orden)        quiero_vender.xml  hoja del chip Monto (15/11 02:13)
  seleccionar_activo.xml  hoja de activo (15/11 02:08)

Cada toque se resuelve buscando qué nodo del xml actual está en ese punto (como el teléfono). Lo único armado a mano:
la lista P2P "sin filtros" es 04.xml con los chips en "Monto" y "Pago" (así se ven en la captura del 15/11 02:13),
y la lista de métodos de pago NO está grabada: el simulador la devuelve como pantalla desconocida y el
recorrido tiene que frenarse ahí, nunca tocar a ciegas.
"""
import os
import re
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CARPETA = sys.argv[1]
sys.argv = sys.argv[:1]
import binance_orden as b  # noqa: E402

X = {k: open(os.path.join(CARPETA, k + '.xml')).read()
     for k in ('01', '02', '03', '04', '05', 'quiero_vender', 'seleccionar_activo')}
NO_GRABADA = ('<?xml version="1.0"?><hierarchy><node text="PANTALLA NO GRABADA" class="android.widget.TextView" '
              'package="com.binance.dev" bounds="[0,500][1080,600]"/></hierarchy>')
APODO = 'PrincessYor'
METODO = {'id': 'PagoMovil', 'nombre': 'Pago Movil'}


def llave(xml, rid, prendida):
    """Pone un interruptor (Switch) prendido o apagado en el xml grabado."""
    x, k = re.subn(r'(resource-id="com\.binance\.dev:id/%s"[^>]*?checked=")(true|false)' % rid,
                   r'\g<1>' + ('true' if prendida else 'false'), xml)
    assert k == 1, 'no está el interruptor %s' % rid
    return x


def cambiar(xml, viejo_texto, rid, nuevo):
    a = 'text="%s" resource-id="com.binance.dev:id/%s"' % (viejo_texto, rid)
    assert a in xml, 'no está %s en el xml grabado' % a
    return xml.replace(a, 'text="%s" resource-id="com.binance.dev:id/%s"' % (nuevo, rid))


class Telefono:
    def __init__(self, pantalla='p2p', moneda='VES', monto=None, pago=None, tab='vender', frente='binance',
                 pro=True, embudo_falla=1, orden_monto='5000'):
        self.s = dict(pantalla=pantalla, moneda=moneda, monto=monto, pago=pago, tab=tab, frente=frente,
                      pro=pro, embudo_falla=embudo_falla, campo='', foco=False, orden_monto=orden_monto,
                      tocado_apodo=None)
        self.malos = []        # toques que nunca deberían pasar
        self.toques = []

    def xml(self):
        s = self.s
        p = s['pantalla']
        if p == 'p2p':
            x = cambiar(X['04'], 'VES', '2131446692', s['moneda'])
            x = cambiar(x, '5,000', 'tv_amount', '{:,.0f}'.format(s['monto']) if s['monto'] else 'Monto')
            x = cambiar(x, 'Pago Movil', '2131452724', s['pago'] or 'Pago')
            if s['tab'] == 'comprar':
                x = x.replace('text="Vender" resource-id="com.binance.dev:id/2131452588"',
                              'text="Comprar" resource-id="com.binance.dev:id/2131452588"')
            return x
        if p == 'monto':
            return cambiar(X['quiero_vender'], 'Ingresa el monto total', '2131432439',
                           s['campo'] or 'Ingresa el monto total')
        if p == 'filtrar':
            if s['foco']:                 # con el teclado el panel se desplaza (grabación 03)
                return cambiar(X['03'], '5000', '2131432527', s['campo'] or 'Ingresa el monto total')
            return llave(X['02'], '2131444418', s['pro'])
        if p == 'orden':
            return cambiar(X['05'], '5000', '2131432247', s['campo'] if s['foco'] else s['orden_monto'])
        if p == 'divisa':
            return X['01']
        if p == 'activo':
            return X['seleccionar_activo']
        if p == 'inicio':
            return ''                     # animado: uiautomator no devuelve nada
        return NO_GRABADA

    def nodo_en(self, x, y):
        mejor = None
        for n in ET.fromstring(self.xml().encode()).iter('node'):
            bb = [int(v) for v in re.findall(r'\d+', n.get('bounds') or '')]
            if len(bb) == 4 and bb[0] <= x <= bb[2] and bb[1] <= y <= bb[3] and \
                    ((n.get('text') or '').strip() or (n.get('class') or '').split('.')[-1] in ('EditText', 'Switch')
                     or n.get('clickable') == 'true'):
                area = ((bb[2] - bb[0]) * (bb[3] - bb[1]), 0 if (n.get('text') or '').strip() else 1)
                if mejor is None or area < mejor[0]:     # el más chico; si empatan, el que tiene texto
                    mejor = (area, n.get('text') or '', bb, n.get('class') or '')
        return mejor

    def tap(self, x, y):
        s = self.s
        p = s['pantalla']
        if p == 'inicio':
            if abs(x - 1080 * b.BOTON_P2P[0]) < 60 and abs(y - 2400 * b.BOTON_P2P[1]) < 60:
                s['pantalla'] = 'p2p'
            return
        n = self.nodo_en(x, y)
        t = n[1] if n else ''
        self.toques.append((p, t))
        if p == 'orden' and (b.PROHIBIDO.search(b.norm(t)) or y > 1950):   # términos, casilla, Realizar Orden
            self.malos.append('tocó "%s" en la orden' % t)
        if p == 'p2p':
            if t == 'Vender' and y < 480:
                s['tab'] = 'vender'
            elif t == s['moneda'] and y < 360:
                s['pantalla'] = 'divisa'
            elif t == 'USDT':
                s['pantalla'] = 'activo'
            elif 995 <= x <= 1045 and 355 <= y <= 455:          # el embudo
                if s['embudo_falla'] > 0:
                    s['embudo_falla'] -= 1                       # no abre a la primera (pasa en el teléfono)
                else:
                    s['pantalla'], s['campo'], s['foco'] = 'filtrar', '', False
            elif n and 330 < y < 480 and 267 <= x <= 357:
                s['pantalla'], s['campo'], s['foco'] = 'monto', '', False
            elif n and 330 < y < 480 and 427 <= x <= 616:
                s['pantalla'] = 'metodos'         # NO grabada
            elif t in ('Vender', 'Comprar') and y > 480:
                if s['tab'] != 'vender':
                    self.malos.append('tocó la tarjeta estando en Comprar')
                if s['pro']:
                    self.malos.append('entró al anuncio con "Solo comerciantes Pro" prendido')
                if not (s['monto'] and s['pago'] and s['moneda'] == 'VES'):
                    self.malos.append('entró al anuncio sin filtros completos: %s' % s)
                s['tocado_apodo'] = 'PrincessYor' if y < 900 else 'otro'
                s['pantalla'], s['foco'] = 'orden', False
        elif p == 'divisa':
            if t in ('VES', 'UYU', 'COP', 'AZN', 'USD', 'ARS'):
                s['moneda'], s['pantalla'] = t, 'p2p'
        elif p == 'filtrar':
            if n and n[3].endswith('Switch'):
                if 856 <= y <= 906:
                    s['pro'] = not s['pro']
                else:
                    self.malos.append('tocó otro interruptor del panel (y=%d)' % y)
            elif n and n[3].endswith('EditText'):
                s['foco'] = True
            elif t == 'Confirmar':
                s['monto'] = b.numero(s['campo']) or s['monto']
                s['pantalla'], s['foco'] = 'p2p', False
        elif p == 'monto':
            if n and n[3].endswith('EditText'):
                s['foco'] = True
            elif t == 'Confirmar':
                s['monto'] = b.numero(s['campo'])
                s['pantalla'], s['foco'] = 'p2p', False
        elif p == 'orden':
            if n and n[3].endswith('EditText'):
                s['foco'], s['campo'] = True, s['orden_monto']

    def key(self, k):
        s = self.s
        if k == 'KEYCODE_DEL' and s['foco']:
            s['campo'] = s['campo'][:-1]
        elif k == 'KEYCODE_BACK':
            if s['pantalla'] in ('activo', 'metodos', 'monto', 'filtrar', 'divisa', 'orden'):
                s['pantalla'] = 'p2p'

    def adb(self, *a, espera=60, salida=True):
        s = self.s
        if a[:2] == ('exec-out', 'uiautomator'):
            return self.xml() if s['frente'] == 'binance' else ''
        if a[:3] == ('shell', 'input', 'tap'):
            self.tap(int(a[3]), int(a[4]))
        elif a[:3] == ('shell', 'input', 'text'):
            if s['foco']:
                s['campo'] += a[3]
        elif a[:3] == ('shell', 'input', 'keyevent'):
            self.key(a[3])
        elif a[:3] == ('shell', 'dumpsys', 'window'):
            return {'binance': 'mCurrentFocus=Window{1 u0 com.binance.dev/x}',
                    'cortina': 'mCurrentFocus=Window{88b51fd u0 NotificationShade}',
                    'termux': 'mCurrentFocus=Window{2 u0 com.termux/x}'}[s['frente']]
        elif a[:4] == ('shell', 'cmd', 'statusbar', 'collapse'):
            if s['frente'] == 'cortina':
                s['frente'] = 'termux'
        elif a[:3] == ('shell', 'am', 'start') or a[:2] == ('shell', 'monkey'):
            if s['frente'] == 'termux':
                s['frente'], s['pantalla'] = 'binance', s['pantalla']
        elif a[:3] == ('shell', 'pm', 'list'):
            return 'package:com.binance.dev'
        return ''


def correr(nombre, espera, **kw):
    t = Telefono(**kw)
    b.adb = t.adb
    b.time.sleep = lambda s: None
    b.tamano_pantalla = lambda: (1080, 2400)
    b.guardar = lambda n: 'binance_%s' % n
    b.EN_ORDEN = False
    b.PAQ = ''
    b.paquete_binance()
    print('==== %s' % nombre)
    try:
        ns = b.llegar_a_la_orden(APODO, METODO, 5000.0)
        r = b.completar_orden(ns, APODO, METODO, 5000.0)
        res = 'orden %s %s' % r
        if t.s['tocado_apodo'] != APODO:
            t.malos.append('abrió la orden de otro')
        if t.s['foco'] and t.s['campo'] != '5000':
            t.malos.append('el monto quedó en %r' % t.s['campo'])
    except b.Frenado as e:
        res = 'frenado: %s' % e
    try:                                     # la barrera final: con EN_ORDEN nada prohibido se toca
        b.tocar('Realizar Orden', 540, 2190, en_orden_ok=True)
        if b.EN_ORDEN:
            t.malos.append('tocó Realizar Orden')
    except b.Frenado:
        pass
    ok = espera in res and not t.malos
    print('  -> %s\n  %s (esperaba: %s)%s' % (res, 'BIEN' if ok else 'MAL', espera,
                                             ''.join('\n  MAL: ' + m for m in t.malos)))
    return ok


casos = [
    ('lista con filtros ya puestos (04): igual pasa por el embudo por lo de Pro', 'orden True True',
     dict(monto=5000, pago='Pago Movil')),
    ('sin monto, Pro prendido, el embudo no abre a la primera', 'orden True True', dict(pago='Pago Movil')),
    ('sin monto, Pro ya apagado, el embudo abre a la primera', 'orden True True',
     dict(pago='Pago Movil', pro=False, embudo_falla=0)),
    ('el embudo no abre nunca', 'no avanza', dict(pago='Pago Movil', embudo_falla=99)),
    ('moneda ARS y pestaña Comprar', 'orden True True', dict(moneda='ARS', tab='comprar', pago='Pago Movil')),
    ('quedó abierto "Seleccionar activo" (como 02:08)', 'orden True True',
     dict(pantalla='activo', pago='Pago Movil')),
    ('quedó abierta la hoja "Quiero vender" (como 02:13)', 'orden True True',
     dict(pantalla='monto', pago='Pago Movil')),
    ('Binance cerrado y cortina abierta (como 02:03), inicio animado', 'orden True True',
     dict(frente='cortina', pantalla='inicio', pago='Pago Movil')),
    ('la orden trae otro monto: lo corrige', 'orden True True', dict(monto=5000, pago='Pago Movil',
                                                                     orden_monto='1234')),
    ('método sin elegir (como hoy 02:13): lista NO grabada', 'Pantalla que no conozco', dict(monto=5000)),
    ('quedó abierta una orden vieja', 'orden True True', dict(pantalla='orden', pago='Pago Movil')),
]
bien = sum(correr(*c[:2], **c[2]) for c in casos)
print('\n%d de %d casos bien' % (bien, len(casos)))
print('==== el apodo no está en la lista')
t = Telefono(monto=5000, pago='Pago Movil')
b.adb, b.EN_ORDEN = t.adb, False
try:
    b.llegar_a_la_orden('NoExiste', METODO, 5000.0)
    print('  MAL: no se frenó')
except b.Frenado as e:
    print('  BIEN: %s' % e)
sys.exit(0 if bien == len(casos) else 1)
