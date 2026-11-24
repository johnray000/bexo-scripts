#!/usr/bin/env python3
"""Prueba sin red bexo_ntfy.py y telefono/escuchar_ntfy.py:  python3 pruebas/probar_ntfy_telefono.py"""
import json
import os
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, 'telefono'))
import bexo_ntfy  # noqa: E402
import escuchar_ntfy as esc  # noqa: E402

bien = n = 0


def ver(nombre, ok, detalle=''):
    global bien, n
    n += 1
    bien += bool(ok)
    print('%s %s%s' % ('BIEN' if ok else 'MAL ', nombre, ' · ' + str(detalle) if detalle else ''))


# bexo_ntfy: sin archivo de tema no manda nada; con tema manda JSON al tema
mandados = []
bexo_ntfy.urllib.request.urlopen = lambda req, timeout=10: mandados.append(json.loads(req.data)) or \
    type('R', (), {'read': lambda self: b''})()
bexo_ntfy.ARCHIVO_TEMA = '/no/existe'
ver('sin ~/.bexo-ntfy no manda', bexo_ntfy.publicar('t', 'x', esperar=True) is False and not mandados)
tmp = tempfile.NamedTemporaryFile('w', delete=False)
tmp.write('bexo-prueba\n')
tmp.close()
bexo_ntfy.ARCHIVO_TEMA = tmp.name
bexo_ntfy.publicar('Binance: me frené ⚠️', 'motivo', 4, esperar=True)
ver('con tema manda al tema con prioridad', mandados and mandados[0]['topic'] == 'bexo-prueba' and
    mandados[0]['priority'] == 4 and mandados[0]['title'] == 'Binance: me frené ⚠️', mandados)

# escuchar_ntfy.procesar
corridos, avisos = [], []
esc.correr_binance = corridos.append
esc.publicar = lambda *a, **k: avisos.append(a)
L = 'https://c2c.binance.com/es-LA/adv?code=1295&monto=5000&pago=PagoMovil&alt=11,22'
ahora = 1_000_000.0
ver('link nuevo → arma', esc.procesar({'message': L, 'time': ahora - 3}, ahora) == 'binance' and corridos == [L])
ver('link viejo (3 min) → ignora', esc.procesar({'message': L, 'time': ahora - 180}, ahora) == 'viejo' and len(corridos) == 1)
ver('otra cosa → desconocido', esc.procesar({'message': 'rm -rf /', 'time': ahora}, ahora) == 'desconocido' and
    len(corridos) == 1)
ver('link de otro sitio → desconocido', esc.procesar({'message': 'https://evil.com/?code=1', 'time': ahora}, ahora) ==
    'desconocido')
ver('link con espacios y salto → arma el link limpio',
    esc.procesar({'message': '  ' + L + '\n', 'time': ahora}, ahora) == 'binance' and corridos[-1] == L)
# botones del final del recorrido (Rearmar / FIN)
import urllib.parse  # noqa: E402
FIN = 'https://script.google.com/macros/s/X/exec?p2p=fin&id=MOV-77&k=clave'
LF = L + '&mov=MOV-77&fin=' + urllib.parse.quote(FIN, safe='')
b = bexo_ntfy.botones_orden(LF)
ver('Rearmar: POST del mismo link al tema de comandos', b and b[0]['label'] == '🔁 Rearmar' and
    b[0]['url'] == 'https://ntfy.sh/bexo-prueba-cmd' and b[0]['body'] == LF and b[0]['clear'] is False, b and b[0])
ver('FIN: GET a la dirección que vino en el link', len(b) == 2 and b[1]['label'] == '✅ FIN' and b[1]['url'] == FIN, b)
ver('sin fin= (prueba a mano): solo Rearmar', [x['label'] for x in bexo_ntfy.botones_orden(L)] == ['🔁 Rearmar'])
ver('sin link: sin botones', bexo_ntfy.botones_orden(None) == [])
ver('el link con mov y fin lo acepta el teléfono', esc.procesar({'message': LF, 'time': ahora}, ahora) == 'binance' and
    corridos[-1] == LF)
mandados.clear()
bexo_ntfy.publicar('ORDEN LISTA', 'x', 5, esperar=True, acciones=b)
ver('los botones viajan en el aviso', mandados and [a['label'] for a in mandados[0]['actions']] == ['🔁 Rearmar', '✅ FIN'])
os.unlink(tmp.name)
print('%d de %d bien' % (bien, n))
sys.exit(0 if bien == n else 1)
