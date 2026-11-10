#!/usr/bin/env python3
"""Lee las ENTRADAS de plata de la app de Prex (Movimientos → detalle de cada una) por ADB, como okx_ordenes.py.

Abre Prex, espera a que pongas tu huella (no la saltea ni la reemplaza), toca Movimientos, lee la lista
y entra al detalle de cada entrada para sacar el titular, la hora y el N° de referencia. Solo lee: no toca
Transferir, Cargar ni nada que mueva plata. Al terminar vuelve al inicio y vibra.

  python prex.py --pantalla prex_lista   # en 30 s guarda la pantalla en Descargas (prex_lista.xml) y vibra
  python prex.py --probar                # lee las entradas de los últimos 7 días y las muestra (no manda nada)
  python prex.py --probar --dias 3

Por ahora deja todo en Descargas/prex_entradas.csv. Mandarlo a la planilla es el paso siguiente.
"""
import argparse
import csv
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from okx_ordenes import adb, bloqueado, conectar, tamano_pantalla, textos, tocar  # noqa: E402

PAQUETE = 'air.Prex'
DESCARGAS = os.path.expanduser('~/storage/downloads')
CSV = os.path.join(DESCARGAS, 'prex_entradas.csv')
# Ícono de cada fila de la lista (vistos el 09/11/2026): transfer-in, transfer-out, purchase. Puede haber más.
FECHA = re.compile(r'^\d{2}/\d{2}/\d{4}$')
MONTO = re.compile(r'^(-\s*)?(U\$S|\$)\s*([\d.]+,\d{2})$')
ESPERA_HUELLA_S = 120
ROTULOS = ('Fecha y hora', 'Recibiste de', 'Titular', 'Entidad financiera', 'País', 'N° de cuenta', 'Motivo',
           'N° de referencia')


def vibrar(ms=400):
    subprocess.run(['termux-vibrate', '-d', str(ms)], check=False)


def avisar(titulo, texto):
    subprocess.run(['termux-notification', '--id', 'prex', '--title', titulo, '--content', texto], check=False)


def numero(s):
    return float(s.replace('.', '').replace(',', '.'))


def leer_lista(lista):
    """Filas de la lista de Movimientos, en orden: {fecha, tipo, desc, monto, moneda, x, y}.
    Prex (una página web adentro de la app) trae la lista entera; las filas fuera de pantalla vienen en (0, 0)."""
    filas, fecha, fila = [], None, None
    for t, x, y, _ in lista:
        if FECHA.match(t):
            fecha = t
        elif re.fullmatch(r'[a-z]+(-[a-z]+)*', t) and fecha:      # el ícono: arranca una fila
            fila = {'fecha': fecha, 'tipo': t, 'desc': '', 'x': x, 'y': y}
        elif fila is not None and not fila['desc']:
            fila['desc'], fila['x'], fila['y'] = t, x, y
        elif fila is not None and MONTO.match(t):
            m = MONTO.match(t)
            fila['monto'] = numero(m.group(3)) * (-1 if m.group(1) else 1)
            fila['moneda'] = 'USD' if m.group(2) == 'U$S' else 'UYU'
            filas.append(fila)
            fila = None
    # Las filas iguales (misma fecha, texto y monto) se numeran para no confundirlas entre sí.
    vistos = {}
    for f in filas:
        k = (f['fecha'], f['desc'], f['monto'])
        vistos[k] = vistos.get(k, 0) + 1
        f['n'] = vistos[k]
    return filas


def leer_detalle(lista):
    """Del detalle: lo que va a la derecha de cada rótulo (Titular, Fecha y hora, N° de referencia...)."""
    textos_ = [t for t, _, _, _ in lista]
    det = {}
    for rotulo in ROTULOS:
        if rotulo in textos_:
            i = textos_.index(rotulo)
            # Un rótulo vacío (ej. Motivo sin texto) no tiene valor: el texto siguiente ya es otro rótulo.
            if i + 1 < len(textos_) and textos_[i + 1] not in ROTULOS + ('Detalle', 'Copiar referencia'):
                det[rotulo] = textos_[i + 1]
    return det


def esperar(condicion, segundos, cada=2):
    fin = time.time() + segundos
    while time.time() < fin:
        lista = textos()[0]
        if condicion(lista):
            return lista
        time.sleep(cada)
    return None


def hay(texto):
    return lambda lista: any(t == texto for t, _, _, _ in lista)


def abrir_movimientos():
    adb('shell', 'monkey', '-p', PAQUETE, '-c', 'android.intent.category.LAUNCHER', '1')
    avisar('Prex', 'Poné tu huella en Prex. Después no toques la pantalla.')
    vibrar()
    if not esperar(hay('Movimientos'), ESPERA_HUELLA_S, cada=3):
        raise SystemExit('Prex no llegó al inicio en %d s (¿huella?)' % ESPERA_HUELLA_S)
    time.sleep(2)
    if not tocar('Movimientos') or not esperar(hay('Tus movimientos'), 30):
        raise SystemExit('No pude entrar a Movimientos')
    time.sleep(3)   # que cargue la lista


def entradas(dias):
    """Recorre las entradas de los últimos `dias`, entrando al detalle de cada una."""
    desde = datetime.now() - timedelta(days=dias)
    alto = tamano_pantalla()[1]
    hechas, resultado = set(), []
    for _ in range(200):
        filas = [f for f in leer_lista(textos()[0])
                 if f['monto'] > 0 and datetime.strptime(f['fecha'], '%d/%m/%Y') >= desde]
        pendientes = [f for f in filas if (f['fecha'], f['desc'], f['monto'], f['n']) not in hechas]
        if not pendientes:
            return resultado
        f = pendientes[0]
        if f['y'] == 0 or f['y'] > alto * 0.85:            # fuera de pantalla: bajar un poco y volver a mirar
            adb('shell', 'input', 'swipe', '540', str(int(alto * 0.8)), '540', str(int(alto * 0.45)), '700')
            time.sleep(1.5)
            continue
        if f['y'] < alto * 0.3:                             # tapada por los filtros de arriba: subir un poco
            adb('shell', 'input', 'swipe', '540', str(int(alto * 0.45)), '540', str(int(alto * 0.7)), '700')
            time.sleep(1.5)
            continue
        adb('shell', 'input', 'tap', str(f['x']), str(f['y']))
        det = leer_detalle(esperar(hay('Fecha y hora'), 20) or [])
        hechas.add((f['fecha'], f['desc'], f['monto'], f['n']))
        resultado.append(dict(f, **det))
        print('%s  %10.2f %s  %-28s ref %s' % (det.get('Fecha y hora', f['fecha']), f['monto'], f['moneda'],
                                              det.get('Titular', f['desc']), det.get('N° de referencia', '?')),
              flush=True)
        adb('shell', 'input', 'keyevent', 'KEYCODE_BACK')
        if not esperar(hay('Tus movimientos'), 20):
            raise SystemExit('No volví a la lista de Movimientos')
        time.sleep(1)
    return resultado


def guardar_csv(lista):
    with open(CSV, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(['fecha_hora', 'monto', 'moneda', 'titular', 'cta', 'referencia', 'descripcion', 'tipo'])
        for e in lista:
            w.writerow([e.get('Fecha y hora', e['fecha']), e['monto'], e['moneda'], e.get('Titular', ''), 'Prex',
                        e.get('N° de referencia', ''), e['desc'], e['tipo']])


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--pantalla', metavar='NOMBRE', help='guarda la pantalla en Descargas/NOMBRE.xml y vibra')
    ap.add_argument('--espera', type=int, default=30, help='segundos antes de guardar la pantalla')
    ap.add_argument('--probar', action='store_true', help='lee las entradas y las muestra, sin mandar nada')
    ap.add_argument('--dias', type=int, default=7)
    a = ap.parse_args()
    if not conectar():
        raise SystemExit('Sin ADB: activá Depuración inalámbrica (Opciones de desarrollador) y que haya wifi')
    if a.pantalla:
        print('En %d s guardo la pantalla. Andá a la app y esperá a que vibre.' % a.espera, flush=True)
        time.sleep(a.espera)
        lista, xml = textos()
        ruta = os.path.join(DESCARGAS, a.pantalla + '.xml')
        with open(ruta, 'w') as fh:
            fh.write(xml)
        vibrar(800)
        print('\n'.join(t for t, _, _, _ in lista))
        print('\nGuardado en %s (%d textos)' % (ruta, len(lista)))
        sys.exit(0)
    if bloqueado():
        raise SystemExit('Teléfono bloqueado: desbloquealo y volvé a probar')
    try:
        abrir_movimientos()
        lista = entradas(a.dias)
    finally:
        adb('shell', 'input', 'keyevent', 'KEYCODE_HOME')
        vibrar(800)
    guardar_csv(lista)
    total = sum(e['monto'] for e in lista)
    print('\n%d entradas, total $ %.2f. Guardadas en %s' % (len(lista), total, CSV))
    avisar('Prex ✅', '%d entradas leídas, total $ %.2f' % (len(lista), total))
