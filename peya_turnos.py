#!/usr/bin/env python3
"""Caza turnos en PeYa Rider: refresca la lista y toca "Agendar" apenas aparece un turno.

Igual que okx_ordenes.py: maneja el teléfono por ADB (depuración inalámbrica, al mismo teléfono).
1. Abre la app de cero y sigue RUTA: menú → Horas de conexión (abre en hoy; el filtro ya lo guarda la app).
2. Se queda en hoy (con --elegir N te da N segundos para tocar otro día). Lo podés cambiar cuando quieras,
   pero ojo: si cambiás a un día con turnos mientras caza, toma el primero.
3. Refresca tirando la lista hacia abajo, cada --min a --max segundos (1,5 a 2 s: tus 1.700 ms, variando un poco),
   sin fin, y entre refresco y refresco mira la pantalla todo el tiempo.
4. Después de cada refresco mira la pantalla muy seguido (una captura, sin uiautomator, que es lento)
   buscando el botón rosa "Agendar". Si aparece, lo toca en el acto y anota cuánto tardó en aparecer.
5. Solo empieza a cazar después de ver la lista vacía una vez, para no agarrar un turno que ya estaba
   (por ejemplo, los del domingo mientras elegís el día).

6. Toca "Agendar horario de conexión" en la ventana que sube, apenas deja de moverse.

Para con PARAR (notificación o el acceso directo), si bloqueás el teléfono, si la app sale de Horarios de
conexión, al tomar un turno, o al pasar --minutos (por defecto, nunca).

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
    ('espera', 4),                    # carga la página de horarios (abre en hoy)
    # Ya no hace falta: la app guarda el filtro aunque la cierres (john, 04/11). Por si algún día se pierde:
    # ('empieza', 'do '),             # el domingo de esta semana: ahí se cargan los filtros
    # ('empieza', 'Filtros'),
    # ('texto', '4 zonas'),           # filtro guardado
    # ('espera', 2.5),                # john: esperar 2 segundos antes de aplicar
    # ('empieza', 'Aplicar filtro'),
]
DOMINGO = ('empieza', 'do ')          # el ensayo va al domingo, donde siempre hay turnos

# El mismo recorrido, pero mirando colores de la pantalla (mucho más rápido que leer los textos):
# se toca apenas aparece cada cosa. (x, y) en fracción de 1080x2400, color esperado.
MAPA_LISTO = [((0.500, 0.904), (252, 214, 227))]                     # botón rosa "Ver horarios de conexión"
MENU_ABIERTO = [((0.139, 0.217), (244, 244, 244)), ((0.553, 0.208), (244, 244, 244)),  # cuadros grises
                ((0.102, 0.090), (241, 74, 128))]                    # y la cabecera rosa del menú
HORAS_DE_CONEXION = (0.553, 0.227)
HORARIOS_LISTO = [((0.056, 0.131), (23, 23, 23))]                    # pestaña negra de arriba
DIAS_X = [100, 245, 392, 540, 687, 835, 980]                          # columnas lu…do (en 1080)
DIA_Y = 0.283
DIA_ELEGIDO = (153, 0, 49)            # el cuadrado bordó del día elegido, 40 px a la izquierda del centro
DIA_ELEGIDO_Y = 0.2875                # y = 690
# El botón "Agendar" de cada turno: rosa claro (252,214,227), entre x 780 y 1040. Se busca en una columna.
ROSA = (252, 214, 227)
COLUMNA_X = 0.926                     # x = 1000 en 1080 de ancho
DESDE_Y = 0.36                        # debajo del calendario y los filtros (y = 870 en 2400)
AGENDAR_FRANJA = (0.392, 0.51)        # y 940-1225: donde está el primer botón "Agendar"
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


_SHELL = None


def tocar_xy(x, y, corrimiento=6, esperar=True):
    """Toca con un pequeño corrimiento, para que no sea siempre el mismo punto exacto.
    Con esperar=False manda el toque por una consola de ADB que queda abierta y sigue sin esperar
    (ahorra abrir ADB y esperar a que Android termine el toque: unos 0,3-0,5 s)."""
    global _SHELL
    x, y = x + random.randint(-corrimiento, corrimiento), y + random.randint(-corrimiento, corrimiento)
    if esperar:
        adb('shell', 'input', 'tap', str(x), str(y))
        return
    if _SHELL is None or _SHELL.poll() is not None:
        _SHELL = subprocess.Popen(['adb', 'shell'], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, text=True)
    _SHELL.stdin.write('input tap %d %d &\n' % (x, y))
    _SHELL.stdin.flush()


def abrir_consola():
    """Abre de antemano la consola de ADB de los toques rápidos (abrirla tarda)."""
    global _SHELL
    if _SHELL is None or _SHELL.poll() is not None:
        _SHELL = subprocess.Popen(['adb', 'shell'], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, text=True)


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


def parecido(c, color, tol):
    return abs(c[0] - color[0]) < tol and abs(c[1] - color[1]) < tol and abs(c[2] - color[2]) < tol


CONFIRMAR_Y_GUARDADA = os.path.expanduser('~/.peya_confirmar_y')   # dónde queda quieto el botón negro


class Pantalla:
    """Captura rápida de la pantalla (píxeles crudos por ADB, sin uiautomator)."""

    def __init__(self, ancho, alto):
        self.ancho, self.alto = ancho, alto
        crudo = subprocess.run(['adb', 'exec-out', 'screencap'], capture_output=True, timeout=20).stdout
        self.cabecera = len(crudo) - ancho * alto * 4      # 12 o 16 bytes según la versión de Android
        if self.cabecera not in (12, 16):
            raise SystemExit('No entiendo la captura de pantalla (%d bytes de más)' % self.cabecera)
        self.x = int(ancho * COLUMNA_X)
        self.capturas, self.tiempo = 0, 0.0
        try:
            with open(CONFIRMAR_Y_GUARDADA) as f:
                self.confirmar_y = int(f.read())
        except (OSError, ValueError):
            self.confirmar_y = int(alto * 0.842)          # y = 2020 en 2400 (captura de john)

    def captura(self, y0=0, y1=None):
        """Las filas y0..y1 de la pantalla. Se recortan en el teléfono: viaja mucho menos que la pantalla entera."""
        t = time.time()
        fila = self.ancho * 4
        if y1 is None:
            cmd = 'screencap'
            corte = self.cabecera
        else:
            cmd = 'screencap | tail -c +%d | head -c %d' % (self.cabecera + y0 * fila + 1, (y1 - y0) * fila)
            corte = 0
        d = subprocess.run(['adb', 'exec-out', cmd], capture_output=True, timeout=10).stdout[corte:]
        self.capturas += 1
        self.tiempo += time.time() - t
        return d

    def ms_por_captura(self):
        return 1000 * self.tiempo / max(1, self.capturas)

    def pixel(self, datos, fx, fy):
        i = (int(self.alto * fy) * self.ancho + int(self.ancho * fx)) * 4
        return datos[i], datos[i + 1], datos[i + 2]

    def esta(self, datos, marcas, tol=14):
        return all(parecido(self.pixel(datos, fx, fy), color, tol) for (fx, fy), color in marcas)

    def esperar(self, marcas, segundos, tol=14):
        t0 = time.time()
        while time.time() - t0 < segundos:
            if self.esta(self.captura(), marcas, tol):
                return True
        return False

    def dia_elegido(self, segundos):
        """Qué columna de día está elegida (0 = lunes … 6 = domingo), esperando hasta `segundos`."""
        t0 = time.time()
        while time.time() - t0 < segundos:
            d = self.captura()
            for i, x in enumerate(DIAS_X):
                if parecido(self.pixel(d, (x - 40) / 1080, DIA_ELEGIDO_Y), DIA_ELEGIDO, 22):
                    return i
        return None

    def buscar(self, datos, fx, color, desde_y, alto_min, tol=12, y0=0):
        """La y del centro de la primera franja de `color` (al menos alto_min píxeles) en la columna fx, o None.
        `datos` empieza en la fila y0 de la pantalla."""
        x, seguidos = int(self.ancho * fx), 0
        for fila in range(max(0, int(self.alto * desde_y) - y0), len(datos) // (self.ancho * 4)):
            i = (fila * self.ancho + x) * 4
            if parecido((datos[i], datos[i + 1], datos[i + 2]), color, tol):
                seguidos += 1
                if seguidos >= alto_min:
                    return y0 + fila - seguidos // 2 + 15   # un poco más abajo del medio de lo visto
            else:
                seguidos = 0
        return None

    def boton_agendar(self):
        """La y del primer botón rosa "Agendar" de la lista, o None. Mira solo la franja del primer turno
        (y 940-1225: con o sin "APPLIED FILTERS" arriba), que es lo que se toca."""
        y0, y1 = int(self.alto * AGENDAR_FRANJA[0]), int(self.alto * AGENDAR_FRANJA[1])
        return self.buscar(self.captura(y0, y1), COLUMNA_X, ROSA, 0, ALTO_MIN_BOTON, y0=y0)

    def boton_confirmar(self, segundos=4):
        """Espera el botón negro de la ventana de confirmación. Lo devuelve apenas está donde queda quieto
        (lo aprendido la vez anterior), sin esperar a que termine de verse todo; si no, cuando deja de moverse."""
        t0, antes = time.time(), None
        y0 = max(int(self.alto * CONFIRMAR_DESDE_Y), self.confirmar_y - 110)   # franja alrededor de donde queda
        y1 = min(self.alto, self.confirmar_y + 110)
        while time.time() - t0 < segundos:
            if os.path.exists(CONFIRMAR_Y_GUARDADA):
                y = self.buscar(self.captura(y0, y1), CONFIRMAR_X, NEGRO, 0, ALTO_MIN_CONFIRMAR, tol=16, y0=y0)
            else:   # la primera vez: toda la parte de abajo, hasta aprender dónde queda quieto
                y = self.buscar(self.captura(), CONFIRMAR_X, NEGRO, CONFIRMAR_DESDE_Y, ALTO_MIN_CONFIRMAR, tol=16)
            if y and abs(y - self.confirmar_y) <= 25:
                return y
            if y and antes and abs(y - antes) <= 4:
                with open(CONFIRMAR_Y_GUARDADA, 'w') as f:
                    f.write(str(y))
                self.confirmar_y = y
                return y
            antes = y
        return None


def ruta_rapida(pantalla, dia=None):
    """El recorrido mirando colores: toca cada cosa apenas aparece. Si algo no aparece, vuelve a leer textos."""
    a, h = pantalla.ancho, pantalla.alto
    if not pantalla.esperar(MAPA_LISTO, 20):
        log('No reconocí el mapa: sigo por textos')
        return False
    # Abrir el menú. Una notificación que baja (como "Depuración inalámbrica conectada") puede tapar el botón ☰:
    # si no se abre, se prueba deslizando desde el borde izquierdo (más abajo, no lo tapa nada) y se
    # esconden las notificaciones.
    for intento in range(4):
        if intento % 2 == 0:
            tocar_xy(int(a * RUTA[0][1]), int(h * RUTA[0][2]))
        else:
            adb('shell', 'input', 'swipe', '3', str(h // 2), str(int(a * 0.7)), str(h // 2), '250')
        if pantalla.esperar(MENU_ABIERTO, 2.5, tol=30):
            break
        adb('shell', 'cmd', 'statusbar', 'collapse')
    else:
        log('No se abrió el menú: sigo por textos')
        tocar_xy(int(a * RUTA[0][1]), int(h * RUTA[0][2]))
        tocar('Horas de conexión')
        return True
    tocar_xy(int(a * HORAS_DE_CONEXION[0]), int(h * HORAS_DE_CONEXION[1]))
    if not pantalla.esperar(HORARIOS_LISTO, 15):
        raise SystemExit('No se abrió la página de horarios')
    if pantalla.dia_elegido(15) is None:            # que cargue la fila de días antes de tocar nada
        raise SystemExit('No cargó la fila de días')
    time.sleep(0.5)
    if dia is not None:
        for _ in range(4):                          # toca el día y confirma que quedó elegido
            tocar_xy(int(DIAS_X[dia] * a / 1080), int(h * DIA_Y), corrimiento=4)
            if pantalla.dia_elegido(2) == dia:
                break
        else:
            raise SystemExit('No pude elegir el día %d' % dia)
    return True


def refrescar(ancho, alto):
    """Tira la lista hacia abajo (como con el dedo) para que se actualice. Empieza en el medio de la lista:
    arrancando arriba (sobre "APPLIED FILTERS") la página casi nunca lo tomaba como "refrescar"."""
    x = str(int(ancho * random.uniform(0.15, 0.5)))       # lejos de la columna de los botones
    adb('shell', 'input', 'swipe', x, str(int(alto * random.uniform(0.50, 0.55))),
        x, str(int(alto * random.uniform(0.86, 0.90))), str(random.randint(380, 440)))   # john: ~411 ms


def notificar(titulo, texto):
    subprocess.run(['termux-notification', '--id', 'peya-turno', '--priority', 'max', '--sound',
                    '--vibrate', '500,300,500', '--title', titulo, '--content', texto], check=False)


def foto(nombre):
    """Guarda una captura PNG en Descargas (para ver qué pasó cuando algo falla)."""
    ruta = '/sdcard/Download/' + time.strftime(nombre + '_%H%M%S.png')
    adb('shell', 'screencap', '-p', ruta)
    return ruta


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
    tocar_xy(int(pantalla.ancho * COLUMNA_X) - 80, y, corrimiento=4, esperar=False)
    yc = pantalla.boton_confirmar()
    t1 = time.time()
    if not yc:
        foto('peya_sin_confirmacion')
        return None
    if confirmar:
        tocar_xy(pantalla.ancho // 2, yc, corrimiento=4, esperar=False)
    pantalla.fin = time.time()
    if confirmar:
        time.sleep(1)   # que el toque llegue antes de seguir
    return t1 - t0, yc


def ensayo(args, ancho, alto):
    """Domingo, donde siempre hay turnos: refresca 3 veces midiendo cuánto tarda en volver "Agendar",
    lo toca y espera la ventana de confirmación. Solo con --confirmar toma el turno de verdad."""
    global ENSAYO_ESPERA_RECARGA
    ENSAYO_ESPERA_RECARGA = True
    pantalla = Pantalla(ancho, alto)
    abrir_consola()
    t0 = time.time()
    while time.time() - t0 < 10 and not pantalla.boton_agendar():   # que cargue la lista del domingo
        pass
    if not pantalla.boton_agendar():
        y0, y1 = int(alto * AGENDAR_FRANJA[0]), int(alto * AGENDAR_FRANJA[1])
        recorte = pantalla.captura(y0, y1)
        entera = pantalla.buscar(pantalla.captura(), COLUMNA_X, ROSA, DESDE_Y, ALTO_MIN_BOTON)
        return log('ENSAYO: no veo ningún "Agendar" en 10 s (recorte: %d bytes de %d esperados; en la pantalla '
                   'entera: %s; captura %s)' % (len(recorte), (y1 - y0) * ancho * 4, entera, foto('peya_sin_agendar')))
    log('ENSAYO: lista del domingo cargada a los %.1f s' % (time.time() - t0))
    for vuelta in range(1, 4):
        pausa(args.min, args.max)
        refrescar(ancho, alto)
        t_suelta = time.time()
        y, demora, desaparecio = mirar(pantalla, args.mirar)
        if vuelta == 3 and not y:
            y = pantalla.boton_agendar()   # aunque no haya recargado, si hay "Agendar" se prueba la confirmación
            if y:
                log('ENSAYO refresco 3: no recargó (captura %s), pero toco "Agendar" igual para probar la ventana'
                    % foto('peya_no_recargo'))
        elif vuelta == 3:
            log('ENSAYO refresco 3: "Agendar" volvió a los %.2f s: lo toco' % demora)
        elif not desaparecio:
            foto('peya_no_recargo')
        if y and vuelta == 3:
            r = agarrar(pantalla, y, args.confirmar)
            if not r:
                return log('ENSAYO: la ventana de confirmación no apareció en 4 s (captura peya_sin_confirmacion en Descargas)')
            log('ENSAYO: botón de confirmar listo a los %.2f s del toque (y=%d). Cada mirada a la pantalla: %d ms'
                % (r + (pantalla.ms_por_captura(),)))
            if args.confirmar:
                log('ENSAYO: CONFIRMÉ el turno. Desde que solté el refresco: %.2f s' % (pantalla.fin - t_suelta))
                notificar('PeYa: turno tomado (ensayo)', 'Fijate en Mis horas de conexión')
            else:
                log('ENSAYO: NO confirmo (sin --confirmar). Hasta acá: %.2f s desde que solté el refresco'
                    % (pantalla.fin - t_suelta))
                adb('shell', 'input', 'keyevent', 'KEYCODE_BACK')
            return
        if y:
            log('ENSAYO refresco %d: la lista se recargó y "Agendar" volvió a los %.2f s' % (vuelta, demora))
        elif not desaparecio:
            log('ENSAYO refresco %d: "Agendar" nunca se fue: tirar hacia abajo NO recargó la lista' % vuelta)
        else:
            log('ENSAYO refresco %d: la lista se borró y no volvió en %g s' % (vuelta, args.mirar))
    log('ENSAYO: en el refresco 3 no apareció "Agendar": no toqué nada')


def refrescar_rapido(ancho, alto):
    """El mismo tirón, mandado por la consola abierta sin esperar: se empieza a mirar la pantalla enseguida."""
    x = int(ancho * random.uniform(0.15, 0.5))
    y1, y2 = int(alto * random.uniform(0.50, 0.55)), int(alto * random.uniform(0.86, 0.90))
    dur = random.randint(380, 440)
    abrir_consola()
    _SHELL.stdin.write('input swipe %d %d %d %d %d &\n' % (x, y1, x, y2, dur))
    _SHELL.stdin.flush()
    return dur / 1000


def estado(texto):
    """Actualiza la notificación fija (sin esperar: tarda medio segundo)."""
    subprocess.Popen(['termux-notification', '--id', 'peya-estado', '--ongoing', '--title', 'PeYa: cazando',
                      '--content', texto, '--button1', 'PARAR', '--button1-action',
                      'sh /data/data/com.termux/files/home/bexo-scripts/telefono/peya.sh parar'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def cazar(args, ancho, alto):
    """Refresca cada --min a --max segundos, sin fin (o --minutos), mirando la pantalla todo el tiempo.
    Apenas aparece "Agendar" lo toca y confirma. El log anota un resumen cada --resumen minutos
    y todo el detalle (con capturas) cuando aparece un turno o algo sale raro."""
    pantalla = Pantalla(ancho, alto)
    abrir_consola()
    inicio = time.time()
    fin = inicio + args.minutos * 60 if args.minutos else float('inf')
    armado, vueltas, avisos_antes = False, 0, 0
    proximo_resumen = proximo_control = time.time()
    while time.time() < fin:
        if os.path.exists(PARAR):
            return log('Parado con PARAR. %d refrescos en %.0f min' % (vueltas, (time.time() - inicio) / 60))
        if time.time() >= proximo_control:      # cada 30 s: ¿sigue en la página de horarios y desbloqueado?
            proximo_control = time.time() + 30
            if bloqueado():
                return log('Teléfono bloqueado: paro. %d refrescos' % vueltas)
            if not pantalla.esta(pantalla.captura(), HORARIOS_LISTO):
                ruta = foto('peya_fuera')
                notificar('PeYa: paré', 'La app salió de Horarios de conexión')
                return log('La pantalla ya no es Horarios de conexión: paro (captura %s)' % ruta)
        if time.time() >= proximo_resumen:
            proximo_resumen = time.time() + args.resumen * 60
            texto = '%d refrescos en %.0f min · mirada %d ms · %s' % (
                vueltas, (time.time() - inicio) / 60, pantalla.ms_por_captura(),
                'cazando' if armado else 'esperando lista vacía')
            log(texto)
            estado(texto)
        t_envio = time.time()
        dur = refrescar_rapido(ancho, alto)
        vueltas += 1
        ciclo = random.uniform(args.min, args.max)
        y = None
        while time.time() - t_envio < ciclo:      # mira la pantalla hasta el próximo refresco
            y = pantalla.boton_agendar()
            if y:
                break
        if y and not armado:
            avisos_antes += 1
            if avisos_antes in (1, 20, 100):
                log('Hay turnos en pantalla desde antes: no toco nada hasta ver la lista vacía')
            continue
        if not y:
            if not armado:
                armado = True
                log('Lista vacía: empiezo a cazar (refresco %d)' % vueltas)
            continue
        visto = time.time()
        r = agarrar(pantalla, y, confirmar=True)
        suelta = t_envio + dur + 0.3            # el tirón termina ~0,3 s después de mandarlo (arranque de input)
        if not r:
            log('Toqué "Agendar" (visto %.2f s después de soltar el refresco %d) pero no vi la confirmación'
                % (visto - suelta, vueltas))
            notificar('PeYa: toqué un turno', 'No vi la ventana de confirmación: fijate vos')
            return
        log('TURNO TOMADO en el refresco %d: "Agendar" visto %.2f s después de soltar · confirmar listo %.2f s '
            'después del toque · total %.2f s · mirada %d ms'
            % (vueltas, visto - suelta, r[0], pantalla.fin - suelta, pantalla.ms_por_captura()))
        time.sleep(0.5)
        log('Captura después de confirmar:', foto('peya_tomado'))
        notificar('🛵 Turno tomado en PeYa', 'Fijate en Mis horas de conexión')
        return
    log('Pasaron %g minutos: paro. %d refrescos' % (args.minutos, vueltas))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--pantalla', action='store_true')
    ap.add_argument('--ensayo', action='store_true',
                    help='en el domingo: mide 3 refrescos, toca Agendar y guarda la confirmación SIN confirmar')
    ap.add_argument('--confirmar', action='store_true', help='en el ensayo: toma el turno de verdad')
    ap.add_argument('--sin-ruta', action='store_true', help='no abre la app: empieza a refrescar donde estés')
    ap.add_argument('--espera', type=int, default=30, help='segundos antes de guardar la pantalla (--pantalla)')
    ap.add_argument('--elegir', type=float, default=0, help='segundos para que elijas otro día antes de empezar (0 = hoy)')
    ap.add_argument('--min', type=float, default=1.5, help='espera mínima entre refrescos, en segundos')
    ap.add_argument('--max', type=float, default=2.0, help='espera máxima entre refrescos, en segundos')
    ap.add_argument('--mirar', type=float, default=4, help='segundos que mira la pantalla después de cada refresco')
    ap.add_argument('--minutos', type=float, default=0, help='cuánto tiempo caza como mucho (0 = sin fin)')
    ap.add_argument('--resumen', type=float, default=2, help='cada cuántos minutos anota un resumen en el log')
    args = ap.parse_args()
    if not conectar():
        # ADB a veces queda colgado con la conexión vieja (al apagar y prender la depuración cambia el puerto)
        adb('disconnect')
        adb('kill-server')
        time.sleep(1)
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
        t = time.time()
        if ruta_rapida(Pantalla(ancho, alto), dia=6 if args.ensayo else None):
            log('Recorrido hecho en %.1f s' % (time.time() - t))
        else:
            recorrer_ruta(ancho, alto)
            if args.ensayo:
                tocar(DOMINGO[1], empieza=True)
        if not args.ensayo and args.elegir:
            notificar('PeYa: elegí el día', 'Tenés %g segundos para tocar hoy o mañana' % args.elegir)
            time.sleep(args.elegir)
    if args.ensayo:
        log('ENSAYO en el domingo')
        ensayo(args, ancho, alto)
    else:
        log('Empiezo a cazar')
        cazar(args, ancho, alto)
