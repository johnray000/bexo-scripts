#!/usr/bin/env python3
"""Pago móvil (Tpago) desde Mercantil Móvil Personas, por ADB, hasta "Verifica tu operación". El resto es tuyo.

  python ~/bexo-scripts/mercantil_pago.py --telefono 04141234567 --cedula 12345678 --banco 0102 --monto 5000

Qué hace (pantallas grabadas el 27/11, grabaciones mercantil y mercantil2):
  1. Abre Mercantil, toca "Identificación biométrica" y espera tu huella (no la reemplaza).
  2. Abre "Cuentas" en el Resumen financiero y lee el saldo de cada Cuenta Corriente.
  3. Elige la cuenta con más saldo; si ninguna alcanza para el monto, se frena y avisa.
  4. Tpago → Enviar Tpago: monto, teléfono, cédula, banco destino y la cuenta elegida. Cada campo se relee:
     si no quedó como debe, se frena.
  5. Toca el botón para seguir y revisa "Verifica tu operación" (monto, teléfono, cédula, banco, cuenta).
  6. Te avisa "tocá Aceptar y poné tu huella". NUNCA toca Aceptar. Espera el "¡Listo!" y avisa la referencia.
Si algo no coincide con lo grabado, se frena y guarda la pantalla en Descargas (mercantil_*.xml/.png).
"""
import argparse
import os
import re
import sys
import time
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PAQUETE = 'com.mercantilbanco.mercantilmovil'
ESPERA_HUELLA_S = 120
ESPERA_LISTO_S = 240
PAUSA = 1.5


class Frenado(Exception):
    pass


# ---------- lo que toca el teléfono (la simulación reemplaza esto) ----------
class Telefono:
    def __init__(self):
        import binance_orden as b
        self.b = b
        b.PAQ = None                      # la huella la dibuja el sistema, no la app

    def pantalla(self):
        return self.b.leer_nodos(self.b.volcar(15, 2))

    def tocar(self, x, y):
        self.b.adb('shell', 'input', 'tap', str(x), str(y))

    def escribir(self, texto):
        self.b.adb('shell', 'input', 'text', texto)

    def borrar(self, n=14):
        self.b.adb('shell', 'input', 'keyevent', *(['67'] * n))

    def bajar(self):
        self.b.adb('shell', 'input', 'swipe', '540', '1800', '540', '900', '400')

    def ocultar_teclado(self):
        if 'mInputShown=true' in self.b.adb('shell', 'dumpsys', 'input_method'):
            self.b.adb('shell', 'input', 'keyevent', '111')   # ESC: cierra el teclado sin volver atrás

    def abrir(self):
        if not self.b.conectar():
            raise Frenado('No hay ADB: reconectá (notificación RECONECTAR)')
        self.b.adb('shell', 'cmd', 'statusbar', 'collapse')
        self.b.adb('shell', 'monkey', '-p', PAQUETE, '-c', 'android.intent.category.LAUNCHER', '1')

    def guardar(self, nombre):
        base = 'mercantil_%s_%s' % (nombre, time.strftime('%H%M%S'))
        self.b.adb('shell', 'screencap', '-p', '/sdcard/Download/%s.png' % base)
        with open(os.path.join(self.b.LOG_DIR, base + '.xml'), 'w') as f:
            f.write(self.b.volcar(15, 1))
        return base

    def avisar(self, titulo, texto, prioridad=3):
        self.b.avisar(titulo, texto, prioridad)

    def esperar(self, s):
        time.sleep(s)


T = None   # el teléfono en uso


# ---------- ayudas ----------
def compacto(t):
    t = unicodedata.normalize('NFD', (t or '').lower())
    return re.sub(r'\s+', ' ', ''.join(c for c in t if unicodedata.category(c) != 'Mn')).strip()


def bs(texto):
    """'Bs. 5.000,00' / '12.345,67' → 5000.0 (None si no hay número)."""
    m = re.search(r'(\d{1,3}(?:\.\d{3})*|\d+),(\d{2})', texto or '')
    return float(m.group(1).replace('.', '') + '.' + m.group(2)) if m else None


def digitos(t):
    return re.sub(r'\D', '', t or '')


def hay(ns, *textos):
    c = [compacto(x) for x in textos]
    return any(compacto(n.t) in c for n in ns)


def nodo(ns, texto, empieza=False):
    c = compacto(texto)
    for n in ns:
        if compacto(n.t) == c or (empieza and compacto(n.t).startswith(c)):
            return n
    return None


def frenar(motivo, nombre='fallo'):
    base = T.guardar(nombre)
    raise Frenado('%s. Pantalla en Descargas/%s' % (motivo, base))


def esperar_pantalla(cond, segundos, cada=1.5):
    fin = time.time() + segundos
    while True:
        ns = T.pantalla()
        if cond(ns):
            return ns
        if time.time() > fin:
            return None
        T.esperar(cada)


# ---------- pasos ----------
def entrar():
    """Login con la huella. Grabación: '¡Hola, …! | Clave de Internet | Identificación biométrica | Ingresar'."""
    T.abrir()
    T.avisar('Mercantil', 'Poné tu huella en Mercantil. Después no toques la pantalla.')
    ultimo = 0
    fin = time.time() + ESPERA_HUELLA_S
    while time.time() < fin:
        ns = T.pantalla()
        if hay(ns, 'Resumen financiero'):
            return ns
        bio = nodo(ns, 'Identificación biométrica')
        if bio and not hay(ns, 'Toca el sensor de huellas digitales') and time.time() - ultimo > 20:
            T.tocar(bio.x, bio.y)            # abre el cartel de la huella (tocar seguido lo cancela)
            ultimo = time.time()
        T.esperar(2)
    frenar('No llegué al Resumen financiero en %d s (¿huella?)' % ESPERA_HUELLA_S, 'huella')


def leer_saldos(ns):
    """Abre 'Cuentas' y lee 'Cuenta Corriente *1111 | 6.000,00' (misma fila). {'*1111': 6000.0, ...}"""
    if not any(n.t.startswith('Cuenta Corriente *') for n in ns):
        c = nodo(ns, 'Cuentas')
        if not c:
            frenar('No encontré "Cuentas" en el Resumen financiero', 'resumen')
        T.tocar(c.x, c.y)
        ns = esperar_pantalla(lambda v: any(n.t.startswith('Cuenta Corriente *') for n in v), 15)
        if not ns:
            frenar('Toqué "Cuentas" y no aparecieron las cuentas', 'resumen')
    saldos = {}
    for n in ns:
        m = re.match(r'Cuenta Corriente (\*\d{4})$', n.t.strip())
        if m:
            fila = [o for o in ns if abs(o.y - n.y) < 40 and o.x > n.x and bs(o.t) is not None]
            if fila:
                saldos[m.group(1)] = bs(fila[0].t)
    if not saldos:
        frenar('No pude leer el saldo de las cuentas', 'resumen')
    return saldos, ns


def elegir_cuenta(saldos, monto):
    mejor = max(saldos, key=lambda k: saldos[k])
    if saldos[mejor] < monto:
        raise Frenado('Ninguna cuenta alcanza para Bs %s (%s)' % (fmt(monto), ', '.join(
            '%s Bs %s' % (k, fmt(v)) for k, v in saldos.items())))
    return mejor


def fmt(v):
    e, d = ('%.2f' % v).split('.')
    return '{:,}'.format(int(e)).replace(',', '.') + ',' + d


def abrir_formulario(ns):
    # La pestaña Tpago es un ícono sin texto a la derecha de "Recargas" (grabación: Resumen x=114, Transferencias
    # x=341, Recargas x=741, ícono Tpago x=969, 50 px más arriba que los rótulos). Después se comprueba el menú.
    res, tra, rec = nodo(ns, 'Resumen'), nodo(ns, 'Transferencias'), nodo(ns, 'Recargas')
    if not (res and tra and rec):
        frenar('No encontré la barra de abajo (Resumen, Transferencias, Recargas)', 'resumen')
    T.tocar(rec.x + (tra.x - res.x), rec.y - 50)
    ns = esperar_pantalla(lambda v: hay(v, 'Enviar Tpago') and hay(v, 'Tpago compartido'), 15)
    if not ns:
        frenar('No abrió el menú de Tpago', 'tpago')
    e = nodo(ns, 'Enviar Tpago')
    T.tocar(e.x, e.y)
    ns = esperar_pantalla(lambda v: hay(v, 'Ingresa los datos'), 15)
    if not ns:
        frenar('No abrió "Enviar Tpago"', 'tpago')
    return ns


def campo(ns, debajo_de):
    """El EditText que está debajo del rótulo (Teléfono celular:, Documento de identidad:)."""
    r = nodo(ns, debajo_de)
    if not r:
        return None
    cand = [n for n in ns if n.clase == 'EditText' and 0 < n.y - r.y < 220]
    return min(cand, key=lambda n: n.y - r.y) if cand else None


def poner_monto(ns, monto):
    """El campo 'Enviar Bs.' (0,00). Se escribe en pesos enteros y se relee; si la app lo toma en céntimos, se reescribe."""
    rot = nodo(ns, 'Enviar Bs.')
    m = [n for n in ns if n.clase == 'EditText' and rot and 0 < n.y - rot.y < 220]
    if not m:
        frenar('No encontré el campo del monto', 'formulario')
    for texto in ('%d' % round(monto), '%d' % round(monto * 100)):
        T.tocar(m[0].x, m[0].y)
        T.borrar()
        T.escribir(texto)
        T.esperar(PAUSA)
        ns = T.pantalla()
        rot = nodo(ns, 'Enviar Bs.')
        m = [n for n in ns if n.clase == 'EditText' and rot and 0 < n.y - rot.y < 220]
        if m and bs(m[0].t) is not None and abs(bs(m[0].t) - monto) < 0.01:
            T.ocultar_teclado()
            return T.pantalla()
    frenar('El monto quedó "%s" y no Bs %s' % (m[0].t if m else '?', fmt(monto)), 'monto')


def poner_texto(ns, rotulo, valor, que):
    c = campo(ns, rotulo)
    if not c:
        T.bajar()
        ns = T.pantalla()
        c = campo(ns, rotulo)
    if not c:
        frenar('No encontré el campo %s' % que, 'formulario')
    T.tocar(c.x, c.y)
    T.borrar(16)
    T.escribir(valor)
    T.esperar(PAUSA)
    ns = T.pantalla()
    c = campo(ns, rotulo)
    if not c or digitos(c.t) != digitos(valor):
        frenar('El %s quedó "%s" y no %s' % (que, c.t if c else '?', valor), que.replace(' ', '_'))
    T.ocultar_teclado()
    return T.pantalla()


def elegir_de_lista(ns, rotulo, empieza, que):
    """Toca el valor debajo del rótulo (Banco destino:, Desde mi cuenta:), busca en la lista una fila que empiece con
    `empieza` y la toca. Después relee el valor. Si la lista no tiene la fila (o no se abrió), se frena."""
    for _ in range(2):
        r = nodo(ns, rotulo)
        if r:
            break
        T.bajar()
        ns = T.pantalla()
    if not r:
        frenar('No encontré "%s"' % rotulo, 'formulario')
    valor = [n for n in ns if 0 < n.y - r.y < 250 and n.clase != 'EditText' and n.t]
    if valor and compacto(valor[0].t).startswith(compacto(empieza)):
        return ns                                            # ya estaba
    if not valor:
        frenar('No encontré el valor de "%s"' % rotulo, 'formulario')
    T.tocar(valor[0].x, valor[0].y)
    T.esperar(PAUSA)
    lista = T.pantalla()
    fila = [n for n in lista if compacto(n.t).startswith(compacto(empieza)) and abs(n.y - valor[0].y) > 30]
    if not fila and nodo(lista, 'Buscar...'):
        b = nodo(lista, 'Buscar...')
        T.tocar(b.x, b.y)
        T.escribir(empieza.split()[0])
        T.esperar(PAUSA)
        lista = T.pantalla()
        fila = [n for n in lista if compacto(n.t).startswith(compacto(empieza)) and n.clase != 'EditText']
    if not fila:
        frenar('En la lista de %s no está "%s"' % (que, empieza), que)
    T.tocar(fila[0].x, fila[0].y)
    T.esperar(PAUSA)
    ns = T.pantalla()
    r = nodo(ns, rotulo)
    valor = [n for n in ns if r and 0 < n.y - r.y < 250 and n.clase != 'EditText' and n.t]
    if not valor or not compacto(valor[0].t).startswith(compacto(empieza)):
        frenar('Elegí %s y no quedó "%s"' % (que, empieza), que)
    return ns


BOTONES_SEGUIR = ('Continuar', 'Siguiente', 'Enviar', 'Aceptar')


def seguir(ns):
    """El botón al final del formulario (no está en las grabaciones: se busca por texto, bajando)."""
    for _ in range(3):
        if hay(ns, 'Verifica tu operación'):   # seguro: en Verifica nunca se toca un botón (Aceptar es tuyo)
            return ns
        b = [n for n in ns if n.clase == 'Button' and compacto(n.t) in [compacto(x) for x in BOTONES_SEGUIR]]
        if b:
            T.tocar(b[0].x, b[0].y)
            v = esperar_pantalla(lambda x: hay(x, 'Verifica tu operación'), 20)
            if v:
                return v
            frenar('Toqué "%s" y no apareció "Verifica tu operación"' % b[0].t, 'seguir')
        T.bajar()
        ns = T.pantalla()
    frenar('No encontré el botón para seguir al final del formulario', 'boton')


def revisar(ns, monto, telefono, cedula, banco, cuenta):
    """'¿Enviar | Bs. 5.000,00 | a 0414-1234567? | Cuenta a debitar: | Cta. Corriente - *2222 | … V-12.345.678 | 0102 - …'"""
    txt = ' | '.join(n.t for n in ns)
    fallas = []
    if not any(bs(n.t) is not None and abs(bs(n.t) - monto) < 0.01 and 'Bs' in n.t for n in ns):
        fallas.append('monto')
    if digitos(telefono) not in digitos(txt):
        fallas.append('teléfono')
    if not any(digitos(n.t) == digitos(cedula) for n in ns):
        fallas.append('cédula')
    if not any(n.t.strip().startswith(banco + ' -') for n in ns):
        fallas.append('banco')
    if cuenta not in txt:
        fallas.append('cuenta')
    return fallas


def esperar_listo():
    ns = esperar_pantalla(lambda v: any('Tu Tpago fue exitoso' in n.t for n in v), ESPERA_LISTO_S, 3)
    if not ns:
        return None
    ref = [n for n in ns if compacto(n.t) == compacto('Nro. de referencia:')]
    if ref:
        abajo = [n for n in ns if 0 < n.y - ref[0].y < 80 and digitos(n.t)]
        return abajo[0].t if abajo else ''
    return ''


def pagar(telefono, cedula, banco, monto, tel=None):
    global T
    T = tel or Telefono()
    telefono, cedula, banco = digitos(telefono), digitos(cedula), digitos(banco)[:4]
    if len(telefono) != 11 or not telefono.startswith('04') or not cedula or len(banco) != 4 or monto <= 0:
        raise Frenado('Datos inválidos: teléfono %s, cédula %s, banco %s, monto %s' % (telefono, cedula, banco, monto))
    ns = entrar()
    saldos, ns = leer_saldos(ns)
    cuenta = elegir_cuenta(saldos, monto)
    ns = abrir_formulario(ns)
    ns = poner_monto(ns, monto)
    ns = poner_texto(ns, 'Teléfono celular:', telefono, 'teléfono')
    ns = poner_texto(ns, 'Documento de identidad:', cedula, 'cédula')
    ns = elegir_de_lista(ns, 'Banco destino:', banco + ' -', 'banco')
    ns = elegir_de_lista(ns, 'Desde mi cuenta:', 'Cta. Corriente ' + cuenta, 'cuenta')
    ns = seguir(ns)
    fallas = revisar(ns, monto, telefono, cedula, banco, cuenta)
    if fallas:
        frenar('En "Verifica tu operación" no coincide: %s. NO toques Aceptar' % ', '.join(fallas), 'verifica')
    T.avisar('Mercantil: revisado ✅ · tocá Aceptar y poné tu huella',
             'Bs %s a %s (%s) desde %s' % (fmt(monto), telefono, banco, cuenta), 5)
    ref = esperar_listo()
    if ref is None:
        T.avisar('Mercantil: no vi el "¡Listo!"', 'Pasaron %d s. Revisá en la app si salió.' % ESPERA_LISTO_S, 4)
        return 'sin listo'
    T.avisar('Mercantil: pago hecho ✅', 'Bs %s a %s · ref %s · desde %s' % (fmt(monto), telefono, ref, cuenta), 4)
    return 'ok ' + ref


def main():
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--telefono', required=True)
    p.add_argument('--cedula', required=True)
    p.add_argument('--banco', required=True, help='código de 4 dígitos, p. ej. 0102')
    p.add_argument('--monto', required=True, type=float, help='en Bs, p. ej. 5000')
    a = p.parse_args()
    try:
        print(pagar(a.telefono, a.cedula, a.banco, a.monto))
    except Frenado as e:
        print('Frenado:', e)
        try:
            T.avisar('Mercantil: me frené ⚠️', str(e), 4)
        except Exception:  # noqa: BLE001
            pass
        sys.exit(1)


if __name__ == '__main__':
    main()
