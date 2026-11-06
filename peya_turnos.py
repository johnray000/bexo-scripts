#!/usr/bin/env python3
"""Caza turnos en PeYa Rider: refresca la lista y toca "Agendar" apenas aparece un turno.

Igual que okx_ordenes.py: maneja el teléfono por ADB (depuración inalámbrica, al mismo teléfono).
1. Abre la app de cero y sigue RUTA: menú → Horas de conexión (abre en hoy; el filtro ya lo guarda la app).
2. Se queda en hoy (con --elegir N te da N segundos para tocar otro día). Lo podés cambiar cuando quieras,
   pero ojo: si cambiás a un día con turnos mientras caza, toma el primero.
3. Refresca tirando la lista hacia abajo, cada --min a --max segundos (2,7 a 3,2 s: tus 1.700 ms + 1,2 s, variando un poco),
   sin fin, y entre refresco y refresco mira la pantalla todo el tiempo.
4. Después de cada refresco mira la pantalla muy seguido (una captura, sin uiautomator, que es lento)
   buscando el botón rosa "Agendar". Si aparece, lo toca en el acto y anota cuánto tardó en aparecer.
5. Solo empieza a cazar después de ver la lista vacía una vez, para no agarrar un turno que ya estaba
   (por ejemplo, los del domingo mientras elegís el día).

6. Toca "Agendar horario de conexión" en la ventana que sube, apenas deja de moverse.

Pausa con BAJAR VOLUMEN x2, al bloquear el teléfono o al salir de PeYa (sigue a los 5 s de volver a Horarios).
Para del todo con PARAR DEL TODO (notificación o el acceso directo), a los --pausa-max min de pausa, o si sale de Horarios de
conexión, al tomar un turno, o al pasar --minutos (por defecto, nunca).

  python peya_turnos.py --pantalla    # guarda lo que hay en pantalla en Descargas
  python peya_turnos.py --estadisticas   # métricas de todos los intentos (~/peya_intentos.csv)
  python peya_turnos.py --ensayo      # en el domingo (siempre hay turnos): mide, toca Agendar y NO confirma
  python peya_turnos.py --ensayo --confirmar   # igual, pero toma el turno de verdad
  python peya_turnos.py               # lo corre telefono/peya.sh (acceso directo del escritorio)
"""
import argparse
import gzip
import os
import random
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from okx_ordenes import adb, adb_bytes, bloqueado, conectar, tamano_pantalla, textos  # noqa: E402

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
# El mapa: el ícono ☰ (raya negra en el medio, blanco arriba y al costado). Antes era el botón rosa de abajo,
# pero ese cambia (por ejemplo cuando ya tenés un turno agendado) y el script caía al método lento.
MAPA_LISTO = [((0.102, 0.0896), (22, 22, 22)), ((0.102, 0.0729), (255, 255, 255)),
              ((0.139, 0.104), (255, 255, 255))]
MENU_ABIERTO = [((0.139, 0.217), (244, 244, 244)), ((0.553, 0.208), (244, 244, 244)),  # cuadros grises
                ((0.102, 0.090), (241, 74, 128))]                    # y la cabecera rosa del menú
HORAS_DE_CONEXION = (0.553, 0.227)
HORARIOS_LISTO = [((0.056, 0.131), (23, 23, 23))]                    # pestaña negra de arriba
DIAS_X = [100, 245, 392, 540, 687, 835, 980]                          # columnas lu…do (en 1080)
DIA_Y = 0.283
DIAS = {'lu': 0, 'lunes': 0, 'ma': 1, 'martes': 1, 'mi': 2, 'miercoles': 2, 'miércoles': 2, 'ju': 3, 'jueves': 3,
        'vi': 4, 'viernes': 4, 'sa': 5, 'sá': 5, 'sabado': 5, 'sábado': 5, 'do': 6, 'domingo': 6}


def columna_dia(texto):
    """'hoy', 'mañana' o un día de la semana → columna 0 (lunes) … 6 (domingo) de la semana que se ve."""
    t = texto.strip().lower()
    hoy = time.localtime().tm_wday
    if t == 'hoy':
        return hoy
    if t in ('mañana', 'manana'):
        col = hoy + 1
    elif t in DIAS:
        col = DIAS[t]
    else:
        raise SystemExit('No entiendo el día "%s" (hoy, mañana, lunes … domingo)' % texto)
    if col > 6 or col < hoy:
        raise SystemExit('"%s" es de la semana que viene: por ahora solo caza en la semana que se ve' % texto)
    return col
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
# El cartel de abajo después de confirmar: verde "Has agendado correctamente…" o rojo con el error
# (por ejemplo "Shift not contain PENDING swap": otro lo tomó antes). Se mira en x = 30, y = 2232.
CARTEL = (0.028, 0.93)
VERDE = (0, 124, 4)
ROJO = (192, 36, 37)
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


class SinADB(Exception):
    pass


def parecido(c, color, tol):
    return abs(c[0] - color[0]) < tol and abs(c[1] - color[1]) < tol and abs(c[2] - color[2]) < tol


CONFIRMAR_Y_GUARDADA = os.path.expanduser('~/.peya_confirmar_y')   # dónde queda quieto el botón negro


class Pantalla:
    """Captura rápida de la pantalla (píxeles crudos por ADB, sin uiautomator)."""

    def __init__(self, ancho, alto):
        self.ancho, self.alto = ancho, alto
        crudo = subprocess.run(['adb', 'exec-out', 'screencap'], capture_output=True, timeout=20).stdout
        self.cabecera = len(crudo) - ancho * alto * 4      # 12 o 16 bytes según la versión de Android
        if not crudo:
            raise SystemExit('ADB no devuelve la pantalla: apagá y prendé la Depuración inalámbrica y arrancá de nuevo')
        if self.cabecera not in (12, 16):
            raise SystemExit('No entiendo la captura de pantalla (%d bytes de más)' % self.cabecera)
        self.x = int(ancho * COLUMNA_X)
        self.capturas, self.tiempo = 0, 0.0
        # Comprimir en el teléfono: la franja que se mira es casi toda blanca, 1,2 MB pasan a ~20 KB.
        # Mucho menos para cifrar y mandar por ADB (eso era buena parte del calor).
        try:
            self.gzip = gzip.decompress(adb_bytes('exec-out', 'echo peya | gzip -1', espera=5)) == b'peya\n'
        except (OSError, EOFError, subprocess.TimeoutExpired, gzip.BadGzipFile):
            self.gzip = False
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
            if self.gzip:
                cmd += ' | gzip -1'
        esperado = ((y1 if y1 is not None else self.alto) - y0) * fila
        for _ in range(3):   # a veces ADB devuelve la captura cortada: se pide de nuevo
            try:
                d = adb_bytes('exec-out', cmd, espera=4)
                if self.gzip and y1 is not None:
                    d = gzip.decompress(d) if d else b''
                d = d[corte:]
            except (subprocess.TimeoutExpired, OSError, EOFError, gzip.BadGzipFile):
                d = b''
            if len(d) >= esperado:
                break
        else:
            if not d:
                raise SinADB()                  # no llegó nada: se cortó la conexión de ADB
            d = d + bytes(esperado - len(d))   # lo que falte, en negro: no se toma por ningún botón
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

    def cartel(self, segundos=4):
        """Después de confirmar: 'verde' (tomado), 'rojo' (error) o None si no apareció ningún cartel."""
        y = int(self.alto * CARTEL[1])
        t0 = time.time()
        while time.time() - t0 < segundos:
            c = self.pixel(self.captura(y, y + 1), CARTEL[0], 0)
            if parecido(c, VERDE, 30):
                return 'verde'
            if parecido(c, ROJO, 35):
                return 'rojo'
        return None

    def en_horarios_rapido(self):
        """¿Está PeYa en Horarios de conexión? Mira una sola fila (la pestaña negra de arriba): es muy barato.
        Si no la ve, vuelve a mirar una vez antes de decir que no (una captura puede fallar)."""
        y = int(self.alto * HORARIOS_LISTO[0][0][1])
        for _ in range(2):
            try:
                fila = self.captura(y, y + 1)
            except SinADB:
                raise
            if parecido(self.pixel(fila, HORARIOS_LISTO[0][0][0], 0), HORARIOS_LISTO[0][1], 25):
                return True
            time.sleep(0.3)
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
            tocar_xy(int(a * HORAS_DE_CONEXION[0]), int(h * HORAS_DE_CONEXION[1]))
            break
        adb('shell', 'cmd', 'statusbar', 'collapse')
    else:
        log('No se abrió el menú: sigo por textos')
        tocar_xy(int(a * RUTA[0][1]), int(h * RUTA[0][2]))
        tocar('Horas de conexión')
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
    subprocess.run(['termux-notification', '--id', 'peya-turno', '--priority', 'max', '--title', titulo, '--content', texto], check=False)


def anunciar(frase):
    """Pitido agudo y fuerte y DESPUÉS la voz (si arrancan juntos la voz corta el pitido). En otro hilo, para
    no frenar nada; el script espera a que termine antes de salir."""
    import threading

    def sonar():
        pitido('turno')
        subprocess.run(['termux-tts-speak', frase], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    threading.Thread(target=sonar).start()


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


def bloque(titulo, *filas):
    """Un evento en varias líneas cortas (la consola del teléfono es angosta):
    14:41:15 ❌ Intento 1: otro lo tomó
             Agendar visto    0.45 s
    """
    print(time.strftime('%H:%M:%S'), titulo, flush=True)
    for f in filas:
        print(' ' * 9 + f, flush=True)


INTENTOS_CSV = os.path.expanduser('~/peya_intentos.csv')   # todos los intentos, de todas las cazas


def registrar(intento):
    """Agrega el intento al historial (para --estadisticas)."""
    nuevo = not os.path.exists(INTENTOS_CSV)
    with open(INTENTOS_CSV, 'a') as f:
        if nuevo:
            f.write('fecha,hora,refresco,visto,confirmar,total,resultado,mirada_ms\n')
        num = lambda v: '' if v is None else '%.2f' % v
        f.write('%s,%s,%d,%s,%s,%s,%s,%d\n' % (
            time.strftime('%Y-%m-%d'), time.strftime('%H:%M:%S'), intento['refresco'], num(intento['visto']),
            num(intento['confirmar']), num(intento['total']), intento['resultado'], intento['mirada']))


def prom(lista, campo):
    v = [i[campo] for i in lista if i.get(campo) is not None]
    return sum(v) / len(v) if v else None


def lineas_metricas(intentos):
    """Las líneas de métricas de una lista de intentos: tomados vs fallidos, y en qué parte se pierde tiempo."""
    tomados = [i for i in intentos if i['resultado'] == 'tomado']
    fallidos = [i for i in intentos if i['resultado'] != 'tomado']
    filas = ['Intentos: %d · ✅ %d · ❌ %d' % (len(intentos), len(tomados), len(fallidos))]
    motivos = {}
    for i in fallidos:
        motivos[i['resultado']] = motivos.get(i['resultado'], 0) + 1
    if motivos:
        filas.append('  ' + ' · '.join('%s %d' % (m, n) for m, n in sorted(motivos.items())))
    for nombre, grupo in (('✅', tomados), ('❌', [i for i in fallidos if i['total'] is not None])):
        if grupo:
            filas.append('%s visto %.2f · conf %.2f · tot %.2f' % (
                nombre, prom(grupo, 'visto'), prom(grupo, 'confirmar'), prom(grupo, 'total')))
    con_total = [i['total'] for i in intentos if i['total'] is not None]
    if con_total:
        filas.append('Mejor %.2f s · peor %.2f s' % (min(con_total), max(con_total)))
    return filas


def resumen_final(inicio, vueltas, intentos, pantalla):
    minutos = (time.time() - inicio) / 60
    bloque('📊 Resumen', '%d refrescos en %.0f min (%.0f/min)' % (vueltas, minutos, vueltas / max(minutos, 0.01)),
           'Mirada: %d ms' % pantalla.ms_por_captura(),
           *(lineas_metricas(intentos) if intentos else ['Sin intentos']))


def estadisticas():
    """Resumen de todos los intentos guardados, en total y por día."""
    import csv
    try:
        with open(INTENTOS_CSV) as f:
            filas = list(csv.DictReader(f))
    except OSError:
        return print('Todavía no hay intentos guardados')
    for i in filas:
        for c in ('visto', 'confirmar', 'total'):
            i[c] = float(i[c]) if i[c] not in ('', 'None') else None
    bloque('📊 Todos los intentos', *lineas_metricas(filas))
    for dia in sorted({i['fecha'] for i in filas}):
        bloque('📅 ' + dia, *lineas_metricas([i for i in filas if i['fecha'] == dia]))


def corto(ruta):
    return os.path.basename(ruta)


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
        y, demora, desaparecio = mirar(pantalla, max(4, args.mirar))
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
            log('ENSAYO refresco %d: la lista se borró y no volvió en %g s' % (vuelta, max(4, args.mirar)))
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


VOLUMEN_X2 = [0]   # cuántas veces apretaste bajar volumen x2


def vigilar_volumen():
    """Botón de parar: apretar BAJAR VOLUMEN dos veces rápido. Escucha los botones físicos por ADB (los toques del script
    no pasan por ahí) y, al ver bajar volumen, deja el aviso de parar."""
    import threading
    proc = subprocess.Popen(['adb', 'shell', 'getevent', '-lq'], stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True)

    ultimo = [0.0]

    def escuchar():
        for linea in proc.stdout:
            if 'KEY_VOLUMEDOWN' in linea and 'DOWN' in linea.split('KEY_VOLUMEDOWN')[1]:
                ahora = time.time()
                if ahora - ultimo[0] < 0.7:      # dos toques rápidos: uno solo no hace nada (podés bajar el volumen)
                    VOLUMEN_X2[0] += 1           # pausa (o sigue, si ya estaba en pausa)
                    ultimo[0] = 0.0
                else:
                    ultimo[0] = ahora
    threading.Thread(target=escuchar, daemon=True).start()
    return proc


class Vigia:
    """Dos miradas a la pantalla en paralelo, desfasadas: ve el botón "Agendar" cada ~0,12 s en vez de
    cada ~0,24 s (cada captura tarda lo mismo, pero se superponen)."""

    def __init__(self, pantalla, hilos=2):
        import threading
        self.pantalla, self.y, self.error = pantalla, None, None
        self.on, self.hallado = threading.Event(), threading.Event()
        for i in range(hilos):
            threading.Thread(target=self._mirar, args=(i * 0.12,), daemon=True).start()

    def _mirar(self, desfase):
        time.sleep(desfase)
        while True:
            self.on.wait()
            try:
                y = self.pantalla.boton_agendar()
            except SinADB as e:
                self.error = e
                self.hallado.set()
                continue
            if y and self.on.is_set():
                self.y = y
                self.hallado.set()

    def mirar(self, segundos):
        """Mira hasta `segundos`; devuelve la y de "Agendar" o None."""
        self.y = None
        self.hallado.clear()
        self.on.set()
        self.hallado.wait(segundos)
        self.on.clear()
        if self.error:
            e, self.error = self.error, None
            raise e
        return self.y


DIA_CAZA = ['hoy']
SCRIPT_SH = '/data/data/com.termux/files/home/bexo-scripts/telefono/peya.sh'


def estado(texto, como='cazando'):
    """La notificación fija dice siempre en qué está: cazando, en pausa o parado.
    Cazando o en pausa tiene el botón PARAR; parado tiene CAZAR DE NUEVO (mismo día)."""
    titulo = {'cazando': '🟢 PeYa: cazando (%s)', 'pausa': '⏸ PeYa: EN PAUSA (%s)',
              'parado': '⏹ PeYa: PARADO (%s)'}[como] % DIA_CAZA[0]
    cmd = ['termux-notification', '--id', 'peya-estado', '--title', titulo, '--content', texto]
    if como == 'parado':
        cmd += ['--button1', 'CAZAR DE NUEVO', '--button1-action', 'sh %s %s' % (SCRIPT_SH, DIA_CAZA[0])]
    else:
        cmd += ['--ongoing', '--button1', 'PARAR DEL TODO', '--button1-action', 'sh %s parar' % SCRIPT_SH]
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def pitido(tipo='turno'):
    """Dos sonidos distintos, a volumen máximo (después vuelve el volumen como estaba):
    turno → tres pitidos agudos cortos (3200 Hz) · error → dos tonos graves largos que bajan (900 → 500 Hz).
    Espera a que termine de sonar."""
    import json, math, struct, wave
    if tipo != 'turno':
        tipo = 'error'
    tonos = {'turno': [(3200, 0.22), (0, 0.08)] * 3,
             'error': [(900, 0.45), (0, 0.12), (500, 0.6)]}[tipo]
    ruta = os.path.expanduser('~/.peya_sonido_%s.wav' % tipo)
    tasa = 44100
    if not os.path.exists(ruta):
        muestras = []
        for hz, seg in tonos:
            for i in range(int(tasa * seg)):
                # onda cuadrada: suena más fuerte y "chillona" que una senoidal al mismo volumen
                muestras.append(0 if hz == 0 else (32000 if math.sin(2 * math.pi * hz * i / tasa) >= 0 else -32000))
        with wave.open(ruta, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(tasa)
            w.writeframes(struct.pack('<%dh' % len(muestras), *muestras))
    antes = None
    try:
        for v in json.loads(subprocess.run(['termux-volume'], capture_output=True, text=True, timeout=5).stdout):
            if v.get('stream') == 'music':
                antes = v['volume']
                subprocess.run(['termux-volume', 'music', str(v['max_volume'])], timeout=5)
    except Exception:
        pass
    subprocess.run(['termux-media-player', 'play', ruta], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(sum(seg for _, seg in tonos) + 0.4)
    if antes is not None:
        subprocess.run(['termux-volume', 'music', str(antes)], check=False)


def en_horarios(pantalla):
    """¿Sigue en Horarios de conexión? Mira la pestaña negra de arriba o el día elegido, y solo dice que no
    después de 3 miradas seguidas (1 s entre cada una): una captura cortada o un tirón en curso no cuentan."""
    for intento in range(3):
        d = pantalla.captura()
        if pantalla.esta(d, HORARIOS_LISTO, tol=25):
            return True
        if any(parecido(pantalla.pixel(d, (x - 40) / 1080, DIA_ELEGIDO_Y), DIA_ELEGIDO, 22) for x in DIAS_X):
            return True
        time.sleep(1)
    return False


def cazar(args, ancho, alto):
    """Refresca cada --min a --max segundos, sin fin (o --minutos), mirando la pantalla todo el tiempo.
    Apenas aparece "Agendar" lo toca y confirma. El log anota un resumen cada --resumen minutos
    y todo el detalle (con capturas) cuando aparece un turno o algo sale raro."""
    pantalla = Pantalla(ancho, alto)
    abrir_consola()
    while True:
        volumen = vigilar_volumen()
        try:
            return _cazar(args, ancho, alto, pantalla)
        except SinADB:
            bloque('⚠️  Se cortó ADB', 'Reconectando…')
        finally:
            volumen.kill()
        global _SHELL
        _SHELL = None
        for _ in range(3):
            if conectar():
                break
            time.sleep(5)
        else:
            estado('Se cortó ADB (¿se apagó la Depuración inalámbrica?)', 'parado')
            pitido('error')
            return bloque('⏹  Sin ADB: paro', 'Prendé la Depuración', 'inalámbrica y arrancá', 'de nuevo')
        bloque('✅ Reconectado: sigo cazando')
        abrir_consola()


def _cazar(args, ancho, alto, pantalla):
    inicio = time.time()
    fin = inicio + args.minutos * 60 if args.minutos else float('inf')
    armado, vueltas, avisos_antes, intentos, pausa_hasta = False, 0, 0, 0, 0
    proximo_resumen = time.time()
    vigia = Vigia(pantalla)
    pausado, pausa_desde, manual, salio, en_peya_desde = False, 0, False, False, 0
    vol_visto = VOLUMEN_X2[0]
    historial = []   # los intentos de esta caza
    while time.time() < fin:
        if os.path.exists(PARAR):
            log('⏹  Parado')
            estado('Arrancá de nuevo desde el acceso directo o con el botón. %d refrescos, %d intentos'
                   % (vueltas, intentos), 'parado')
            return resumen_final(inicio, vueltas, historial, pantalla)
        if VOLUMEN_X2[0] != vol_visto:              # bajar volumen x2: pausa (o sigue, si ya estaba en pausa)
            vol_visto = VOLUMEN_X2[0]
            subprocess.Popen(['termux-vibrate', '-d', '80'], stdout=subprocess.DEVNULL,   # vibrita corta: tomó el gesto
                             stderr=subprocess.DEVNULL)
            if pausado:
                pausado = False
                log('▶  Sigo (bajar volumen x2)')
                estado('Cazando de nuevo')
                armado = False
                continue
            pausado, pausa_desde, manual, salio, en_peya_desde = True, time.time(), True, False, 0
            log('⏸  Pausa (bajar volumen x2)')
            estado('Para seguir: bajar volumen x2, o salí de PeYa y volvé a Horarios 5 s. '
                   'Se para sola a los %g min' % args.pausa_max, 'pausa')
            continue
        if pausado:
            if time.time() - pausa_desde > args.pausa_max * 60:
                log('⏹  %g min en pausa: paro' % args.pausa_max)
                estado('%g min en pausa. Arrancá de nuevo desde el acceso directo o con el botón' % args.pausa_max,
                       'parado')
                return resumen_final(inicio, vueltas, historial, pantalla)
            if pantalla.en_horarios_rapido():
                # sigue después de 5 s seguidos en Horarios; si la pausa fue con el volumen, además tenés que
                # haber salido de PeYa (si no, la pausa con volumen no serviría de nada)
                if manual and not salio:
                    time.sleep(1)
                    continue
                en_peya_desde = en_peya_desde or time.time()
                if time.time() - en_peya_desde >= 5:
                    pausado, armado = False, False      # al volver espera ver la lista vacía otra vez
                    log('▶  Sigo cazando')
                    estado('Cazando de nuevo')
                    continue
            else:
                salio, en_peya_desde = True, 0
            time.sleep(1)
            continue
        if not pantalla.en_horarios_rapido():   # saliste de PeYa (inicio, otra app) o bloqueaste el teléfono
            pausado, pausa_desde, manual, salio, en_peya_desde = True, time.time(), False, True, 0
            log('⏸  Pausa: PeYa no está en Horarios')
            estado('Volvé a PeYa → Horarios y sigue sola a los 5 s. Se para sola a los %g min' % args.pausa_max,
                   'pausa')
            continue
        if time.time() >= proximo_resumen:
            proximo_resumen = time.time() + args.resumen * 60
            texto = '%d refrescos · %.0f min · %d intentos' % (vueltas, (time.time() - inicio) / 60, intentos)
            log('🔄 %s · %d ms' % (texto, pantalla.ms_por_captura()))
            estado(texto)
        t_envio = time.time()
        dur = refrescar_rapido(ancho, alto)
        vueltas += 1
        ciclo = random.uniform(args.min, args.max)
        # La lista solo cambia al refrescar: se mira desde el tirón hasta que terminó de cargar (--mirar s después
        # de soltar) y el resto del ciclo se descansa. Mirar todo el tiempo recalentaba el teléfono y cansaba ADB.
        time.sleep(max(0, dur - 0.05))     # mientras arrastra la lista no puede cambiar: no se mira
        y = vigia.mirar(min(ciclo, dur + args.mirar) - (time.time() - t_envio))
        if not y:
            time.sleep(max(0, ciclo - (time.time() - t_envio)))
        if y and vueltas <= pausa_hasta:
            continue
        if y and not armado:
            avisos_antes += 1
            if avisos_antes in (1, 20, 100):
                bloque('⏸  Hay turnos desde antes', 'Espero ver la lista vacía')
            continue
        if not y:
            if not armado:
                armado = True
                bloque('🎯 Lista vacía: cazando')
            continue
        visto = time.time()
        r = agarrar(pantalla, y, confirmar=True)
        suelta = t_envio + dur + 0.3            # el tirón termina ~0,3 s después de mandarlo (arranque de input)
        intentos += 1
        if not r:
            intento = dict(refresco=vueltas, visto=visto - suelta, confirmar=None, total=None,
                           resultado='sin ventana', mirada=pantalla.ms_por_captura())
            historial.append(intento)
            registrar(intento)
            log('❌ #%d sin ventana · visto %.2f s · %s' % (intentos, visto - suelta, corto(foto('peya_sin_confirmacion'))))
            adb('shell', 'input', 'keyevent', 'KEYCODE_BACK')
            pausa_hasta = vueltas + 2
            continue
        tiempos = ('Agendar visto   %.2f s' % (visto - suelta),
                   'Confirmar listo %.2f s' % r[0],
                   'Total           %.2f s' % (pantalla.fin - suelta))
        corto_t = '%.2f+%.2f=%.2f s' % (visto - suelta, r[0], pantalla.fin - suelta)
        resultado = pantalla.cartel()
        intento = dict(refresco=vueltas, visto=visto - suelta, confirmar=r[0], total=pantalla.fin - suelta,
                       resultado={'verde': 'tomado', 'rojo': 'otro'}.get(resultado, 'sin cartel'),
                       mirada=pantalla.ms_por_captura())
        historial.append(intento)
        registrar(intento)
        if resultado == 'verde':
            bloque('✅ TURNO TOMADO (intento %d)' % intentos, *tiempos, 'Refresco %d' % vueltas)
            resumen_final(inicio, vueltas, historial, pantalla)
            notificar('🛵 Turno tomado en PeYa', 'Fijate en Mis horas de conexión')
            anunciar('Turno tomado en Pedidos Ya')
            estado('¡Turno tomado! Fijate en Mis horas de conexión', 'parado')
            return
        if resultado != 'rojo':   # sin cartel es raro: se guarda qué había en pantalla
            corto_t += ' · ' + corto(foto('peya_sin_cartel'))
        log('❌ #%d %s · %s' % (intentos, intento['resultado'], corto_t))
        estado('Intento %d falló (%s). Sigo cazando' % (intentos, 'otro lo tomó' if resultado == 'rojo' else 'sin cartel'))
        time.sleep(0.5)
        if pantalla.buscar(pantalla.captura(), CONFIRMAR_X, NEGRO, CONFIRMAR_DESDE_Y, ALTO_MIN_CONFIRMAR, tol=16):
            adb('shell', 'input', 'keyevent', 'KEYCODE_BACK')   # quedó abierta la ventana: se cierra
        # el turno fallido puede seguir un momento en la lista: 2 refrescos sin tocar y después,
        # a la primera lista vacía (o si no, igual), se vuelve a cazar
        pausa_hasta = vueltas + 2
    log('⏹  Pasaron %g min: paro' % args.minutos)
    resumen_final(inicio, vueltas, historial, pantalla)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--pantalla', action='store_true')
    ap.add_argument('--estadisticas', action='store_true', help='resumen de todos los intentos guardados')
    ap.add_argument('--ensayo', action='store_true',
                    help='en el domingo: mide 3 refrescos, toca Agendar y guarda la confirmación SIN confirmar')
    ap.add_argument('--confirmar', action='store_true', help='en el ensayo: toma el turno de verdad')
    ap.add_argument('--sin-ruta', action='store_true', help='no abre la app: empieza a refrescar donde estés')
    ap.add_argument('--espera', type=int, default=30, help='segundos antes de guardar la pantalla (--pantalla)')
    ap.add_argument('--dia', default='hoy', help='hoy, mañana o un día de esta semana (jueves, vi, …)')
    ap.add_argument('--elegir', type=float, default=0, help='segundos para que elijas otro día antes de empezar (0 = hoy)')
    ap.add_argument('--min', type=float, default=3.2, help='espera mínima entre refrescos, en segundos')
    ap.add_argument('--max', type=float, default=3.7, help='espera máxima entre refrescos, en segundos')
    ap.add_argument('--mirar', type=float, default=1.8,
                    help='segundos que mira la pantalla después de soltar cada refresco (después descansa)')
    ap.add_argument('--minutos', type=float, default=0, help='cuánto tiempo caza como mucho (0 = sin fin)')
    ap.add_argument('--pausa-max', type=float, default=10, help='minutos en pausa antes de parar del todo')
    ap.add_argument('--resumen', type=float, default=10, help='cada cuántos minutos anota un resumen en el log')
    args = ap.parse_args()
    if args.estadisticas:
        estadisticas()
        sys.exit(0)
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
        dia = 6 if args.ensayo else columna_dia(args.dia)
        if ruta_rapida(Pantalla(ancho, alto), dia=None if dia == time.localtime().tm_wday else dia):
            log('🛵 Recorrido: %.1f s' % (time.time() - t))
        else:
            recorrer_ruta(ancho, alto)
            if dia != time.localtime().tm_wday:
                p = Pantalla(ancho, alto)
                p.dia_elegido(15)
                for _ in range(4):
                    tocar_xy(int(DIAS_X[dia] * ancho / 1080), int(alto * DIA_Y), corrimiento=4)
                    if p.dia_elegido(2) == dia:
                        break
        if not args.ensayo and args.elegir:
            notificar('PeYa: elegí el día', 'Tenés %g segundos para tocar hoy o mañana' % args.elegir)
            time.sleep(args.elegir)
    if args.ensayo:
        log('ENSAYO en el domingo')
        ensayo(args, ancho, alto)
    else:
        DIA_CAZA[0] = args.dia
        bloque('▶  Empiezo a cazar: %s' % args.dia, 'Pausa: bajar volumen x2', 'Parar: botón de la notificación')
        estado('Arrancando')
        cazar(args, ancho, alto)
