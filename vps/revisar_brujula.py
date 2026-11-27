#!/usr/bin/env python3
"""Revisión de la Brújula P2P en el VPS: qué tiene guardado, de cuándo es y qué falló.
Lo corre john cuando algo no cierra y le pasa la salida a Claude:
    sudo python3 /opt/dashboard-p2p/revisar_brujula.py
Solo lee: data.json, yo_binance.json, la config (sin mostrar la clave) y el estado del servicio."""
import json
import os
import subprocess
import time

CARPETA = os.path.dirname(os.path.abspath(__file__))


def leer(nombre):
    try:
        with open(os.path.join(CARPETA, nombre), encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        return {'_error': str(e)}


def hace(seg):
    if seg is None:
        return '—'
    m = (time.time() - seg) / 60
    return f'hace {m:.0f} min' if m < 90 else f'hace {m / 60:.1f} h'


print('== Servicio')
r = subprocess.run(['systemctl', 'is-active', 'dashboard-p2p'], capture_output=True, text=True)
print('dashboard-p2p:', r.stdout.strip() or r.stderr.strip())
env = {}
try:
    with open('/etc/dashboard-p2p.env') as f:
        for linea in f:
            if '=' in linea:
                k, v = linea.strip().split('=', 1)
                env[k] = v
except OSError as e:
    print('No pude leer /etc/dashboard-p2p.env:', e)
print('Puerto:', env.get('DASH_PUERTO', '?'), '| botón al teléfono (ntfy):', 'sí' if env.get('DASH_NTFY_TEMA') else 'NO configurado')

d = leer('data.json')
print('\n== Último cálculo')
if '_error' in d:
    print('data.json:', d['_error'])
else:
    s = d.get('servidor') or {}
    print('Pedido a la planilla:', 'bien' if s.get('ok') else 'FALLÓ: ' + str(s.get('error')), '|', hace(s.get('hora')))
    print('Números de la planilla del:', d.get('generadoTexto', '—'))
    b = s.get('binance') or {}
    print('Binance en vivo:', b.get('encontrados'), 'grupos con anuncio visible de', b.get('grupos'),
          '| usuario:', b.get('usuario') or '—', '|', b.get('error') or 'sin error')
    t = s.get('telefono') or {}
    print('Último pedido al teléfono:', hace(t.get('pedido')) if t.get('pedido') else 'nunca')
    print('\n== Subidas de órdenes')
    for x in d.get('subidas') or []:
        print(f"{x['fuente']:8} {x.get('cuando') or '—':12} {'ATRASADA' if x.get('atrasada') else ''}")
    print('\n== Revisión de datos (ok / ojo / mal)')
    for x in d.get('revision') or [{'estado': '?', 'prueba': 'revisión', 'detalle': 'el Apps Script todavía no la manda'}]:
        print(f"[{x['estado']:3}] {x['prueba']}: {x['detalle']}")
    print('\n== Anuncios')
    for a in d.get('anuncios') or []:
        print(f"{a['ex']:8} {a['tipo']:6} {a['cripto']:4} {a.get('precio')} {a.get('accion'):8} fuente={a.get('fuente')}")
yo = leer('yo_binance.json')
print('\nUsuario de Binance aprendido:', yo.get('apodo') or yo.get('_error'))
