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

# El recorrido desde que se abre la app hasta los turnos (pantallas de john, 04/11/2026, 1080x2400).
# ('pos', x, y): toca por posición (fracción del ancho y alto), para botones sin texto como el menú.
# ('texto', t): toca el botón con ese texto. ('empieza', t): el primero visible que empieza con t.
# ('espera', s): espera s segundos.
RUTA = [
    ('pos', 0.102, 0.090),            # menú ☰ de arriba a la izquierda (no tiene texto)
    ('texto', 'Horas de conexión'),
    ('espera', 4),                    # carga la página de horarios
    ('empieza', 'do '),               # el domingo de esta semana: ahí se cargan los filtros
    ('empieza', 'Filtros'),
    ('texto', '4 zonas'),             # filtro guardado
    ('espera', 2.5),                  # john: esperar 2 segundos antes de aplicar
    ('empieza', 'Aplicar filtro'),
]
PARAR = os.path.expanduser('~/.peya_parar')
DESCARGAS = os.path.expanduser('~/storage/downloads')
HORARIO = re.compile(r'^\d{1,2}:\d{2} – \d{1,2}:\d{2}')   # '17:45 – 22:00 (4h 15m)'


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


def visibles():
    """Los textos de la pantalla que se ven (la página web también trae botones ocultos, con tamaño cero)."""
    return [(t, x, y) for t, x, y, _ in textos()[0] if (x, y) != (0, 0)]


def tocar(texto, empieza=False, intentos=10):
    for _ in range(intentos):
        for t, x, y in visibles():
            if t == texto or (empieza and t.startswith(texto)):
                tocar_xy(x, y)
                pausa(2, 3.5)
                return True
        time.sleep(1.5)
    raise SystemExit('No encontré "%s" en la pantalla de PeYa Rider' % texto)


def recorrer_ruta():
    ancho, alto = tamano_pantalla()
    for paso in RUTA:
        if paso[0] == 'pos':
            tocar_xy(int(ancho * paso[1]), int(alto * paso[2]))
            pausa(2, 3.5)
        elif paso[0] == 'espera':
            pausa(paso[1], paso[1] + 1)
        else:
            tocar(paso[1], empieza=paso[0] == 'empieza')


def refrescar(ancho, alto):
    """Tira la lista hacia abajo (como con el dedo) para que se actualice."""
    x = str(int(ancho * random.uniform(0.4, 0.6)))
    adb('shell', 'input', 'swipe', x, str(int(alto * random.uniform(0.28, 0.33))),
        x, str(int(alto * random.uniform(0.7, 0.78))), str(random.randint(350, 600)))


def turnos(lista):
    """Los turnos de la lista: 'horario · zona'. La página trae la lista entera, aunque no entre en pantalla."""
    salida, textos_ = set(), [t for t, _, _, _ in lista]
    for i, t in enumerate(textos_):
        if HORARIO.match(t):
            zona = textos_[i + 1] if i + 1 < len(textos_) and textos_[i + 1] != 'Agendar' else \
                (textos_[i + 2] if i + 2 < len(textos_) else '')
            salida.add('%s · %s' % (t.split(' (')[0], zona))
    return salida


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
    if bloqueado():
        raise SystemExit('Teléfono bloqueado: desbloquealo y volvé a tocar el botón')
    if os.path.exists(PARAR):
        os.remove(PARAR)
    paquete = paquete_peya()
    adb('shell', 'am', 'force-stop', paquete)
    adb('shell', 'monkey', '-p', paquete, '-c', 'android.intent.category.LAUNCHER', '1')
    pausa(7, 10)
    recorrer_ruta()
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
