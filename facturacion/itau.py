#!/usr/bin/env python3
"""Lee las ENTRADAS de la cuenta en pesos de Itaú (CC Pesos → movimientos → entradas) por ADB, como prex.py.

Abre Itaú, toca "Ingresar" para que aparezca el cartel de la huella y espera a que la pongas (no la saltea ni la
reemplaza). Después toca la cuenta CC Pesos, la pestaña "entradas" y abre cada entrada para leer el ordenante.
Solo lee: no toca Transferir, Pagar ni nada que mueva plata. Al terminar vuelve al inicio y vibra.

  python itau.py --probar                 # entradas de los últimos 7 días, sin mandar nada
  python itau.py --desde 01/10/2026 --hasta 31/10/2026
  python itau.py --dias 9                 # lee y manda a la hoja "Movs UY" (lo que usa el botón de los martes)

Itaú no muestra N° de referencia en las transferencias: para no duplicar se arma uno con la fecha, los números
del texto ("TRASPASO DE 4731176ILINK"), el monto y el orden dentro del día.
"""
import argparse
import csv
import os
import re
import sys
import time
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from okx_ordenes import adb, bloqueado, conectar, tamano_pantalla, textos, tocar  # noqa: E402
from prex import avisar, esperar, guardar_pantalla, mandar, vibrar, DESCARGAS  # noqa: E402

PAQUETE = 'com.uy.itau.appitauuypf'
CTA = 'Itau'
CSV = os.path.join(DESCARGAS, 'itau_entradas.csv')
ESPERA_HUELLA_S = 120
MESES = {m: i + 1 for i, m in enumerate(['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
                                         'septiembre', 'octubre', 'noviembre', 'diciembre'])}
FECHA = re.compile(r'^(\d{1,2}) de ([a-záéíóú]+)$', re.I)
MONTO = re.compile(r'^(-\s*)?(U\$S|\$)\s*([\d.]+,\d{2})$')


def fecha_de(texto, hoy=None):
    """'09 de noviembre' → date. Sin año: si el mes es posterior al actual, es del año pasado."""
    hoy = hoy or date.today()
    t = texto.strip().lower()
    if t == 'hoy':
        return hoy
    if t == 'ayer':
        return hoy - timedelta(days=1)
    m = FECHA.match(t)
    if not m or m.group(2) not in MESES:
        return None
    mes, dia = MESES[m.group(2)], int(m.group(1))
    return date(hoy.year - (1 if mes > hoy.month else 0), mes, dia)


def numero(s):
    return float(s.replace('.', '').replace(',', '.'))


def leer_pantalla(lista):
    """Lo que hay en pantalla, en orden: fechas ('fecha', date) y filas ('fila', {...}).
    Cada fila es el texto justo antes de un monto. Lo que sigue a una fila abierta (rótulo: valor) va a 'det'."""
    items, ultimo = [], None
    textos_ = [(t, x, y) for t, x, y, _ in lista]
    ids = [rid for _, _, _, rid in lista]
    i = 0
    while i < len(textos_):
        t, x, y = textos_[i]
        f = fecha_de(t)
        if f:
            items.append(('fecha', f))
            ultimo = None
        elif MONTO.match(t) and i > 0 and ids[i] == 'txtAmount':   # no el "saldo actual" de arriba
            m = MONTO.match(t)
            desc, dx, dy = textos_[i - 1]
            if not MONTO.match(desc) and not fecha_de(desc) and not desc.endswith(':'):
                ultimo = {'desc': ' '.join(desc.split()), 'monto': numero(m.group(3)) * (-1 if m.group(1) else 1),
                          'moneda': 'USD' if m.group(2) == 'U$S' else 'UYU', 'x': dx, 'y': dy, 'det': {}}
                items.append(('fila', ultimo))
        elif t.endswith(':') and ultimo is not None and i + 1 < len(textos_):
            ultimo['det'][t[:-1].strip().lower()] = textos_[i + 1][0]
        i += 1
    return items


def filas_con_fecha(items, fecha_previa):
    """Pone a cada fila la fecha del último encabezado de arriba (o fecha_previa si arriba no hay ninguno)."""
    filas, f = [], fecha_previa
    for tipo, v in items:
        if tipo == 'fecha':
            f = v
        else:
            v['fecha'] = f
            filas.append(v)
    return filas


def alinear(previas, nuevas):
    """(salteo, k): las filas nuevas[salteo:salteo+k] son las últimas k de `previas` (mismo texto y monto, en orden).
    Así se sabe qué filas ya se vieron aunque haya dos iguales, y se les copia la fecha y si ya se leyeron.
    `salteo` (hasta 2) tolera una fila cortada arriba que en la pantalla anterior no se leyó."""
    for salteo in range(0, min(3, len(nuevas))):
        resto = nuevas[salteo:]
        for k in range(min(len(previas), len(resto)), 0, -1):
            if all((a['desc'], a['monto']) == (b['desc'], b['monto']) for a, b in zip(previas[-k:], resto[:k])):
                return salteo, k
    return 0, 0


def referencia(f, orden):
    digitos = ''.join(re.findall(r'\d+', f['desc'])) or re.sub(r'\W+', '', f['desc'])[:20]
    return 'ITAU-%s-%s-%d-%d' % (f['fecha'].strftime('%Y%m%d'), digitos, round(f['monto'] * 100), orden)


def esperar_huella():
    """Toca "Ingresar" (abre el cartel de la huella) y espera a que entres. La huella la ponés siempre vos."""
    fin, ultimo_toque = time.time() + ESPERA_HUELLA_S, 0
    while time.time() < fin:
        lista = textos()[0]
        if any(t.startswith('CC Pesos') for t, _, _, _ in lista):
            return True
        if time.time() - ultimo_toque > 10:
            for t, x, y, _ in lista:
                if t.strip().lower() == 'ingresar' and y > 0:
                    adb('shell', 'input', 'tap', str(x), str(y))
                    ultimo_toque = time.time()
                    print('Toqué "Ingresar"', flush=True)
                    break
        time.sleep(3)
    return False


def abrir_entradas():
    adb('shell', 'monkey', '-p', PAQUETE, '-c', 'android.intent.category.LAUNCHER', '1')
    avisar('Itaú', 'Poné tu huella en Itaú. Después no toques la pantalla.')
    vibrar()
    if not esperar_huella():
        guardar_pantalla('itau_fallo')
        raise SystemExit('Itaú no llegó al inicio en %d s (¿huella?). Pantalla en Descargas/itau_fallo.xml'
                         % ESPERA_HUELLA_S)
    time.sleep(2)
    if not tocar('CC Pesos', parcial=True) or not esperar(hay_texto('entradas'), 30):
        guardar_pantalla('itau_fallo')
        raise SystemExit('No pude entrar a los movimientos de CC Pesos')
    time.sleep(2)
    if not tocar('entradas'):
        raise SystemExit('No encontré la pestaña "entradas"')
    time.sleep(3)


def hay_texto(texto):
    return lambda lista: any(t.strip().lower() == texto for t, _, _, _ in lista)


def deslizar(alto):
    """Baja un tercio de pantalla (para que siempre queden filas a la vista de antes y se puedan alinear)."""
    adb('shell', 'input', 'swipe', '540', str(int(alto * 0.75)), '540', str(int(alto * 0.45)), '800')
    time.sleep(2)


MAX_MINUTOS = 15


def entradas(desde, hasta):
    alto = tamano_pantalla()[1]
    previas, resultado, iguales, sin_cambio = [], [], {}, 0
    fecha_previa = date.today()
    lugar_pedido = None                          # (fila, y) cuando se bajó para hacer lugar al detalle
    fin = time.time() + MAX_MINUTOS * 60
    mas_vieja = None
    for _ in range(1500):
        if time.time() > fin:
            print('Corté a los %d minutos: algo no avanzaba' % MAX_MINUTOS, flush=True)
            guardar_pantalla('itau_trabado')
            return resultado
        nuevas = filas_con_fecha(leer_pantalla(textos()[0]), fecha_previa)
        salteo, k = alinear(previas, nuevas)
        for f in nuevas[:salteo]:
            f['hecha'] = True                    # quedaron arriba: ya se vieron
        for a, b in zip(previas[-k:] if k else [], nuevas[salteo:salteo + k]):
            b['fecha'], b['hecha'] = a['fecha'], a.get('hecha', False)
        if previas and nuevas and k == 0:
            print('Aviso: no pude alinear con la pantalla anterior', flush=True)
        if nuevas:
            mas_vieja = min(mas_vieja or nuevas[-1]['fecha'], nuevas[-1]['fecha'])
        if nuevas:
            fecha_previa = nuevas[-1]['fecha']
        previas = nuevas
        pendiente = next((f for f in nuevas if not f.get('hecha') and f['monto'] > 0
                          and desde <= f['fecha'] <= hasta), None)
        if pendiente is None:
            # Nada para leer en pantalla: o ya pasamos `desde`, o hay que bajar.
            if any(f['fecha'] < desde for f in nuevas):
                return resultado
            for f in nuevas:                     # lo más nuevo que `hasta` se marca como visto
                f['hecha'] = True
            firma = [(f['desc'], f['monto']) for f in nuevas]
            deslizar(alto)
            despues = [(f['desc'], f['monto']) for f in filas_con_fecha(leer_pantalla(textos()[0]), fecha_previa)]
            sin_cambio = sin_cambio + 1 if despues == firma else 0
            if sin_cambio >= 2:                  # el final de la lista
                if mas_vieja and mas_vieja > desde:
                    print('Aviso: la lista de Itaú termina el %s; antes de esa fecha no muestra nada (sin filtro)'
                          % mas_vieja.strftime('%d/%m'), flush=True)
                return resultado
            continue
        # Que haya lugar abajo para el detalle. Si ya se bajó y la fila no se movió (final de la lista), se abre igual.
        if pendiente['y'] > alto * 0.6 and lugar_pedido != (pendiente['desc'], pendiente['monto'], pendiente['y']):
            lugar_pedido = (pendiente['desc'], pendiente['monto'], pendiente['y'])
            deslizar(alto)
            continue
        adb('shell', 'input', 'tap', str(pendiente['x']), str(pendiente['y']))
        time.sleep(2)
        abierta = filas_con_fecha(leer_pantalla(textos()[0]), fecha_previa)
        det = next((f['det'] for f in abierta if abs(f['y'] - pendiente['y']) < 40
                    and (f['desc'], f['monto']) == (pendiente['desc'], pendiente['monto'])), {})
        adb('shell', 'input', 'tap', str(pendiente['x']), str(pendiente['y']))     # la vuelve a cerrar
        time.sleep(1.5)
        pendiente['hecha'] = True
        clave = (pendiente['fecha'], pendiente['desc'], pendiente['monto'])
        iguales[clave] = iguales.get(clave, 0) + 1
        e = dict(pendiente, det=det, ref=referencia(pendiente, iguales[clave]))
        resultado.append(e)
        print('%s  %10.2f %s  %-34s %s' % (e['fecha'].strftime('%d/%m/%y'), e['monto'], e['moneda'],
                                           det.get('ordenante') or e['desc'], e['ref']), flush=True)
    return resultado


def detalle_util(e):
    """El texto del banco solo si agrega algo además del ordenante (ej. "CRE. CAMBIOSTOLC29427756")."""
    return '' if e['desc'].startswith('TRASPASO DE') and e['det'].get('ordenante') else e['desc']


def para_planilla(lista):
    return [{'fecha_hora': e['fecha'].strftime('%d/%m/%Y'), 'monto': e['monto'], 'moneda': e['moneda'],
             'titular': e['det'].get('ordenante') or e['desc'], 'cta': CTA, 'referencia': e['ref'],
             'descripcion': detalle_util(e)} for e in lista]


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--probar', action='store_true', help='lee las entradas y las muestra, sin mandar nada')
    ap.add_argument('--dias', type=int, default=7, help='últimos N días (días enteros)')
    ap.add_argument('--desde', help='dd/mm/aaaa: desde este día (en vez de --dias)')
    ap.add_argument('--hasta', help='dd/mm/aaaa: hasta este día (por defecto hoy)')
    a = ap.parse_args()
    if not conectar():
        raise SystemExit('Sin ADB: activá Depuración inalámbrica (Opciones de desarrollador) y que haya wifi')
    if bloqueado():
        raise SystemExit('Teléfono bloqueado: desbloquealo y volvé a probar')
    hoy = date.today()
    desde = datetime.strptime(a.desde, '%d/%m/%Y').date() if a.desde else hoy - timedelta(days=a.dias)
    hasta = datetime.strptime(a.hasta, '%d/%m/%Y').date() if a.hasta else hoy
    try:
        abrir_entradas()
        lista = entradas(desde, hasta)
    finally:
        adb('shell', 'input', 'keyevent', 'KEYCODE_HOME')
        vibrar(800)
    filas = para_planilla(lista)
    with open(CSV, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0]) if filas else ['fecha_hora'])
        w.writeheader()
        w.writerows(filas)
    total = sum(e['monto'] for e in lista)
    print('\n%d entradas, total $ %.2f. Guardadas en %s' % (len(lista), total, CSV))
    if a.probar:
        avisar('Itaú ✅', '%d entradas leídas, total $ %.2f (prueba, no se mandaron)' % (len(lista), total))
        sys.exit(0)
    r = mandar(filas, CTA)
    print('Planilla:', r, flush=True)
    if not r.get('ok'):
        avisar('Itaú ⚠️', 'No se pudo mandar a la planilla: %s' % r.get('error', r))
        raise SystemExit(1)
    avisar('Itaú ✅', '%d entradas leídas, %d nuevas en la planilla' % (len(lista), r.get('nuevas', 0)))
