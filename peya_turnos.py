#!/usr/bin/env python3
"""Refresca la sección de turnos de PeYa Rider y te avisa cuando aparece uno nuevo.

Igual que okx_ordenes.py: maneja el teléfono por ADB (depuración inalámbrica, al mismo teléfono).
Abre la app de cero, sigue los botones de RUTA hasta los turnos y refresca con esperas que varían
(entre --min y --max segundos), para que no parezca un robot. Para con el botón PARAR de la notificación,
al pasar --minutos, o si bloqueás el teléfono.

  python peya_turnos.py --pantalla    # guarda lo que hay en pantalla en Descargas (para armar la RUTA)
  python peya_turnos.py --probar      # hace el recorrido y refresca 3 veces, mostrando lo que ve
  python peya_turnos.py               # lo corre telefono/peya.sh (botón de la notificación)

Solo avisa: no toma turnos.
"""
import argparse
import os
import random
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from okx_ordenes import adb, bloqueado, conectar, tamano_pantalla, textos  # noqa: E402

# Los botones para llegar a los turnos desde que se abre la app, por el texto que se ve en pantalla.
# PENDIENTE: completar con lo que muestre --pantalla en cada paso del recorrido de john.
RUTA = []
PARAR = os.path.expanduser('~/.peya_parar')
DESCARGAS = os.path.expanduser('~/storage/downloads')
HORA = re.compile(r'\b\d{1,2}:\d{2}\b')   # un turno se reconoce por sus horas (ajustar con la pantalla real)


def paquete_peya():
    for linea in adb('shell', 'pm', 'list', 'packages').splitlines():
        p = linea.replace('package:', '').strip()
        if 'rider' in p.lower() and ('pedidosya' in p.lower() or 'logistics' in p.lower() or 'peya' in p.lower()):
            return p
    raise SystemExit('No encontré la app de PeYa Rider instalada')


def pausa(a, b):
    time.sleep(random.uniform(a, b))


def tocar_xy(x, y):
    """Toca con un pequeño corrimiento, para que no sea siempre el mismo punto exacto."""
    adb('shell', 'input', 'tap', str(x + random.randint(-6, 6)), str(y + random.randint(-6, 6)))


def tocar(texto, intentos=10):
    for _ in range(intentos):
        for t, x, y, _ in textos()[0]:
            if t == texto:
                tocar_xy(x, y)
                pausa(2, 3.5)
                return True
        time.sleep(1.5)
    raise SystemExit('No encontré "%s" en la pantalla de PeYa Rider' % texto)


def refrescar(ancho, alto):
    """Tira la lista hacia abajo (como con el dedo) para que se actualice."""
    x = str(int(ancho * random.uniform(0.4, 0.6)))
    adb('shell', 'input', 'swipe', x, str(int(alto * random.uniform(0.28, 0.33))),
        x, str(int(alto * random.uniform(0.7, 0.78))), str(random.randint(350, 600)))


def turnos(lista):
    """Los textos de la pantalla que parecen un turno (tienen una hora)."""
    return {t for t, _, _, _ in lista if HORA.search(t)}


def avisar(nuevos):
    texto = ', '.join(sorted(nuevos))[:200]
    subprocess.run(['termux-notification', '--id', 'peya-turno', '--priority', 'max', '--sound',
                    '--vibrate', '500,300,500,300,500', '--title', '🛵 Turno nuevo en PeYa', '--content', texto],
                   check=False)
    subprocess.run(['termux-tts-speak', 'Turno nuevo en PeYa'], check=False)


def pantalla(espera):
    print('Ya podés salir de Termux. En %d segundos guarda lo que haya en pantalla: '
          'dejá PeYa Rider en la pantalla que quieras y esperá a que vibre.' % espera, flush=True)
    time.sleep(espera)
    lista, xml = textos()
    subprocess.run(['termux-vibrate'], check=False)
    ruta = os.path.join(DESCARGAS, time.strftime('peya_pantalla_%H%M%S.xml'))
    with open(ruta, 'w') as f:
        f.write(xml)
    print('\n'.join(t for t, _, _, _ in lista))
    print('\nGuardado en', ruta)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--pantalla', action='store_true')
    ap.add_argument('--probar', action='store_true')
    ap.add_argument('--espera', type=int, default=30, help='segundos antes de guardar la pantalla (--pantalla)')
    ap.add_argument('--min', type=float, default=20, help='espera mínima entre refrescos, en segundos')
    ap.add_argument('--max', type=float, default=45, help='espera máxima entre refrescos, en segundos')
    ap.add_argument('--minutos', type=float, default=60, help='cuánto tiempo refresca como mucho')
    args = ap.parse_args()
    if not conectar():
        raise SystemExit('Sin ADB: activá Depuración inalámbrica (Opciones de desarrollador) y que haya wifi')
    if args.pantalla:
        pantalla(args.espera)
        sys.exit(0)
    if not RUTA:
        raise SystemExit('Falta armar el recorrido (RUTA) con las pantallas de PeYa Rider')
    if bloqueado():
        raise SystemExit('Teléfono bloqueado: desbloquealo y volvé a tocar el botón')
    if os.path.exists(PARAR):
        os.remove(PARAR)
    paquete = paquete_peya()
    adb('shell', 'am', 'force-stop', paquete)
    adb('shell', 'monkey', '-p', paquete, '-c', 'android.intent.category.LAUNCHER', '1')
    pausa(7, 10)
    for paso in RUTA:
        tocar(paso)
    ancho, alto = tamano_pantalla()
    vistos = turnos(textos()[0])
    print(time.strftime('%H:%M'), 'Turnos al empezar:', sorted(vistos) or 'ninguno', flush=True)
    fin = time.time() + (3 * args.max + 60 if args.probar else args.minutos * 60)
    vueltas = 0
    while time.time() < fin and not os.path.exists(PARAR):
        pausa(args.min, args.max)
        if os.path.exists(PARAR):
            break
        if bloqueado():
            print(time.strftime('%H:%M'), 'Teléfono bloqueado: paro', flush=True)
            break
        refrescar(ancho, alto)
        pausa(3, 5)
        vueltas += 1
        ahora = turnos(textos()[0])
        nuevos = ahora - vistos
        if args.probar:
            print('Vuelta %d:' % vueltas, sorted(ahora) or 'sin turnos', flush=True)
            if vueltas >= 3:
                break
        if nuevos:
            print(time.strftime('%H:%M'), 'NUEVO:', sorted(nuevos), flush=True)
            avisar(nuevos)
        vistos = ahora
    print(time.strftime('%H:%M'), 'Listo: %d refrescos' % vueltas, flush=True)
