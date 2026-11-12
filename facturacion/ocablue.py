#!/usr/bin/env python3
"""Lee las ENTRADAS de la Cuenta pesos de OCA Blue (Ver movimientos) por ADB, como itau.py.

Abre OCA, toca "Ingresar" para que aparezca el cartel de la huella y espera a que la pongas (no la saltea ni la
reemplaza). Después toca "Ver movimientos" y, en la Cuenta pesos, abre cada entrada para leer el ordenante.
Solo lee: no toca Transferir, Pagar ni nada que mueva plata. Al terminar vuelve al inicio y vibra.

  python ocablue.py --probar                 # entradas de los últimos 7 días, sin mandar nada
  python ocablue.py --probar --dias 40
  python ocablue.py --dias 9                 # lee y manda a la hoja "Movs UY" (lo que usa el botón de los martes)

Referencia: el N° de transferencia del detalle (OCA-04071180). Los depósitos de Red Pagos no tienen detalle: se
arma una con la fecha, los números del texto, el monto y el orden dentro del día.
"""
import argparse
import csv
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from okx_ordenes import adb, bloqueado, conectar, tamano_pantalla, textos, tocar  # noqa: E402
from prex import avisar, esperar, guardar_pantalla, mandar, vibrar, DESCARGAS  # noqa: E402
from itau import MESES, alinear, deslizar, filas_con_fecha, numero  # noqa: E402

PAQUETE = 'uy.com.oca.ocatarjetas'
CTA = 'OcaBlue'
CSV = os.path.join(DESCARGAS, 'ocablue_entradas.csv')
ESPERA_HUELLA_S = 120
MAX_MINUTOS = 15
FECHA = re.compile(r'^(\d{1,2})\s+(?:de\s+)?([a-záéíóú]+)$', re.I)     # "11 noviembre"
MONTO = re.compile(r'^(-\s*)?\$\s*([\d.]+,\d{2})$')                      # " $ 1.000,00" / "- $ 10.000,00"


def fecha_de(texto, hoy=None):
    """'09 noviembre' → date. Sin año: si el mes es posterior al actual, es del año pasado."""
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


def zonas_tocables(xml):
    """Rectángulos de lo que se puede tocar. Las filas con flechita lo son; los depósitos de Red Pagos, no."""
    zonas = []
    try:
        for n in ET.fromstring(xml).iter('node'):
            b = [int(v) for v in re.findall(r'\d+', n.get('bounds') or '')]
            if n.get('clickable') == 'true' and len(b) == 4:
                zonas.append(b)
    except ET.ParseError:
        pass
    return zonas


def leer_pantalla(lista, xml=''):
    """Lo que hay en pantalla, en orden: fechas ('fecha', date) y filas ('fila', {...}).
    Cada fila es el texto justo antes de un monto en pesos. Lo que sigue a una fila abierta (rótulo: valor) va a 'det'.
    Los montos en U$S (cuenta dólares, que viene escondida en la misma pantalla) no se leen."""
    zonas = zonas_tocables(xml)
    items, ultimo = [], None
    for i, (t, x, y, _) in enumerate(lista):
        f = fecha_de(t)
        if f:
            items.append(('fecha', f))
            ultimo = None
        elif MONTO.match(t) and i > 0:
            m = MONTO.match(t)
            desc, dx, dy, _ = lista[i - 1]
            if MONTO.match(desc) or fecha_de(desc) or desc.endswith(':') or desc.lower().startswith('saldo'):
                continue
            ultimo = {'desc': ' '.join(desc.split()), 'monto': numero(m.group(2)) * (-1 if m.group(1) else 1),
                      'moneda': 'UYU', 'x': dx, 'y': dy, 'det': {},
                      'abre': any(z[0] <= dx <= z[2] and z[1] <= dy <= z[3] for z in zonas) if zonas else True}
            items.append(('fila', ultimo))
        elif t.endswith(':') and ultimo is not None and i + 1 < len(lista):
            valor = lista[i + 1][0]
            if not valor.endswith(':'):                      # "Referencia:" suele venir vacía
                ultimo['det'][t[:-1].strip().lower()] = ' '.join(valor.split())
    return items


def leer(fecha_previa):
    lista, xml = textos()
    return filas_con_fecha(leer_pantalla(lista, xml), fecha_previa)


def referencia(f, orden):
    n = re.sub(r'\D', '', f['det'].get('n° de transferencia', ''))
    if n:
        return 'OCA-' + n
    digitos = ''.join(re.findall(r'\d+', f['desc'])) or re.sub(r'\W+', '', f['desc'])[:20]
    return 'OCA-%s-%s-%d-%d' % (f['fecha'].strftime('%Y%m%d'), digitos, round(f['monto'] * 100), orden)


def esperar_huella():
    """Toca "Ingresar" (abre el cartel de la huella) y espera a que entres. La huella la ponés siempre vos."""
    fin, ultimo_toque = time.time() + ESPERA_HUELLA_S, 0
    while time.time() < fin:
        lista = textos()[0]
        if any(t.strip().lower() == 'ver movimientos' for t, _, _, _ in lista):
            return True
        if time.time() - ultimo_toque > 30:   # tocar seguido cancela el cartel de la huella
            for t, x, y, _ in lista:
                if t.strip().lower() == 'ingresar' and y > 0:
                    adb('shell', 'input', 'tap', str(x), str(y))
                    ultimo_toque = time.time()
                    print('Toqué "Ingresar"', flush=True)
                    break
        time.sleep(3)
    return False


def abrir_movimientos():
    adb('shell', 'monkey', '-p', PAQUETE, '-c', 'android.intent.category.LAUNCHER', '1')
    avisar('OCA Blue', 'Poné tu huella en OCA. Después no toques la pantalla.')
    vibrar()
    if not esperar_huella():
        guardar_pantalla('oca_fallo')
        raise SystemExit('OCA no llegó al inicio en %d s (¿huella?). Pantalla en Descargas/oca_fallo.xml'
                         % ESPERA_HUELLA_S)
    time.sleep(2)
    if not tocar('Ver movimientos') or not esperar(lambda l: any(t == 'Cuenta pesos' for t, _, _, _ in l), 30):
        guardar_pantalla('oca_fallo')
        raise SystemExit('No pude entrar a "Ver movimientos". Pantalla en Descargas/oca_fallo.xml')
    tocar('Cuenta pesos')                      # es la pestaña de entrada; tocarla igual por las dudas
    time.sleep(2)


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
            guardar_pantalla('oca_trabado')
            return resultado
        nuevas = leer(fecha_previa)
        salteo, k = alinear(previas, nuevas)
        for f in nuevas[:salteo]:
            f['hecha'] = True                    # quedaron arriba: ya se vieron
        for a, b in zip(previas[-k:] if k else [], nuevas[salteo:salteo + k]):
            b['fecha'], b['hecha'] = a['fecha'], a.get('hecha', False)
        if previas and nuevas and k == 0:
            print('Aviso: no pude alinear con la pantalla anterior', flush=True)
        if nuevas:
            mas_vieja = min(mas_vieja or nuevas[-1]['fecha'], nuevas[-1]['fecha'])
            fecha_previa = nuevas[-1]['fecha']
        previas = nuevas
        pendiente = next((f for f in nuevas if not f.get('hecha') and f['monto'] > 0
                          and desde <= f['fecha'] <= hasta), None)
        if pendiente is None:
            if any(f['fecha'] < desde for f in nuevas):
                return resultado
            for f in nuevas:
                f['hecha'] = True
            firma = [(f['desc'], f['monto']) for f in nuevas]
            deslizar(alto)
            despues = [(f['desc'], f['monto']) for f in leer(fecha_previa)]
            sin_cambio = sin_cambio + 1 if despues == firma else 0
            if sin_cambio >= 2:                  # el final de la lista
                if mas_vieja and mas_vieja > desde:
                    print('Aviso: la lista de OCA termina el %s; antes no muestra nada' % mas_vieja.strftime('%d/%m'),
                          flush=True)
                return resultado
            continue
        det = {}
        if pendiente['abre']:
            # El detalle se abre abajo de la fila (unos 800 px): que haya lugar. Si ya se bajó y no se movió, igual.
            clave_lugar = (pendiente['desc'], pendiente['monto'], pendiente['y'])
            if pendiente['y'] > alto * 0.5 and lugar_pedido != clave_lugar:
                lugar_pedido = clave_lugar
                deslizar(alto)
                continue
            adb('shell', 'input', 'tap', str(pendiente['x']), str(pendiente['y']))
            time.sleep(2)
            for _ in range(2):
                abierta = next((f for f in sorted(leer(fecha_previa), key=lambda f: abs(f['y'] - pendiente['y']))
                                if (f['desc'], f['monto']) == (pendiente['desc'], pendiente['monto']) and f['det']),
                               None)
                if abierta:
                    break
                time.sleep(1.5)
            if abierta:
                det = abierta['det']
                adb('shell', 'input', 'tap', str(abierta['x']), str(abierta['y']))     # la vuelve a cerrar
                time.sleep(1.5)
            else:
                print('(sin detalle: %s)' % pendiente['desc'], flush=True)
                adb('shell', 'input', 'tap', str(pendiente['x']), str(pendiente['y']))
                time.sleep(1.5)
        pendiente['hecha'] = True
        try:                                     # el detalle trae la fecha con año
            pendiente['fecha'] = datetime.strptime(det.get('fecha', ''), '%d/%m/%Y').date()
        except ValueError:
            pass
        clave = (pendiente['fecha'], pendiente['desc'], pendiente['monto'])
        iguales[clave] = iguales.get(clave, 0) + 1
        e = dict(pendiente, det=det)
        e['ref'] = referencia(e, iguales[clave])
        resultado.append(e)
        print('%s  %10.2f  %-34s %s' % (e['fecha'].strftime('%d/%m/%y'), e['monto'],
                                        det.get('nombre del ordenante') or e['desc'], e['ref']), flush=True)
    return resultado


def para_planilla(lista):
    filas = []
    for e in lista:
        nombre = e['det'].get('nombre del ordenante', '')
        filas.append({'fecha_hora': e['fecha'].strftime('%d/%m/%Y'), 'monto': e['monto'], 'moneda': e['moneda'],
                      'titular': nombre or e['desc'], 'cta': CTA, 'referencia': e['ref'],
                      'descripcion': e['det'].get('referencia', '') if nombre else e['desc']})
    return filas


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
        abrir_movimientos()
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
        avisar('OCA Blue ✅', '%d entradas leídas, total $ %.2f (prueba, no se mandaron)' % (len(lista), total))
        sys.exit(0)
    r = mandar(filas, CTA)
    print('Planilla:', r, flush=True)
    if not r.get('ok'):
        avisar('OCA Blue ⚠️', 'No se pudo mandar a la planilla: %s' % r.get('error', r))
        raise SystemExit(1)
    avisar('OCA Blue ✅', '%d entradas leídas, %d nuevas en la planilla' % (len(lista), r.get('nuevas', 0)))
