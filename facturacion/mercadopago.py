#!/usr/bin/env python3
"""Lee las ENTRADAS de Mercado Pago (Tu dinero → Ver todos) por ADB, como itau.py.

Abre Mercado Pago, espera el inicio (si la app pide huella, la ponés vos: no la saltea ni la reemplaza), toca el saldo,
"Ver todos" y baja por "Movimientos de tu dinero" leyendo la lista. No abre cada movimiento: la lista ya trae nombre,
monto, tipo y hora. Solo lee: no toca Ingresar, Transferir ni nada que mueva plata. Al terminar vuelve al inicio y vibra.

  python mercadopago.py --probar                 # entradas de los últimos 7 días, sin mandar nada
  python mercadopago.py --probar --dias 40
  python mercadopago.py --dias 9                 # lee y manda a la hoja "Movs UY" (lo que usa el botón de los martes)

Referencia: MP-<fecha>-<hora>-<monto en centésimos>-<orden> (la lista no muestra el N° de movimiento).
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
from itau import fecha_de  # noqa: E402

PAQUETE = 'com.mercadopago.wallet'
CTA = 'MercadoPago'
CSV = os.path.join(DESCARGAS, 'mercadopago_entradas.csv')
ESPERA_INICIO_S = 120
MAX_DESLIZADAS = 60
MONTO = re.compile(r'^([+-])\s*(\d+) pesos uruguayos(?: con (\d+) centésimos)?$')   # "+655 pesos uruguayos con 94 centésimos"
HORA = re.compile(r'^\d{1,2}:\d{2}$')
EXCLUIR = re.compile(r'devoluci|reintegro|cancelad', re.I)


def leer_lista(lista):
    """Filas de "Movimientos de tu dinero", en orden: {fecha, hora, nombre, tipo, monto}.
    Cada fila: el nombre (repetido), el monto con signo, el tipo y la hora. Los saldos del día van sin signo."""
    t = [x[0] for x in lista]
    filas, fecha = [], None
    for i, s in enumerate(t):
        f = fecha_de(s)
        if f:
            fecha = f
            continue
        m = MONTO.match(s)
        if not m or fecha is None or i == 0:
            continue
        monto = int(m.group(2)) + int(m.group(3) or 0) / 100.0
        tipo = t[i + 1] if i + 1 < len(t) else ''
        hora = t[i + 2] if i + 2 < len(t) and HORA.match(t[i + 2]) else ''
        filas.append({'fecha': fecha, 'hora': hora, 'nombre': ' '.join(t[i - 1].split()), 'tipo': tipo,
                      'monto': monto * (-1 if m.group(1) == '-' else 1)})
    return filas


def en_inicio(lista):
    return any(s.startswith('Saldo,') or s == 'Ver todos' for s, _, _, _ in lista)


def abrir_movimientos():
    adb('shell', 'monkey', '-p', PAQUETE, '-c', 'android.intent.category.LAUNCHER', '1')
    avisar('Mercado Pago', 'Si Mercado Pago pide tu huella, ponela. Después no toques la pantalla.')
    vibrar()
    if not esperar(en_inicio, ESPERA_INICIO_S, cada=3):
        guardar_pantalla('mp_fallo')
        raise SystemExit('Mercado Pago no llegó al inicio en %d s (¿huella?). Pantalla en Descargas/mp_fallo.xml'
                         % ESPERA_INICIO_S)
    time.sleep(2)
    if not any(s == 'Ver todos' for s, _, _, _ in textos()[0]):
        tocar('Saldo,', parcial=True)               # el recuadro del saldo abre "Tu dinero"
    if not tocar('Ver todos'):
        guardar_pantalla('mp_fallo')
        raise SystemExit('No encontré "Ver todos" en Tu dinero. Pantalla en Descargas/mp_fallo.xml')
    if not esperar(lambda l: any(s == 'Movimientos de tu dinero' for s, _, _, _ in l)
                   and any(fecha_de(s) for s, _, _, _ in l), 40):
        guardar_pantalla('mp_fallo')
        raise SystemExit('La lista de movimientos no cargó. Pantalla en Descargas/mp_fallo.xml')
    time.sleep(2)


def entradas(desde, hasta):
    """Baja la lista hasta pasar `desde` o hasta que no aparezca nada nuevo. La lista es una página web: trae todo
    lo cargado (también lo que está fuera de pantalla) y carga más al llegar abajo."""
    alto = tamano_pantalla()[1]
    vistas, sin_nuevas = {}, 0
    for _ in range(MAX_DESLIZADAS):
        filas = leer_lista(textos()[0])
        iguales, nuevas = {}, 0
        for f in filas:                              # dos movimientos iguales el mismo minuto: se cuentan aparte
            k = (f['fecha'], f['hora'], f['nombre'], f['monto'])
            iguales[k] = iguales.get(k, 0) + 1
            clave = k + (iguales[k],)
            if clave not in vistas:
                vistas[clave] = dict(f, orden=iguales[k])
                nuevas += 1
        sin_nuevas = 0 if nuevas else sin_nuevas + 1
        if any(f['fecha'] < desde for f in filas) or sin_nuevas >= 3:
            break
        adb('shell', 'input', 'swipe', '540', str(int(alto * 0.8)), '540', str(int(alto * 0.25)), '600')
        time.sleep(2.5)
    else:
        print('Aviso: bajé %d veces y no llegué al %s' % (MAX_DESLIZADAS, desde.strftime('%d/%m')), flush=True)
    resultado = []
    for f in vistas.values():
        if f['monto'] <= 0 or not desde <= f['fecha'] <= hasta or EXCLUIR.search(f['tipo'] + ' ' + f['nombre']):
            continue
        f['ref'] = 'MP-%s-%s-%d-%d' % (f['fecha'].strftime('%Y%m%d'), f['hora'].replace(':', ''),
                                       round(f['monto'] * 100), f['orden'])
        resultado.append(f)
    resultado.sort(key=lambda f: (f['fecha'], f['hora']), reverse=True)
    for f in resultado:
        print('%s %5s  %10.2f  %-34s %s' % (f['fecha'].strftime('%d/%m/%y'), f['hora'], f['monto'], f['nombre'],
                                            f['tipo']), flush=True)
    return resultado


def para_planilla(lista):
    return [{'fecha_hora': f['fecha'].strftime('%d/%m/%Y') + (' - ' + f['hora'] if f['hora'] else ''),
             'monto': f['monto'], 'moneda': 'UYU', 'titular': f['nombre'], 'cta': CTA, 'referencia': f['ref'],
             'descripcion': '' if f['tipo'] == 'Transferencia recibida' else f['tipo']} for f in lista]


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
    total = sum(f['monto'] for f in lista)
    print('\n%d entradas, total $ %.2f. Guardadas en %s' % (len(lista), total, CSV))
    if a.probar:
        avisar('Mercado Pago ✅', '%d entradas leídas, total $ %.2f (prueba, no se mandaron)' % (len(lista), total))
        sys.exit(0)
    r = mandar(filas, CTA)
    print('Planilla:', r, flush=True)
    if not r.get('ok'):
        avisar('Mercado Pago ⚠️', 'No se pudo mandar a la planilla: %s' % r.get('error', r))
        raise SystemExit(1)
    avisar('Mercado Pago ✅', '%d entradas leídas, %d nuevas en la planilla' % (len(lista), r.get('nuevas', 0)))
