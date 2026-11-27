#!/usr/bin/env python3
"""Graba las pantallas de CUALQUIER app mientras hacés el camino a mano (para armar un recorrido nuevo sin adivinar).

  python ~/bexo-scripts/telefono/grabar_app.py mercantil        # 120 s
  python ~/bexo-scripts/telefono/grabar_app.py mercantil 180    # más tiempo

Guarda cada pantalla nueva (xml + captura) en Descargas/grabacion_<nombre>_HHMMSS/ y un resumen.txt, y al final
deja Descargas/grabacion_<nombre>_HHMMSS.tgz listo para mandar con qué app
estaba al frente y los textos de cada pantalla. Vibra largo al empezar, cortito con cada pantalla y dos veces al terminar.
Después de cada toque esperá la vibración cortita (2-3 s). Solo mira: no toca nada.
Ojo: las apps de bancos a veces dan la captura en negro (la protegen); el xml igual sirve.
La carpeta tiene tus saldos y cuentas: mandala por acá, nunca al repo (limpiar_telefono.py la borra en el grupo 1).
"""
import os
import sys
import tarfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import binance_orden as b  # noqa: E402  (volcar, leer_nodos, firma, vibrar, adb, conectar)


def grabar(nombre, segundos=120, espera_inicio=5):
    if not b.conectar():
        raise SystemExit('No hay ADB: reconectá (notificación RECONECTAR) y probá de nuevo')
    b.PAQ = None                       # todas las apps, no solo Binance
    carpeta_n = 'grabacion_%s_%s' % (nombre, time.strftime('%H%M%S'))
    carpeta = os.path.join(b.LOG_DIR, carpeta_n)
    os.makedirs(carpeta, exist_ok=True)
    b.adb('shell', 'mkdir', '-p', '/sdcard/Download/' + carpeta_n)
    print('Grabando %d s en Descargas/%s. Abrí la app y hacé el camino; después de cada toque esperá la vibración.'
          % (segundos, carpeta_n), flush=True)
    for i in range(espera_inicio, 0, -1):
        print('  empiezo en %d…' % i, flush=True)
        time.sleep(1)
    b.vibrar(400)
    ultima, n, fin, resumen = None, 0, time.time() + segundos, []
    while time.time() < fin:
        xml = b.volcar(10, 1)
        ns = b.leer_nodos(xml)
        f = b.firma(ns)
        if ns and f != ultima:
            ultima, n = f, n + 1
            with open(os.path.join(carpeta, '%02d.xml' % n), 'w') as fx:
                fx.write(xml)
            b.adb('shell', 'screencap', '-p', '/sdcard/Download/%s/%02d.png' % (carpeta_n, n))
            app = b.al_frente()
            resumen.append('%02d  %s\n    %s' % (n, app, b.que_veo(ns)))
            b.vibrar(60)
            print('  pantalla %d: %s' % (n, b.que_veo(ns)[:80]), flush=True)
        time.sleep(0.5)
    with open(os.path.join(carpeta, 'resumen.txt'), 'w') as fr:
        fr.write('\n'.join(resumen) + '\n')
    b.vibrar(300)
    time.sleep(0.6)
    b.vibrar(300)
    tgz = os.path.join(b.LOG_DIR, carpeta_n + '.tgz')   # listo para mandar, sin otro comando
    with tarfile.open(tgz, 'w:gz') as t:
        t.add(carpeta, arcname=carpeta_n)
    print('Listo: %d pantallas. Mandá Descargas/%s.tgz' % (n, carpeta_n))
    return carpeta, n


if __name__ == '__main__':
    a = sys.argv[1:]
    if not a or not a[0].replace('_', '').isalnum():
        print(__doc__)
        sys.exit(2)
    grabar(a[0], int(a[1]) if len(a) > 1 and a[1].isdigit() else 120)
