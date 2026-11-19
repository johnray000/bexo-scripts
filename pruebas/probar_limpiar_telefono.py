#!/usr/bin/env python3
"""Prueba telefono/limpiar_telefono.py sobre un teléfono falso (carpetas temporales):
   python3 pruebas/probar_limpiar_telefono.py"""
import os
import sys
import tempfile
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, 'telefono'))
import limpiar_telefono as L  # noqa: E402

bien = n = 0


def ver(nombre, ok, detalle=''):
    global bien, n
    n += 1
    bien += bool(ok)
    print('%s %s%s' % ('BIEN' if ok else 'MAL ', nombre, ' · ' + str(detalle) if detalle else ''))


base = tempfile.mkdtemp()
interno, desc = os.path.join(base, 'shared'), os.path.join(base, 'shared', 'Download')


def poner(ruta, dias, tam=1000):
    r = os.path.join(interno, ruta)
    os.makedirs(os.path.dirname(r), exist_ok=True)
    with open(r, 'wb') as f:
        f.write(b'x' * tam)
    t = time.time() - dias * 86400 - 60
    os.utime(r, (t, t))
    return r


WA = 'Android/media/com.whatsapp/WhatsApp/Media/'
poner('Download/binance_filtrar_172132.png', 2)
poner('Download/binance_filtrar_172132.xml', 2)
poner('Download/binance_grabacion_153012/0001.xml', 3)
poner('Download/grabacion_binance_simulador.tgz', 4)
poner('Download/chats_waha.json.gz', 2)
poner('Download/prex_entradas.csv', 90)            # protegido
poner('Download/okx_enlaces.txt', 90)              # protegido
poner('Download/factura_luz.pdf', 45)              # tuyo viejo
poner('Download/contrato.pdf', 5)                  # tuyo nuevo
poner('Download/MisFotos/viaje.jpg', 200)          # carpeta tuya: nunca
poner('DCIM/Screenshots/Screenshot_1.png', 1)
poner('Pictures/Screenshots/Screenshot_2.png', 30)
poner(WA + 'WhatsApp Images/IMG-1.jpg', 0)         # hoy: no se ofrece
poner(WA + 'WhatsApp Images/IMG-2.jpg', 5)
poner(WA + 'WhatsApp Images/Sent/IMG-3.jpg', 5)
poner(WA + 'WhatsApp Images/.nomedia', 50)
poner(WA + 'WhatsApp Documents/comprobante.pdf', 10)
poner('WhatsApp Business/Media/WhatsApp Business Images/IMG-4.jpg', 8)   # Business, ruta vieja

g = L.grupos(interno, desc)
nombres = lambda i: sorted(os.path.basename(x[0]) for x in g[i][1])  # noqa: E731
ver('1 pruebas y fallas (archivos + carpeta de grabación + tgz + chats)', nombres(0) == sorted([
    'binance_filtrar_172132.png', 'binance_filtrar_172132.xml', 'binance_grabacion_153012',
    'grabacion_binance_simulador.tgz', 'chats_waha.json.gz']), nombres(0))
ver('2 capturas recientes', nombres(1) == ['Screenshot_1.png'], nombres(1))
ver('3 capturas viejas', nombres(2) == ['Screenshot_2.png'], nombres(2))
ver('4 WhatsApp recibidas de más de 2 días (sin la de hoy ni .nomedia, con Business)',
    nombres(3) == ['IMG-2.jpg', 'IMG-4.jpg'], nombres(3))
ver('5 WhatsApp mandadas', nombres(4) == ['IMG-3.jpg'], nombres(4))
ver('6 documentos de WhatsApp', nombres(5) == ['comprobante.pdf'], nombres(5))
ver('7 tus archivos viejos (no protegidos, no carpetas, no nuevos)', nombres(6) == ['factura_luz.pdf'], nombres(6))
ver('los protegidos no aparecen en ningún grupo',
    not any('entradas.csv' in x[0] or 'okx_enlaces' in x[0] for _, l in g for x in l))

respuestas = iter(['1 4', 'no'])
ver('sin escribir BORRAR no borra', L.menu(g, lambda p: next(respuestas)) == 0 and
    os.path.exists(os.path.join(desc, 'chats_waha.json.gz')))
respuestas = iter(['1, 4', 'BORRAR'])
hechos = L.menu(g, lambda p: next(respuestas))
ver('borra los grupos elegidos', hechos == 7 and not os.path.exists(os.path.join(desc, 'binance_grabacion_153012'))
    and not os.path.exists(os.path.join(interno, WA, 'WhatsApp Images/IMG-2.jpg')), hechos)
ver('no toca lo demás', all(os.path.exists(os.path.join(interno, r)) for r in (
    'Download/prex_entradas.csv', 'Download/okx_enlaces.txt', 'Download/MisFotos/viaje.jpg', 'Download/contrato.pdf',
    WA + 'WhatsApp Images/IMG-1.jpg', 'DCIM/Screenshots/Screenshot_1.png', WA + 'WhatsApp Images/Sent/IMG-3.jpg')))
respuestas = iter(['', ''])
ver('Enter = nada', L.menu(L.grupos(interno, desc), lambda p: next(respuestas)) == 0)
print('%d de %d bien' % (bien, n))
sys.exit(0 if bien == n else 1)
