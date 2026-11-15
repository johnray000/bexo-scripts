#!/usr/bin/env python3
"""Prueba binance_orden.py SIN teléfono, contra las pantallas grabadas con --grabar.

  python3 pruebas/simular_binance.py CARPETA_GRABACION

CARPETA_GRABACION tiene 01.xml … 05.xml de la grabación del 15/11/2026 (no está en el repo porque muestra saldos:
está en los archivos del proyecto, p2p/binance_app/grabacion/). Simula los toques: portada P2P (04) → panel Filtrar
(03) → Confirmar → Vender de PrincessYor → "Vender USDT" (05). Tiene que terminar en (True, True) y con
"Por seguridad no toqué Realizar Orden". Corre también el caso con la moneda en ARS (abre 01, toca VES).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.argv, CARPETA = sys.argv[:1], sys.argv[1]
import binance_orden as b  # noqa: E402

X = {k: open(os.path.join(CARPETA, '%s.xml' % k)).read() for k in ('01', '03', '04', '05')}
X['04ars'] = X['04'].replace('text="VES" resource-id="com.binance.dev:id/2131446692"',
                             'text="ARS" resource-id="com.binance.dev:id/2131446692"')


def correr(inicio):
    st = {'s': inicio, 'escrito': []}

    def adb(*a, espera=60, salida=True):
        if a[:2] == ('exec-out', 'uiautomator'):
            return X[st['s']]
        if a[:3] == ('shell', 'input', 'tap'):
            x, y, s = int(a[3]), int(a[4]), st['s']
            if s == '04ars' and 258 < y < 333 and x > 896:
                st['s'] = '01'                      # moneda → Seleccionar divisa
            elif s == '01' and 595 < y < 652 and x < 152:
                st['s'] = '04'                      # VES
            elif s == '04' and 355 < y < 455 and 267 < x < 407:
                st['s'] = '03'                      # filtro de monto → panel Filtrar
            elif s == '03' and 1430 < y < 1530 and x > 550:
                st['s'] = '04'                      # Confirmar
            elif s == '04' and 814 < y < 874 and x > 842:
                st['s'] = '05'                      # Vender de PrincessYor
        if a[:3] == ('shell', 'input', 'text'):
            st['escrito'].append(a[3])
        if a[:3] == ('shell', 'dumpsys', 'window'):
            return 'mCurrentFocus=Window{1 u0 com.binance.dev/x}'
        if a[:3] == ('shell', 'pm', 'list'):
            return 'package:com.binance.dev'
        return ''
    b.adb = adb
    b.time.sleep = lambda s: None
    b.tamano_pantalla = lambda: (1080, 2400)
    b.guardar = lambda n: 'x'
    b.T.en_orden = False
    b.paquete_binance()
    b.abrir_p2p('com.binance.dev')
    m = {'id': 'PagoMovil', 'nombre': 'Pago Movil'}
    b.preparar_lista(m, 5000)
    b.buscar_en_lista('PrincessYor')
    print('resultado:', b.completar_orden({'apodo': 'PrincessYor'}, m, 5000), 'escrito:', st['escrito'])
    try:
        b.T.xy('Realizar Orden', 1, 1)
        print('MAL: tocó Realizar Orden')
    except b.Frenado as e:
        print('bien:', e)


for inicio in ('04', '04ars'):
    print('==== empezando con moneda %s' % ('VES' if inicio == '04' else 'ARS'))
    correr(inicio)
