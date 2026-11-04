#!/usr/bin/env python3
"""Caza turnos en PeYa Rider: refresca la lista y toca "Agendar" apenas aparece un turno.

Igual que okx_ordenes.py: maneja el teléfono por ADB (depuración inalámbrica, al mismo teléfono).
1. Abre la app de cero y sigue RUTA: menú → Horas de conexión → domingo → Filtros → 4 zonas → Aplicar.
2. Te da --elegir segundos para que toques el día que querés (hoy, mañana…). Lo podés cambiar cuando quieras.
3. Refresca tirando la lista hacia abajo, cada --min a --max segundos (1,5 a 2 s: tus 1.700 ms, variando un poco).
4. Después de cada refresco mira la pantalla muy seguido (una captura, sin uiautomator, que es lento)
   buscando el botón rosa "Agendar". Si aparece, lo toca en el acto y anota cuánto tardó en aparecer.
5. Solo empieza a cazar después de ver la lista vacía una vez, para no agarrar un turno que ya estaba
   (por ejemplo, los del domingo mientras elegís el día).

6. Toca "Agendar horario de conexión" en la ventana que sube, apenas deja de moverse.

Para con PARAR (notificación o el acceso directo), al pasar --minutos, si bloqueás el teléfono, o al tomar un turno.

  python peya_turnos.py --pantalla    # guarda lo que hay en pantalla en Descargas
  python peya_turnos.py --ensayo      # en el domingo (siempre hay turnos): mide, toca Agendar y NO confirma
  python peya_turnos.py --ensayo --confirmar   # igual, pero toma el turno de verdad
  python peya_turnos.py               # lo corre telefono/peya.sh (acceso directo del escritorio)
"""
import argparse
import os
import random
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from okx_ordenes import adb, bloqueado, conectar, tamano_pantalla, textos  # noqa: E402

PAQUETE = 'com.logistics.rider.pedidosya'
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
# El botón "Agendar" de cada turno: rosa claro (252,214,227), entre x 780 y 1040. Se busca en una columna.
ROSA = (252, 214, 227)
COLUMNA_X = 0.926                     # x = 1000 en 1080 de ancho
DESDE_Y = 0.36                        # debajo del calendario y los filtros (y = 870 en 2400)
ALTO_MIN_BOTON = 40                   # píxeles rosas seguidos para contar como botón (el botón mide ~110)
# La ventana "Reservar este horario de conexión?": botón negro (23,23,23) "Agendar horario de conexión",
# de lado a lado, abajo (y 1970-2110 en 2400). El fondo oscurecido es gris (89,89,89), no negro.
NEGRO = (23, 23, 23)
CONFIRMAR_X = 0.12                    # x = 130: a la izquierda del texto blanco del botón
CONFIRMAR_DESDE_Y = 0.60
ALTO_MIN_CONFIRMAR = 60               # el botón mide ~140
PARAR = os.path.expanduser('~/.peya_parar')
DESCARGAS = os.path.expanduser('~/storage/downloads')


def pausa(a, b):
    time.sleep(random.uniform(a, b))


def tocar_xy(x, y, corrimiento=6):
    """Toca con un pequeño corrimiento, para que no sea siempre el mismo punto exacto."""
    adb('shell', 'input', 'tap', str(x + random.randint(-corrimiento, corrimiento)),
        str(y + random.randint(-corrimiento, corrimiento)))


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


def recorrer_ruta(ancho, alto):
    for paso in RUTA:
        if paso[0] == 'pos':
            tocar_xy(int(ancho * paso[1]), int(alto * paso[2]))
            pausa(2, 3.5)
        elif paso[0] == 'espera':
            pausa(paso[1], paso[1] + 1)
        else:
            tocar(paso[1], empieza=paso[0] == 'empieza')


class Pantalla:
    """Captura rápida: pide solo la parte de abajo de la pantalla y mira una columna de píxeles."""

    def __init__(self, ancho, alto):
        self.ancho, self.alto = ancho, alto
        crudo = subprocess.run(['adb', 'exec-out', 'screencap'], capture_output=True, timeout=20).stdout
        self.cabecera = len(crudo) - ancho * alto * 4      # 12 o 16 bytes según la versión de Android
        if self.cabecera not in (12, 16):
            raise SystemExit('No entiendo la captura de pantalla (%d bytes de más)' % self.cabecera)
        self.y0 = int(alto * DESDE_Y)
        self.x = int(ancho * COLUMNA_X)
        inicio = self.cabecera + self.y0 * ancho * 4
        self.cmd = ['adb', 'exec-out', 'screencap | tail -c +%d' % (inicio + 1)]

    def captura(self):
        return subprocess.run(self.cmd, capture_output=True, timeout=10).stdout

    def buscar(self, datos, fx, color, desde_y, alto_min, tol=12):
        """La y del centro de la primera franja de `color` (al menos alto_min píxeles) en la columna fx, o None."""
        x, seguidos = int(self.ancho * fx), 0
        primera = max(0, int(self.alto * desde_y) - self.y0)
        for fila in range(primera, len(datos) // (self.ancho * 4)):
            i = (fila * self.ancho + x) * 4
            if abs(datos[i] - color[0]) < tol and abs(datos[i + 1] - color[1]) < tol and abs(datos[i + 2] - color[2]) < tol:
                seguidos += 1
                if seguidos >= alto_min:
                    return self.y0 + fila - seguidos // 2 + 15   # un poco más abajo del medio de lo visto
            else:
                seguidos = 0
        return None

    def boton_agendar(self):
        """La y del primer botón rosa "Agendar" de la lista, o None."""
        return self.buscar(self.captura(), COLUMNA_X, ROSA, DESDE_Y, ALTO_MIN_BOTON)

    def boton_confirmar(self, segundos=4):
        """Espera la ventana de confirmación y devuelve la y de su botón negro cuando deja de moverse
        (la ventana sube con una animación: se toca apenas está quieta). None si no aparece."""
        t0, antes = time.time(), None
        while time.time() - t0 < segundos:
            y = self.buscar(self.captura(), CONFIRMAR_X, NEGRO, CONFIRMAR_DESDE_Y, ALTO_MIN_CONFIRMAR, tol=16)
            if y and antes and abs(y - antes) <= 4:
                return y
            antes = y
        return None


def refrescar(ancho, alto):
    """Tira la lista hacia abajo (como con el dedo) para que se actualice."""
    x = str(int(ancho * random.uniform(0.15, 0.5)))       # lejos de la columna de los botones
    adb('shell', 'input', 'swipe', x, str(int(alto * random.uniform(0.40, 0.44))),
        x, str(int(alto * random.uniform(0.70, 0.76))), str(random.randint(180, 260)))


def notificar(titulo, texto):
    subprocess.run(['termux-notification', '--id', 'peya-turno', '--priority', 'max', '--sound',
                    '--vibrate', '500,300,500', '--title', titulo, '--content', texto], check=False)


def guardar_pantalla(nombre):
    lista, xml = textos()
    ruta = os.path.join(DESCARGAS, time.strftime(nombre + '_%H%M%S.xml'))
    with open(ruta, 'w') as f:
        f.write(xml)
    return ruta, lista


def log(*cosas):
    print(time.strftime('%H:%M:%S'), *cosas, flush=True)


def mirar(pantalla, segundos):
    """Después de un refresco: mira la pantalla hasta ver "Agendar" o hasta que pasen `segundos`.
    Devuelve (y del botón o None, segundos hasta verlo, si el botón desapareció en algún momento)."""
    t0, desaparecio = time.time(), False
    while time.time() - t0 < segundos:
        y = pantalla.boton_agendar()
        if y and (desaparecio or not ENSAYO_ESPERA_RECARGA):
            return y, time.time() - t0, desaparecio
        if not y:
            desaparecio = True
    return None, time.time() - t0, desaparecio


ENSAYO_ESPERA_RECARGA = False   # en el ensayo se espera a que la lista se borre y vuelva (prueba que recargó)


def agarrar(pantalla, y, confirmar):
    """Toca "Agendar" y, si `confirmar`, toca "Agendar horario de conexión" apenas la ventana queda quieta.
    Devuelve cuánto tardó cada parte (o None si la ventana no apareció)."""
    t0 = time.time()
    tocar_xy(int(pantalla.ancho * COLUMNA_X) - 80, y, corrimiento=4)
    yc = pantalla.boton_confirmar()
    t1 = time.time()
    if not yc:
        guardar_pantalla('peya_confirmar')
        return None
    if confirmar:
        tocar_xy(pantalla.ancho // 2, yc, corrimiento=4)
    return t1 - t0, yc


def ensayo(args, ancho, alto):
    """Domingo, donde siempre hay turnos: refresca 3 veces midiendo cuánto tarda en volver "Agendar",
    lo toca y espera la ventana de confirmación. Solo con --confirmar toma el turno de verdad."""
    global ENSAYO_ESPERA_RECARGA
    ENSAYO_ESPERA_RECARGA = True
    pantalla = Pantalla(ancho, alto)
    if not pantalla.boton_agendar():
        return log('ENSAYO: no veo ningún "Agendar" en pantalla. ¿Estás en el domingo, con turnos?')
    for vuelta in range(1, 4):
        pausa(args.min, args.max)
        refrescar(ancho, alto)
        t_suelta = time.time()
        y, demora, desaparecio = mirar(pantalla, args.mirar)
        if y and vuelta == 3:
            log('ENSAYO refresco 3: "Agendar" volvió a los %.2f s: lo toco' % demora)
            r = agarrar(pantalla, y, args.confirmar)
            if not r:
                return log('ENSAYO: la ventana de confirmación no apareció en 4 s (pantalla guardada en Descargas)')
            log('ENSAYO: la ventana de confirmación quedó quieta a los %.2f s del toque (botón en y=%d)' % r)
            if args.confirmar:
                log('ENSAYO: CONFIRMÉ el turno. Desde que solté el refresco: %.2f s' % (time.time() - t_suelta))
                notificar('PeYa: turno tomado (ensayo)', 'Fijate en Mis horas de conexión')
            else:
                log('ENSAYO: NO confirmo (sin --confirmar). Hasta acá: %.2f s desde que solté el refresco'
                    % (time.time() - t_suelta))
                adb('shell', 'input', 'keyevent', 'KEYCODE_BACK')
            return
        if y:
            log('ENSAYO refresco %d: la lista se recargó y "Agendar" volvió a los %.2f s' % (vuelta, demora))
        elif not desaparecio:
            log('ENSAYO refresco %d: "Agendar" nunca se fue: tirar hacia abajo NO recargó la lista' % vuelta)
        else:
            log('ENSAYO refresco %d: la lista se borró y no volvió en %g s' % (vuelta, args.mirar))
    log('ENSAYO: en el refresco 3 no apareció "Agendar": no toqué nada')


def cazar(args, ancho, alto):
    pantalla = Pantalla(ancho, alto)
    fin = time.time() + args.minutos * 60
    armado, vueltas = False, 0
    while time.time() < fin:
        if os.path.exists(PARAR):
            return log('Parado con PARAR. %d refrescos' % vueltas)
        if bloqueado():
            return log('Teléfono bloqueado: paro. %d refrescos' % vueltas)
        refrescar(ancho, alto)
        vueltas += 1
        y, demora, _ = mirar(pantalla, args.mirar)
        if y and not armado:
            # todavía hay turnos de antes (o estás eligiendo el día): no se toca nada
            if vueltas % 10 == 1:
                log('Hay turnos en pantalla desde antes: espero a ver la lista vacía para empezar a cazar')
        elif y:
            r = agarrar(pantalla, y, confirmar=True)
            if not r:
                log('Toqué "Agendar" (a los %.2f s del refresco) pero no vi la confirmación' % demora)
                notificar('PeYa: toqué un turno', 'No vi la ventana de confirmación: fijate vos')
                return
            log('TURNO TOMADO: "Agendar" a los %.2f s del refresco, confirmación %.2f s después (refresco %d)'
                % (demora, r[0], vueltas))
            notificar('🛵 Turno tomado en PeYa', 'Fijate en Mis horas de conexión')
            return
        elif not armado:
            armado = True
            log('Lista vacía: empiezo a cazar (refresco %d)' % vueltas)
        pausa(args.min, args.max)
    log('Pasaron %g minutos: paro. %d refrescos' % (args.minutos, vueltas))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--pantalla', action='store_true')
    ap.add_argument('--ensayo', action='store_true',
                    help='en el domingo: mide 3 refrescos, toca Agendar y guarda la confirmación SIN confirmar')
    ap.add_argument('--confirmar', action='store_true', help='en el ensayo: toma el turno de verdad')
    ap.add_argument('--sin-ruta', action='store_true', help='no abre la app: empieza a refrescar donde estés')
    ap.add_argument('--espera', type=int, default=30, help='segundos antes de guardar la pantalla (--pantalla)')
    ap.add_argument('--elegir', type=float, default=10, help='segundos para elegir el día después del filtro')
    ap.add_argument('--min', type=float, default=1.5, help='espera mínima entre refrescos, en segundos')
    ap.add_argument('--max', type=float, default=2.0, help='espera máxima entre refrescos, en segundos')
    ap.add_argument('--mirar', type=float, default=4, help='segundos que mira la pantalla después de cada refresco')
    ap.add_argument('--minutos', type=float, default=60, help='cuánto tiempo caza como mucho')
    args = ap.parse_args()
    if not conectar():
        raise SystemExit('Sin ADB: activá Depuración inalámbrica (Opciones de desarrollador) y que haya wifi')
    if args.pantalla:
        print('En %d segundos guarda lo que haya en pantalla: dejá PeYa en la pantalla que quieras.' % args.espera,
              flush=True)
        time.sleep(args.espera)
        ruta, lista = guardar_pantalla('peya_pantalla')
        subprocess.run(['termux-vibrate'], check=False)
        print('\n'.join(t for t, _, _, _ in lista))
        print('\nGuardado en', ruta)
        sys.exit(0)
    if bloqueado():
        raise SystemExit('Teléfono bloqueado: desbloquealo y volvé a tocar el acceso directo')
    if os.path.exists(PARAR):
        os.remove(PARAR)
    ancho, alto = tamano_pantalla()
    if not args.sin_ruta:
        adb('shell', 'am', 'force-stop', PAQUETE)
        adb('shell', 'monkey', '-p', PAQUETE, '-c', 'android.intent.category.LAUNCHER', '1')
        pausa(7, 9)
        recorrer_ruta(ancho, alto)
        if not args.ensayo:   # el ensayo se queda en el domingo, donde termina el recorrido
            notificar('PeYa: elegí el día', 'Tenés %g segundos para tocar hoy o mañana' % args.elegir)
            time.sleep(args.elegir)
    if args.ensayo:
        log('ENSAYO en el domingo')
        ensayo(args, ancho, alto)
    else:
        log('Empiezo a cazar')
        cazar(args, ancho, alto)
