#!/usr/bin/env python3
"""Lee las ENTRADAS de plata de la app de Prex (Movimientos → detalle de cada una) por ADB, como okx_ordenes.py.

Abre Prex, espera a que pongas tu huella (no la saltea ni la reemplaza), toca Movimientos, lee la lista
y entra al detalle de cada entrada para sacar el titular, la hora y el N° de referencia. Solo lee: no toca
Transferir, Cargar ni nada que mueva plata. Al terminar vuelve al inicio y vibra.

  python prex.py --pantalla prex_lista   # en 30 s guarda la pantalla en Descargas (prex_lista.xml) y vibra
  python prex.py --probar                # lee las entradas de los últimos 7 días y las muestra (no manda nada)
  python prex.py --probar --dias 3
  python prex.py --desde 01/10/2026 --hasta 31/10/2026   # un mes entero (o desde una fecha hasta hoy)
  python prex.py                         # lee y manda a la planilla (hoja "Movs UY" de Registro BEXO)

Siempre deja una copia en Descargas/prex_entradas.csv. Para mandar usa WEBAPP_URL y ORDENES_TOKEN de
~/.subir-ordenes.env (los mismos de subir_ordenes.py); del lado de Apps Script lo recibe 17_MovimientosUY.gs.
"""
import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from okx_ordenes import adb, bloqueado, conectar, tamano_pantalla, textos, tocar  # noqa: E402
from subir_ordenes import leer_env  # noqa: E402

PAQUETE = 'air.Prex'
DESCARGAS = os.path.expanduser('~/storage/downloads')
CSV = os.path.join(DESCARGAS, 'prex_entradas.csv')
# Ícono de cada fila de la lista (vistos el 09/11/2026): transfer-in, transfer-out, purchase. Puede haber más.
FECHA = re.compile(r'^\d{2}/\d{2}/\d{4}$')
MONTO = re.compile(r'^(-\s*)?(U\$S|\$)\s*([\d.]+,\d{2})$')
ESPERA_HUELLA_S = 120
# Si Prex abre sin mostrar el cartel de la huella, se toca su botón de huella (texto o descripción con esto).
BOTON_HUELLA = re.compile(r'huella|biom|fingerprint|digital', re.I)
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


def guardar_pantalla(nombre):
    with open(os.path.join(DESCARGAS, nombre + '.xml'), 'w') as fh:
        fh.write(textos()[1])


def esperar_huella():
    """Espera a que entres a Prex con tu huella. Si el cartel de la huella no aparece solo, toca el botón de huella
    de la pantalla de ingreso (cada 10 s, por si el primer toque no lo abrió). La huella la ponés siempre vos."""
    fin, ultimo_toque, guardada = time.time() + ESPERA_HUELLA_S, 0, False
    while time.time() < fin:
        lista = textos()[0]
        if any(t == 'Movimientos' for t, _, _, _ in lista):
            return True
        if time.time() - ultimo_toque > 10:
            for t, x, y, _ in lista:
                if BOTON_HUELLA.search(t) and y > 0:
                    adb('shell', 'input', 'tap', str(x), str(y))
                    ultimo_toque = time.time()
                    print('Toqué "%s" para que aparezca la huella' % t, flush=True)
                    break
            else:
                if not guardada and lista and time.time() > fin - ESPERA_HUELLA_S + 20:
                    guardar_pantalla('prex_ingreso')   # para ajustar el botón si no lo encontró
                    guardada = True
        time.sleep(3)
    return False


def abrir_movimientos():
    adb('shell', 'monkey', '-p', PAQUETE, '-c', 'android.intent.category.LAUNCHER', '1')
    avisar('Prex', 'Poné tu huella en Prex. Después no toques la pantalla.')
    vibrar()
    if not esperar_huella():
        guardar_pantalla('prex_fallo')
        raise SystemExit('Prex no llegó al inicio en %d s (¿huella?). Guardé la pantalla en Descargas/prex_fallo.xml'
                         % ESPERA_HUELLA_S)
    time.sleep(2)
    if not tocar('Movimientos') or not esperar(hay('Tus movimientos'), 30):
        raise SystemExit('No pude entrar a Movimientos')
    time.sleep(3)   # que cargue la lista


def deslizar(hacia_abajo, alto, rapido=False):
    """hacia_abajo=True muestra lo más viejo (la lista sube). rapido: un envión largo, para llegar al final."""
    y1, y2 = (0.8, 0.45) if hacia_abajo else (0.45, 0.8)
    if rapido:
        y1, y2 = (0.85, 0.25) if hacia_abajo else (0.25, 0.85)
    adb('shell', 'input', 'swipe', '540', str(int(alto * y1)), '540', str(int(alto * y2)), '150' if rapido else '700')
    time.sleep(1.5)


def entradas(desde, hasta):
    """Recorre las entradas entre `desde` y `hasta` (fechas, días enteros), entrando al detalle de cada una.
    Prex carga la lista de a partes: si lo más viejo cargado todavía es posterior a `desde`, baja hasta el final
    para que cargue más, y para cuando la lista deja de crecer."""
    alto = tamano_pantalla()[1]
    hechas, resultado, sin_crecer = set(), [], 0
    for _ in range(1500):
        todas = leer_lista(textos()[0])
        filas = [f for f in todas if f['monto'] > 0
                 and desde <= datetime.strptime(f['fecha'], '%d/%m/%Y').date() <= hasta]
        pendientes = [f for f in filas if (f['fecha'], f['desc'], f['monto'], f['n']) not in hechas]
        if not pendientes:
            mas_vieja = min((datetime.strptime(f['fecha'], '%d/%m/%Y').date() for f in todas), default=desde)
            if mas_vieja < desde or sin_crecer >= 3:
                return resultado
            for _ in range(4):                               # al final de la lista, para que cargue más
                deslizar(True, alto, rapido=True)
            time.sleep(3)
            sin_crecer = sin_crecer + 1 if len(leer_lista(textos()[0])) == len(todas) else 0
            continue
        f = pendientes[0]
        if f['y'] == 0 or f['y'] > alto * 0.85 or f['y'] < alto * 0.3:
            # Fuera de pantalla (o tapada por los filtros de arriba): hacia dónde está, según las filas que se ven.
            visibles = [i for i, g in enumerate(todas) if alto * 0.3 <= g['y'] <= alto * 0.85]
            i = todas.index(f)
            deslizar(not visibles or i > visibles[-1] or (f['y'] > alto * 0.85), alto)
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


def para_planilla(lista):
    return [{'fecha_hora': e.get('Fecha y hora', e['fecha']), 'monto': e['monto'], 'moneda': e['moneda'],
             'titular': e.get('Titular', ''), 'cta': 'Prex', 'referencia': e.get('N° de referencia', ''),
             'descripcion': e['desc']} for e in lista]


def subir(lista):
    cfg = leer_env()
    cuerpo = json.dumps({'movimientosUY': para_planilla(lista), 'cta': 'Prex', 'token': cfg['ORDENES_TOKEN']}).encode()
    req = urllib.request.Request(cfg['WEBAPP_URL'], data=cuerpo, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode('utf-8', 'replace'))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--pantalla', metavar='NOMBRE', help='guarda la pantalla en Descargas/NOMBRE.xml y vibra')
    ap.add_argument('--espera', type=int, default=30, help='segundos antes de guardar la pantalla')
    ap.add_argument('--probar', action='store_true', help='lee las entradas y las muestra, sin mandar nada')
    ap.add_argument('--dias', type=int, default=7, help='últimos N días (días enteros)')
    ap.add_argument('--desde', help='dd/mm/aaaa: desde este día (en vez de --dias)')
    ap.add_argument('--hasta', help='dd/mm/aaaa: hasta este día (por defecto hoy)')
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
        hoy = datetime.now().date()
        desde = datetime.strptime(a.desde, '%d/%m/%Y').date() if a.desde else hoy - timedelta(days=a.dias)
        hasta = datetime.strptime(a.hasta, '%d/%m/%Y').date() if a.hasta else hoy
        lista = entradas(desde, hasta)
    finally:
        adb('shell', 'input', 'keyevent', 'KEYCODE_HOME')
        vibrar(800)
    guardar_csv(lista)
    total = sum(e['monto'] for e in lista)
    print('\n%d entradas, total $ %.2f. Guardadas en %s' % (len(lista), total, CSV))
    if a.probar:
        avisar('Prex ✅', '%d entradas leídas, total $ %.2f (prueba, no se mandaron)' % (len(lista), total))
        sys.exit(0)
    r = subir(lista)
    print('Planilla:', r, flush=True)
    if not r.get('ok'):
        avisar('Prex ⚠️', 'No se pudo mandar a la planilla: %s' % r.get('error', r))
        raise SystemExit(1)
    avisar('Prex ✅', '%d entradas leídas, %d nuevas en la planilla' % (len(lista), r.get('nuevas', 0)))
    with open(os.path.expanduser('~/.movs_uy_ultima'), 'w') as fh:   # para el botón de los martes (movs_uy_boton.sh)
        fh.write(str(int(time.time())))
