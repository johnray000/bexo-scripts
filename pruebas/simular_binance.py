#!/usr/bin/env python3
"""Prueba binance_orden.py SIN teléfono, contra pantallas grabadas de verdad.

  python3 pruebas/simular_binance.py CARPETA

CARPETA (en los archivos del proyecto, p2p/binance_app/grabacion/; no va al repo porque muestra saldos) tiene:
  01.xml                 Seleccionar divisa                       (grabación 15/11 madrugada)
  03.xml                 panel Filtrar desplazado (con teclado)   (madrugada)
  04.xml                 lista P2P VES con PrincessYor             (madrugada)
  05.xml                 Vender USDT de PrincessYor                (madrugada)
  quiero_vender.xml      hoja del chip Monto                       (15/11 02:13)
  seleccionar_activo.xml hoja de activo                            (15/11 02:08)
  lista_ars_comprar.xml  lista en ARS, pestaña Comprar, con casillas Pro / Nuevo usuario (15/11 15:27, 01)
  filtrar.xml            panel Filtrar recién abierto              (15:27, 05)
  lista_ves.xml          lista VES con wen2, sin barra de abajo en el xml (15:27, 08)
  orden_wen2.xml         Vender USDT de wen2, casilla sin tildar   (15:27, 09)
  filtrar_metodos.xml    panel Filtrar bajado hasta "Método de Pago", ninguno elegido (16:34, 02)
  filtrar_metodos_elegido.xml  lo mismo con "(1 seleccionado/s)" (16:34, 03)
  precio_actualizado.xml cartel "El precio del anuncio se ha actualizado… Entendido" sobre la orden (17:46)
  filtrar_reabierto.xml  panel reabierto: el método volvió a "Todo" aunque la lista diga Pago Movil (16:34, 05)

Cada toque se resuelve buscando qué nodo del xml actual está en ese punto (como el teléfono). Se imita lo que pasa
en el teléfono: el embudo a veces no abre al primer toque y la PRIMERA vez que se confirma el filtro, la app lo
descarta. Lo armado a mano: la lista "sin filtros" es la grabada con los chips en "Monto" y "Pago" (así se ven en
las capturas). La lista de métodos de pago NO está grabada: si el recorrido la abriera, sería pantalla desconocida.
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
     for k in ('01', '03', '04', '05', 'quiero_vender', 'seleccionar_activo', 'lista_ars_comprar', 'filtrar',
               'lista_ves', 'orden_wen2', 'filtrar_metodos', 'filtrar_metodos_elegido', 'filtrar_reabierto',
               'precio_actualizado')}
METODOS_PANEL = ('Pago Movil', 'Banco de Venezuela', 'Banesco', 'Mercantil', 'Provincial')
NO_GRABADA = ('<?xml version="1.0"?><hierarchy><node text="PANTALLA NO GRABADA" class="android.widget.TextView" '
              'package="com.binance.dev" bounds="[0,500][1080,600]"/></hierarchy>')
METODO = {'id': 'PagoMovil', 'nombre': 'Pago Movil'}
# Interruptores del panel Filtrar: rid → (fila y1, y2), y cómo vienen (grabación 15:27, 05)
LLAVES = {'2131444437': (726, 776), '2131444418': (856, 906), '2131444409': (986, 1036)}
DE_FABRICA = {'2131444437': True, '2131444418': False, '2131444409': True}
# Las dos listas grabadas: el apodo de la primera tarjeta y el xml de su orden
LISTAS = {'04': ('PrincessYor', '05', '5000'), 'lista_ves': ('wen2', 'orden_wen2', '5000')}


def cambiar(xml, viejo_texto, rid, nuevo):
    a = 'text="%s" resource-id="com.binance.dev:id/%s"' % (viejo_texto, rid)
    assert a in xml, 'no está %s en el xml grabado' % a
    return xml.replace(a, 'text="%s" resource-id="com.binance.dev:id/%s"' % (nuevo, rid))


def llave(xml, rid, prendida):
    x, k = re.subn(r'(resource-id="com\.binance\.dev:id/%s"[^>]*?checked=")(true|false)' % rid,
                   r'\g<1>' + ('true' if prendida else 'false'), xml)
    assert k == 1, 'no está el interruptor %s' % rid
    return x


class Telefono:
    def __init__(self, lista='lista_ves', pantalla='p2p', moneda='VES', monto=None, pago=None, tab='vender',
                 frente='binance', embudo_falla=1, descarta_primera=True, llaves=None, orden_monto='5000',
                 recuerda_metodo=False, precio_cambia=False, cortina_terca=False, reinicio_desconocido=False):
        self.lista = lista
        self.apodo, self.orden_xml, self.orden_rid_txt = LISTAS[lista]
        self.s = dict(pantalla=pantalla, moneda=moneda, monto=monto, pago=pago, tab=tab, frente=frente,
                      embudo_falla=embudo_falla, descarta=descarta_primera, campo='', foco=False,
                      orden_monto=orden_monto, tocado_apodo=None,
                      aplicadas=dict(llaves or DE_FABRICA), panel={}, vista='arriba',
                      recuerda=recuerda_metodo, panel_metodo=None, casilla=False,
                      precio_cambia=precio_cambia, refrescado=False, cortina_terca=cortina_terca,
                      reinicio_desconocido=reinicio_desconocido, reinicios=0)
        self.malos = []

    def xml(self):
        s = self.s
        p = s['pantalla']
        if p == 'p2p':
            x = cambiar(X[self.lista], 'VES', '2131446692', s['moneda'])
            x = cambiar(x, '5,000', 'tv_amount', '{:,.0f}'.format(s['monto']) if s['monto'] else 'Monto')
            x = cambiar(x, 'Pago Movil', '2131452724', s['pago'] or 'Pago')   # el método aplicado
            if s['tab'] == 'comprar':
                x = x.replace('text="Vender" resource-id="com.binance.dev:id/2131452588"',
                              'text="Comprar" resource-id="com.binance.dev:id/2131452588"')
            return x
        if p == 'ars_comprar':
            return X['lista_ars_comprar']
        if p == 'monto':
            return cambiar(X['quiero_vender'], 'Ingresa el monto total', '2131432439',
                           s['campo'] or 'Ingresa el monto total')
        if p == 'filtrar':
            if s['vista'] == 'metodos':   # bajado hasta "Método de Pago" (16:34): el xml no dice cuál, solo cuántos
                return X['filtrar_metodos_elegido' if s['panel_metodo'] else 'filtrar_metodos']
            if s['foco']:                 # con el teclado el panel se desplaza (grabación 03)
                return cambiar(X['03'], '5000', '2131432527', s['campo'] or 'Ingresa el monto total')
            x = X['filtrar']
            for rid, on in s['panel'].items():
                x = llave(x, rid, on)
            if s['campo']:
                x = cambiar(x, 'Ingresa el monto total', '2131432527', s['campo'])
            return x
        if p == 'orden':
            x = cambiar(X[self.orden_xml], self.orden_rid_txt, '2131432247',
                        s['campo'] if s['foco'] else s['orden_monto'])
            return llave(x, '2131430132', s['casilla'])      # la casilla de términos
        if p == 'precio_dialogo':
            return X['precio_actualizado']
        if p == 'divisa':
            return X['01']
        if p == 'activo':
            return X['seleccionar_activo']
        if p == 'inicio':
            return ''
        return NO_GRABADA

    def nodo_en(self, x, y):
        mejor = None
        for n in ET.fromstring(self.xml().encode()).iter('node'):
            bb = [int(v) for v in re.findall(r'\d+', n.get('bounds') or '')]
            if len(bb) == 4 and bb[0] <= x <= bb[2] and bb[1] <= y <= bb[3] and \
                    ((n.get('text') or '').strip() or (n.get('class') or '').split('.')[-1] in ('EditText', 'Switch')
                     or n.get('clickable') == 'true'):
                area = ((bb[2] - bb[0]) * (bb[3] - bb[1]), 0 if (n.get('text') or '').strip() else 1)
                if mejor is None or area < mejor[0]:   # el más chico; si empatan, el que tiene texto
                    mejor = (area, n.get('text') or '', bb, (n.get('class') or '').split('.')[-1])
        return mejor

    def tap(self, x, y):
        s = self.s
        p = s['pantalla']
        if p == 'inicio':
            if abs(x - 1080 * b.BOTON_P2P[0]) < 60 and abs(y - 2400 * b.BOTON_P2P[1]) < 60:
                s['pantalla'] = 'p2p'
            return
        n = self.nodo_en(x, y)
        t, clase = (n[1], n[3]) if n else ('', '')
        if p == 'orden' and clase == 'CheckBox':
            s['casilla'] = not s['casilla']
            s['toques_casilla'] = s.get('toques_casilla', 0) + 1
        elif p == 'orden' and (b.PROHIBIDO.search(b.norm(t)) or y > 2130):     # Realizar Orden, "Haz clic…"
            self.malos.append('tocó "%s" en la orden' % (t or clase))
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
                    s['pantalla'], s['campo'], s['foco'], s['vista'] = 'filtrar', '', False, 'arriba'
                    s['panel'] = dict(s['aplicadas'])
                    s['panel_metodo'] = s['pago'] if s['recuerda'] else None   # 16:34: reabre en "Todo"
                    if s['monto']:
                        s['campo'] = fmt(s['monto'])
            elif n and 330 < y < 480 and 267 <= x <= 357:
                s['pantalla'], s['campo'], s['foco'] = 'monto', '', False
            elif n and 330 < y < 480 and 427 <= x <= 616:
                s['pantalla'] = 'metodos'                        # NO grabada
                self.malos.append('tocó el chip de método')
            elif t in ('Vender', 'Comprar') and y > 480:
                if s['tab'] != 'vender':
                    self.malos.append('tocó la tarjeta estando en Comprar')
                if s['pago'] != 'Pago Movil':
                    self.malos.append('entró al anuncio con el método en %r' % s['pago'])
                if any(s['aplicadas'].values()):
                    self.malos.append('entró al anuncio con interruptores prendidos: %s' % s['aplicadas'])
                if not (s['monto'] and s['moneda'] == 'VES'):
                    self.malos.append('entró al anuncio sin monto o sin VES')
                s['tocado_apodo'] = self.apodo if y < 900 else 'otro'
                s['pantalla'], s['foco'] = 'orden', False
                if s['precio_cambia'] is True:    # 17:46: el anunciante cambió el precio (una vez)
                    s['precio_cambia'] = 'mostrado'
                    s['pantalla'] = 'precio_dialogo'
                elif s['precio_cambia'] == 'mostrado' and not s['refrescado']:
                    self.malos.append('volvió a entrar sin refrescar la lista')
        elif p == 'precio_dialogo':
            if t == 'Entendido':
                s['pantalla'] = 'orden'
            else:
                self.malos.append('tocó "%s" en el cartel de precio' % t)
        elif p == 'divisa':
            if t in ('VES', 'UYU', 'COP', 'AZN', 'USD', 'ARS'):
                s['moneda'], s['pantalla'] = t, 'p2p'
        elif p == 'filtrar':
            if s['vista'] == 'metodos' and t in METODOS_PANEL:
                s['panel_metodo'] = None if s['panel_metodo'] == t else t
            elif s['vista'] == 'metodos' and t == 'Todo' and 900 < y < 1400:
                s['panel_metodo'] = None
            elif clase == 'Switch':
                rid = [r for r, (y1, y2) in LLAVES.items() if y1 <= y <= y2]
                if rid:
                    s['panel'][rid[0]] = not s['panel'][rid[0]]
                else:
                    self.malos.append('tocó otro interruptor del panel (y=%d)' % y)
            elif clase == 'EditText':
                s['foco'] = True
            elif t == 'Confirmar':
                if s['descarta']:
                    s['descarta'] = False                        # la primera vez la app descarta el filtro
                else:
                    s['monto'] = b.numero(s['campo']) or s['monto']
                    s['aplicadas'] = dict(s['panel'])
                    s['pago'] = s['panel_metodo']
                s['pantalla'], s['foco'] = 'p2p', False
        elif p == 'monto':
            if clase == 'EditText':
                s['foco'] = True
            elif t == 'Confirmar':
                s['monto'] = b.numero(s['campo'])
                s['pantalla'], s['foco'] = 'p2p', False
        elif p == 'orden':
            if clase == 'EditText':
                s['foco'], s['campo'] = True, s['orden_monto']

    def key(self, k):
        s = self.s
        if k == 'KEYCODE_DEL' and s['foco']:
            s['campo'] = s['campo'][:-1]
        elif k == 'KEYCODE_BACK' and s['frente'] == 'cortina':
            s['frente'] = 'termux'                # Atrás con la cortina abierta: solo la cierra
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
            for k in a[3:]:                       # input keyevent acepta varias teclas seguidas
                self.key(k)
        elif a[:3] == ('shell', 'input', 'swipe') and s['pantalla'] == 'filtrar':
            s['vista'], s['foco'] = 'metodos', False
        elif a[:3] == ('shell', 'input', 'swipe') and s['pantalla'] == 'p2p' and int(a[4]) < int(a[6]):
            s['refrescado'] = True                # arrastre hacia abajo: refresca la lista
        elif a[:3] == ('shell', 'dumpsys', 'window'):
            return {'binance': 'mCurrentFocus=Window{1 u0 com.binance.dev/x}',
                    'cortina': 'mCurrentFocus=Window{88b51fd u0 NotificationShade}',
                    'termux': 'mCurrentFocus=Window{2 u0 com.termux/x}'}[s['frente']]
        elif a[:4] == ('shell', 'cmd', 'statusbar', 'collapse'):
            if s['frente'] == 'cortina' and not s['cortina_terca']:
                s['frente'] = 'termux'
        elif a[:3] == ('shell', 'am', 'force-stop'):
            s['frente'], s['reinicios'] = 'termux', s['reinicios'] + 1
            s['pantalla'] = 'libro' if s['reinicio_desconocido'] else 'inicio'
        elif a[:3] == ('shell', 'am', 'start') or a[:2] == ('shell', 'monkey'):
            if s['frente'] == 'termux':
                s['frente'] = 'binance'
        elif a[:3] == ('shell', 'pm', 'list'):
            return 'package:com.binance.dev'
        return ''


def fmt(m):
    return b.fmt_monto(m)


def preparar(t):
    b.adb = t.adb
    b.time.sleep = lambda s: None
    b.tamano_pantalla = lambda: (1080, 2400)
    b.guardar = lambda n: 'binance_%s' % n
    b.EN_ORDEN = False
    b.PAQ = ''
    b.paquete_binance()


def correr(nombre, espera, **kw):
    t = Telefono(**kw)
    preparar(t)
    print('==== %s' % nombre)
    try:
        ns = b.llegar_a_la_orden([{'apodo': t.apodo, 'precio': None, 'reserva': False}], METODO, 5000.0)
        res = 'orden %s %s %s' % b.completar_orden(ns, b.ELEGIDO['apodo'], METODO, 5000.0)
        if not t.s['casilla'] or t.s.get('toques_casilla') != 1:
            t.malos.append('la casilla quedó %s (%s toques)' % (t.s['casilla'], t.s.get('toques_casilla')))
        if t.s['tocado_apodo'] != t.apodo:
            t.malos.append('abrió la orden de otro')
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
    ('15:27: lista VES sin monto, filtro de fábrica, el embudo falla y descarta la 1ª vez', 'orden True True True', {}),
    ('lo mismo con la lista de la madrugada (PrincessYor)', 'orden True True True', dict(lista='04')),
    ('el embudo abre siempre y no descarta', 'orden True True True', dict(embudo_falla=0, descarta_primera=False)),
    ('interruptores ya apagados y monto puesto: igual pasa dos veces por el embudo', 'orden True True True',
     dict(monto=5000, pago='Pago Movil', llaves={r: False for r in LLAVES})),
    ('"Pro" prendido además de los otros', 'orden True True True',
     dict(llaves={'2131444437': True, '2131444418': True, '2131444409': True})),
    ('el embudo no abre nunca', 'no avanza', dict(embudo_falla=99)),
    ('moneda ARS y pestaña Comprar', 'orden True True True', dict(moneda='ARS', tab='comprar')),
    ('la lista venía con Banesco (el panel lo olvida): elige Pago Movil', 'orden True True True', dict(pago='Banesco')),
    ('el panel recuerda Pago Movil: no lo toca (si lo tocara, lo desmarcaría)', 'orden True True True',
     dict(pago='Pago Movil', recuerda_metodo=True, descarta_primera=False)),
    ('el panel recuerda Banesco: se frena y pide dejarlo en Todo', 'dejalo en Todo',
     dict(pago='Banesco', recuerda_metodo=True)),
    ('quedó abierto "Seleccionar activo" (como 02:08)', 'orden True True True', dict(pantalla='activo')),
    ('quedó abierta la hoja "Quiero vender" (como 02:13)', 'orden True True True', dict(pantalla='monto')),
    ('Binance cerrado y cortina abierta (como 02:03), inicio animado', 'orden True True True',
     dict(frente='cortina', pantalla='inicio')),
    ('la orden trae otro monto: lo corrige', 'orden True True True', dict(orden_monto='1234')),
    ('el precio cambió al abrir la orden: Entendido, atrás, refrescar y de nuevo', 'orden True True True',
     dict(precio_cambia=True)),
    ('cortina terca (collapse no anda, como 17:27): la cierra con Atrás', 'orden True True True',
     dict(frente='cortina', cortina_terca=True)),
    ('Binance en el libro de órdenes (pantalla no grabada): lo reinicia', 'orden True True True',
     dict(pantalla='libro')),
    ('después de reiniciar sigue sin conocer la pantalla: se frena (no reinicia en bucle)', 'Pantalla que no conozco',
     dict(pantalla='libro', reinicio_desconocido=True)),
    ('quedó abierta una orden vieja', 'orden True True True', dict(pantalla='orden')),
]
bien = sum(correr(*c[:2], **c[2]) for c in casos)

print('==== que_es() con todas las pantallas grabadas')
esperado = {'01': 'divisa', '03': 'filtrar', '04': 'p2p', '05': 'orden', 'quiero_vender': 'monto',
            'seleccionar_activo': 'activo', 'lista_ars_comprar': 'p2p', 'filtrar': 'filtrar', 'lista_ves': 'p2p',
            'orden_wen2': 'orden', 'filtrar_metodos': 'filtrar', 'filtrar_metodos_elegido': 'filtrar',
            'filtrar_reabierto': 'filtrar', 'precio_actualizado': 'precio cambiado'}
b.PAQ = 'com.binance.dev'
mal_que_es = [(k, b.que_es(b.leer_nodos(X[k][X[k].find('<?xml'):]))) for k in esperado]
mal_que_es = [(k, q) for k, q in mal_que_es if q != esperado[k]]
print('  ' + ('BIEN' if not mal_que_es else 'MAL: %s' % mal_que_es))

print('==== --buscar / --prueba: búsqueda con una respuesta con la forma de Binance (campos de vps/relay_binance.py)')
import io  # noqa: E402
import json  # noqa: E402


def falso_urlopen(req, timeout=15):
    cuerpo = json.loads(req.data)
    assert cuerpo['tradeType'] == 'SELL' and cuerpo['payTypes'] == ['PagoMovil'] and str(cuerpo['transAmount']) == '5000'
    ads = [('1', 'Caro', '10000', '50000', ['PagoMovil']),        # el monto no entra
           ('2', 'wen2', '300', '81600', ['Banesco', 'PagoMovil']),
           ('3', 'Otro', '1000', '9000', ['PagoMovil'])]
    return io.BytesIO(json.dumps({'data': [{'adv': {'advNo': n, 'price': '1068', 'minSingleTransAmount': mn,
                                                    'dynamicMaxSingleTransAmount': mx,
                                                    'tradeMethods': [{'identifier': m} for m in ms]},
                                            'advertiser': {'nickName': ap}} for n, ap, mn, mx, ms in ads]}).encode())


b.urllib.request.urlopen = falso_urlopen
r = b.buscar_anuncios(5000.0, 'PagoMovil')
ok_busca = [a['apodo'] for a in r] == ['wen2', 'Otro']
print('  %s: %s' % ('BIEN' if ok_busca else 'MAL', [a['apodo'] for a in r]))
if not ok_busca:
    bien -= 1

print('==== el apodo no está en la lista')
t = Telefono()
preparar(t)
try:
    b.llegar_a_la_orden([{'apodo': 'NoExiste', 'precio': None, 'reserva': False}], METODO, 5000.0)
    print('  MAL: no se frenó')
    bien -= 1
except b.Frenado as e:
    print('  BIEN: %s' % e)
print('==== el apodo no está y la lista ya pasó su precio (como 16:42): se frena en la primera pantalla')
t = Telefono(monto=5000, pago='Pago Movil', llaves={r: False for r in LLAVES}, embudo_falla=0, descarta_primera=False)
preparar(t)
try:
    b.llegar_a_la_orden([{'apodo': 'NoExiste', 'precio': 1080.0, 'reserva': False}], METODO, 5000.0)
    print('  MAL: no se frenó')
    bien -= 1
except b.Frenado as e:
    ok_precio = 'Pasé el precio' in str(e)
    print('  %s: %s' % ('BIEN' if ok_precio else 'MAL', e))
    if not ok_precio:
        bien -= 1
print('==== orden con un método que no es el tuyo: no toca la casilla')
t = Telefono(pantalla='orden')
preparar(t)
b.EN_ORDEN = True
ns = b.leer_nodos(t.xml()[t.xml().find('<?xml'):])
r = b.completar_orden(ns, 'wen2', {'id': 'Banesco', 'nombre': 'Banesco'}, 5000.0)
ok_cas = r == (True, False, False) and not t.s['casilla'] and not t.malos
print('  %s: %s · casilla=%s' % ('BIEN' if ok_cas else 'MAL', r, t.s['casilla']))
if not ok_cas:
    bien -= 1

print('==== reservas (lista grabada con wen2 a 1068)')


def reserva(nombre, cands, espera_apodo, espera_alerta=None):
    t = Telefono(monto=5000, pago='Pago Movil', llaves={r: False for r in LLAVES}, embudo_falla=0,
                 descarta_primera=False)
    preparar(t)
    b.ELEGIDO = None
    try:
        b.llegar_a_la_orden(cands, METODO, 5000.0)
        el = b.ELEGIDO['apodo']
        texto, alerta = b.resumen(cands[0], b.ELEGIDO, 5000.0, METODO, [], 'x')
    except b.Frenado as e:
        el, texto, alerta = None, 'frenado: %s' % e, None
    ok = el == espera_apodo and (espera_alerta is None or alerta == espera_alerta) and not t.malos
    print('  %s %s -> %s · alerta=%s · %s' % ('BIEN' if ok else 'MAL', nombre, el, alerta, texto[:150]))
    return ok


c = lambda ap, pr, res=False: {'apodo': ap, 'precio': pr, 'reserva': res}
ok_res = all([
    reserva('el elegido no está, reserva -0,2 %', [c('Ataraxia0104', 1070.105), c('wen2', 1068.0, True)], 'wen2', False),
    reserva('el elegido no está, reserva -2 %: avisa', [c('Caro', 1090.0), c('wen2', 1068.0, True)], 'wen2', True),
    reserva('el elegido sí está', [c('wen2', 1068.0), c('keka26', 1066.7, True)], 'wen2', False),
    reserva('reserva visible pero el elegido podría estar más abajo: sigue y no la toma',
            [c('Barato', 1000.0), c('wen2', 1068.0, True)], None),
])
if not ok_res:
    bien -= 1

print('==== aviso con el precio de la orden (puede haber cambiado)')
pr = {'apodo': 'uno', 'precio': 1070.0}
t1, a1 = b.resumen(pr, {'apodo': 'uno', 'precio': 1070.0, 'precio_orden': 1055.0, 'reserva': False}, 5000.0, METODO, [], 'x')
t2, a2 = b.resumen(pr, {'apodo': 'uno', 'precio': 1070.0, 'precio_orden': 1068.0, 'reserva': False}, 5000.0, METODO, [], 'x')
ok_pr = a1 and 'bajó 1.4%' in t1 and not a2
print('  %s: bajó 1,4 %% -> alerta=%s · bajó 0,2 %% -> alerta=%s' % ('BIEN' if ok_pr else 'MAL', a1, a2))
if not ok_pr:
    bien -= 1

print('==== armar_candidatos: el anuncio ya no existe en Binance, la reserva sí')
DET = {'1': None, '2': {'apodo': 'wen2', 'precio': 1068.0, 'min': 300.0, 'max': 81600.0,
                        'metodos': [{'id': 'PagoMovil', 'nombre': 'Pago Movil'}]},
       '3': {'apodo': 'chico', 'precio': 1067.0, 'min': 6000.0, 'max': 9000.0,
             'metodos': [{'id': 'PagoMovil', 'nombre': 'Pago Movil'}]}}


def det_falso(ad):
    if DET[ad] is None:
        raise b.Frenado('Binance no devolvió el anuncio %s: puede que ya no exista' % ad)
    return DET[ad]


b.detalle_anuncio = det_falso
ad, monto, pago, alts = b.leer_link('https://c2c.binance.com/es-LA/adv?code=1&monto=5000&pago=PagoMovil&alt=2,3')
cands, met, princ = b.armar_candidatos(ad, alts, monto, pago)
texto, alerta = b.resumen(princ, dict(cands[0]), 5000.0, met, [], 'x')
ok_arm = [x['apodo'] for x in cands] == ['wen2'] and cands[0]['reserva'] and met['nombre'] == 'Pago Movil' and \
    alerta and 'no estaba el anuncio 1' in texto
print('  %s: %s · alerta=%s · %s' % ('BIEN' if ok_arm else 'MAL', [(x['apodo'], x['reserva']) for x in cands], alerta,
                                     texto[:110]))
if not ok_arm:
    bien -= 1
print('\n%d de %d casos bien%s' % (bien, len(casos), '' if not mal_que_es else ' · que_es MAL'))
sys.exit(0 if bien == len(casos) and not mal_que_es else 1)
