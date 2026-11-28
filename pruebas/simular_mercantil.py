#!/usr/bin/env python3
"""Simula mercantil_pago.py sobre las pantallas grabadas el 27/11 (grabaciones mercantil y mercantil2).

  python3 pruebas/simular_mercantil.py <carpeta>   (login, huella, resumen, resumen_cuentas, tpago, form,
                                                   form_bajo_bancos, verifica, listo .xml)

Las grabaciones tienen saldos, cuentas y datos de clientes: NUNCA van al repo, y este archivo no tiene ningún valor
real escrito: ubica cada campo por su rótulo ("Teléfono celular:", "Desde mi cuenta:", "Monto (Bs.):"…) y usa
cuentas y datos inventados.
Inventado (no grabado, marcado INVENTADO): la lista de cuentas de "Desde mi cuenta" y el botón para seguir al final
del formulario. Por eso hay casos con y sin botón: si no está, el recorrido tiene que frenarse, no adivinar.
"""
import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
import binance_orden as b  # noqa: E402
import mercantil_pago as m  # noqa: E402

b.PAQ = None
CARPETA = sys.argv[1] if len(sys.argv) > 1 else '.'
X = {f[:-4]: b.leer_nodos(open(os.path.join(CARPETA, f)).read()) for f in os.listdir(CARPETA) if f.endswith('.xml')}
N = b.N
TEL, CED, BANCO, MONTO = '04141234567', '12345678', '0102', 5000.0          # inventados
CUENTAS = {'*1111': 3000.00, '*2222': 90000.00}                             # inventadas


def debajo(ns, rotulo, filtro=lambda n: True, dist=250):
    """El nodo más cercano debajo del rótulo."""
    r = [n for n in ns if n.t == rotulo]
    if not r:
        return None
    c = [n for n in ns if 0 < n.y - r[0].y < dist and filtro(n)]
    return min(c, key=lambda n: n.y - r[0].y) if c else None


def cambiar(ns, viejo, nuevo_t):
    return [n._replace(t=nuevo_t) if n is viejo else n for n in ns]


def renombrar_cuentas(ns, saldos):
    """Las 'Cuenta Corriente *dddd' grabadas pasan a las inventadas, con su saldo en la misma fila."""
    reales = [n for n in ns if re.match(r'^Cuenta Corriente \*\d{4}$', n.t)]
    for real, (k, v) in zip(reales, saldos.items()):
        fila = [o for o in ns if abs(o.y - real.y) < 40 and o.x > real.x and m.bs(o.t) is not None]
        ns = cambiar(ns, real, 'Cuenta Corriente ' + k)
        if fila:
            ns = cambiar(ns, fila[0], m.fmt(v))
    return ns


class Fake:
    def __init__(self, saldos=None, boton='Continuar', monto_pesos=False, huella_ok=True, john_acepta=True,
                 verifica_cambia=None, banco_en_lista=True, monto_inicial='0,00', borrar_anda=True):
        self.saldos = saldos or dict(CUENTAS)
        primera = list(self.saldos)[0]
        self.s = dict(p='cerrada', polls=0, monto=monto_inicial, tel='Ingresa un número de celular', ced='Número de documento',
                      banco='Selecciona el banco destino',
                      cuenta='Cta. Corriente %s - Bs. %s' % (primera, m.fmt(self.saldos[primera])),
                      bajo=False, lista=None, foco=None, avisos=[], toco_aceptar=False)
        # 28/11: el monto es tipo caja registradora (los 2 últimos dígitos son céntimos) y se agrega a lo que había
        self.boton, self.pesos, self.huella_ok, self.john = boton, monto_pesos, huella_ok, john_acepta
        self.borrar_anda = borrar_anda
        self.verifica_cambia, self.banco_en_lista = verifica_cambia, banco_en_lista
        self.ref = '999888777'

    def pantalla(self):
        s = self.s
        s['polls'] += 1
        p = s['p']
        if p in ('login', 'resumen', 'tpago'):
            return X[p]
        if p == 'huella':
            if self.huella_ok and s['polls'] > 2:
                s['p'] = 'resumen'
            return X['huella']
        if p == 'resumen_cuentas':
            return renombrar_cuentas(X['resumen_cuentas'], self.saldos)
        if p == 'form':
            return self.formulario()
        if p == 'verifica':
            ns = X['verifica']
            cuenta = s['cuenta'].split(' - ')[0].split()[-1]
            for patron, nuevo in ((r'^Bs\. ', 'Bs. ' + s['monto']), (r'^a 0\d{3}-\d{7}\?$', 'a %s?' % s['tel']),
                                  (r'^V-[\d.]+$', 'V-' + s['ced']), (r'^0\d{3} - ', s['banco'].rstrip('.')),
                                  (r'^Cta\. Corriente - \*', 'Cta. Corriente - ' + cuenta)):
                ns = [n._replace(t=nuevo) if re.match(patron, n.t) else n for n in ns]
            if self.verifica_cambia:
                ns = [n._replace(t=self.verifica_cambia[1]) if re.match(self.verifica_cambia[0], n.t) else n for n in ns]
            return ns
        if p == 'metodo':
            return X['metodo']
        if p == 'huella_pago':
            if self.john and s['polls'] > 3:          # vos ponés la huella
                s['p'] = 'listo'
            return X['huella']
        if p == 'listo':
            ns = X['listo']
            mo = debajo(ns, 'Monto (Bs.):', lambda n: m.bs(n.t) is not None, 80)
            ref = debajo(ns, 'Nro. de referencia:', lambda n: bool(m.digitos(n.t)), 80)
            ns = cambiar(ns, mo, s['monto']) if mo else ns
            return cambiar(ns, ref, self.ref) if ref else ns
        return []

    def formulario(self):
        s = self.s
        if s['lista'] == 'banco':
            lista = [n for n in X['form_bajo_bancos'] if n.t == 'Buscar...' or re.match(r'^0\d{3} - ', n.t)]
            if not self.banco_en_lista:
                lista = [n for n in lista if not n.t.startswith(BANCO)]
            return lista
        if s['lista'] == 'cuenta':                   # INVENTADO: como la lista de Transferencias (grabación 1)
            return [N('Cta. Corriente %s - Bs. %s' % (k, m.fmt(v)), 540, 1500 + i * 120, 'TextView', '', True, None)
                    for i, (k, v) in enumerate(self.saldos.items())]
        if not s['bajo']:
            ns = X['form']
            mo = debajo(ns, 'Enviar Bs.', lambda n: n.clase == 'EditText')
            ns = cambiar(ns, mo, s['monto'])
        else:                                        # formulario bajado, sin la lista de bancos encima
            ns = [n for n in X['form_bajo_bancos'] if not (n.t == 'Buscar...' or re.match(r'^0\d{3} - ', n.t))]
            if self.boton:                           # INVENTADO
                ns = ns + [N(self.boton, 540, 2150, 'Button', '', True, None)]
        if s['foco'] and not s['bajo']:              # 28/11: el teclado abierto tapa la mitad de abajo
            ns = [n for n in ns if n.y < 1560]
        for rot, clave, filtro in (('Teléfono celular:', 'tel', lambda n: n.clase == 'EditText'),
                                   ('Documento de identidad:', 'ced', lambda n: n.clase == 'EditText'),
                                   ('Banco destino:', 'banco', lambda n: n.clase != 'EditText' and n.t),
                                   ('Desde mi cuenta:', 'cuenta', lambda n: n.clase != 'EditText' and n.t)):
            n = debajo(ns, rot, filtro)
            if n:
                ns = cambiar(ns, n, s[clave])
        return ns

    def tocar(self, x, y):
        s = self.s
        ns = self.pantalla()
        s['polls'] -= 1
        hit = min(ns, key=lambda n: abs(n.x - x) + abs(n.y - y)) if ns else None
        t = hit.t if hit else ''
        if s['p'] == 'login' and 896 <= x <= 1026 and 986 <= y <= 1116:     # el ícono de la huella (no el texto)
            s['p'], s['polls'] = 'huella', 0
        elif s['p'] == 'resumen' and t == 'Cuentas':
            s['p'] = 'resumen_cuentas'
        elif s['p'] in ('resumen', 'resumen_cuentas') and 909 <= x <= 1029 and 2117 <= y <= 2237:   # ícono Tpago
            s['p'] = 'tpago'
        elif s['p'] == 'tpago' and t == 'Enviar Tpago':
            s['p'], s['bajo'] = 'form', False
        elif s['p'] == 'form':
            if s['lista'] == 'banco':
                if re.match(r'^0\d{3} - ', t):
                    s['banco'], s['lista'] = t, None
            elif s['lista'] == 'cuenta':
                s['cuenta'], s['lista'] = t, None
            elif t == s['banco']:
                s['lista'] = 'banco'
            elif t == s['cuenta']:
                s['lista'] = 'cuenta'
            elif hit and hit.clase == 'EditText':
                s['foco'] = {s['tel']: 'tel', s['ced']: 'ced', s['monto']: 'monto'}.get(t)
            elif hit and hit.clase == 'Button' and t == self.boton:
                s['p'], s['polls'] = 'verifica', 0
        elif s['p'] == 'verifica' and t == 'Aceptar':
            s['toco_aceptar'] = True
            s['p'] = 'metodo'
        elif s['p'] == 'metodo' and m.compacto(t) == 'identificacion biometrica':
            s['p'], s['polls'] = 'huella_pago', 0
        elif s['p'] == 'metodo':
            s['otro_metodo'] = t

    def escribir(self, texto):
        s = self.s
        if s['foco'] == 'monto':
            previo = m.digitos(s['monto']).lstrip('0')
            s['monto'] = m.fmt(int(previo + texto) / (1 if self.pesos else 100))
        elif s['foco'] == 'tel':
            s['tel'] = texto[:4] + '-' + texto[4:]
        elif s['foco'] == 'ced':
            s['ced'] = '{:,}'.format(int(texto)).replace(',', '.')

    def ancho(self):
        return 1080

    def escribir_lento(self, texto):
        for c in texto:
            self.escribir(c)

    def borrar(self, n=14):
        if self.s['foco'] == 'monto' and self.borrar_anda:
            self.s['monto'] = '0,00'

    def bajar(self):
        if self.s['foco']:                           # 28/11: deslizar con el teclado abierto abrió su configuración
            self.s['p'] = 'config_teclado'
        elif self.s['p'] == 'form':
            self.s['bajo'] = True

    def ocultar_teclado(self):
        self.s['foco'] = None

    def abrir(self):
        self.s['p'] = 'login'

    def guardar(self, nombre):
        return 'mercantil_%s' % nombre

    def avisar(self, titulo, texto, prioridad=3):
        self.s['avisos'].append(titulo + ' · ' + texto)

    def esperar(self, s):
        pass


m.ESPERA_HUELLA_S = 3
m.ESPERA_LISTO_S = 3
bien = n = 0


def caso(nombre, esperado, **kw):
    global bien, n
    n += 1
    telefono, monto = kw.pop('telefono', TEL), kw.pop('monto', MONTO)
    f = Fake(**kw)
    try:
        r = m.pagar(telefono, CED, BANCO, monto, tel=f)
    except m.Frenado as e:
        r = 'frenado: ' + str(e)
    # Aceptar solo si todo coincidió (el pago llega a la huella); nunca otro método de seguridad
    ok = esperado in r and (f.s['toco_aceptar'] == r.startswith(('ok', 'sin listo'))) and not f.s.get('otro_metodo')
    bien += ok
    print('%s %s → %s' % ('BIEN' if ok else 'MAL ', nombre, r[:150]))
    if not ok:
        print('    avisos:', f.s['avisos'][-3:])
    return f


f = caso('pago completo: elige *2222, revisa, toca Aceptar e Identificación Biométrica, espera tu huella', 'ok 999888777')
ver = [a for a in f.s['avisos'] if 'revisado' in a]
print('     aviso:', ver[0] if ver else '—')
caso('ninguna cuenta alcanza', 'Ninguna cuenta alcanza', saldos={'*1111': 100.0, '*2222': 200.0})
caso('la huella no llega', 'No llegué al Resumen financiero', huella_ok=False)
caso('28/11: el monto ya tenía algo y borrar no anda: se frena sin escribir encima', 'no queda en 0,00',
     monto_inicial='66,00', borrar_anda=False)
caso('el monto tenía algo y borrar anda: lo limpia y escribe', 'ok', monto_inicial='66,00')
caso('si la app tomara pesos enteros: queda otro número y se frena (no reintenta)', 'El monto quedó', monto_pesos=True)
caso('no hay botón para seguir (no grabado): se frena', 'No encontré el botón para seguir', boton=None)
caso('el botón se llama distinto (no grabado): se frena', 'No encontré el botón para seguir', boton='Pagar')
caso('Verifica muestra otro teléfono: se frena y avisa NO toques Aceptar', 'NO toques Aceptar',
     verifica_cambia=(r'^a 0\d{3}-\d{7}\?$', 'a 0424-0000000?'))
caso('el banco no está en la lista (ni buscando): se frena', 'no está "0102 -"', banco_en_lista=False)
caso('no ponés la huella: avisa que no vio el ¡Listo!', 'sin listo', john_acepta=False)
caso('teléfono mal escrito: se frena antes de abrir', 'Datos inválidos', telefono='4141234567')
print('%d de %d casos bien' % (bien, n))
sys.exit(0 if bien == n else 1)
