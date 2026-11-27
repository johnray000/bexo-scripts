#!/usr/bin/env python3
"""Prueba telefono/grabar_app.py sin teléfono (pantallas grabadas de Binance como si fueran otra app).
   python3 pruebas/probar_grabar_app.py <carpeta con xml>"""
import glob
import itertools
import os
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, 'telefono'))
sys.path.insert(0, RAIZ)
import binance_orden as b  # noqa: E402
import grabar_app  # noqa: E402

xmls = [open(f).read() for f in sorted(glob.glob(os.path.join(sys.argv[1], '*.xml')))[:3]]
secuencia = itertools.chain([xmls[0], xmls[0], xmls[1], xmls[1], xmls[2]], itertools.repeat(xmls[2]))
tmp = tempfile.mkdtemp()
b.LOG_DIR, b.conectar, b.adb = tmp, (lambda: True), (lambda *a, **k: '')
b.volcar, b.vibrar, b.al_frente = (lambda *a: next(secuencia)), (lambda ms: None), (lambda: 'mCurrentFocus=app.de.prueba')
carpeta, n = grabar_app.grabar('prueba', segundos=4, espera_inicio=0)
ok = os.path.exists(carpeta + '.tgz') and n == 3 and len(glob.glob(os.path.join(carpeta, '*.xml'))) == 3 and 'app.de.prueba' in open(os.path.join(carpeta, 'resumen.txt')).read()
print('%s: guarda solo las pantallas nuevas (%d) con resumen' % ('BIEN' if ok else 'MAL', n))
sys.exit(0 if ok else 1)
