#!/usr/bin/env python3
"""Guarda los avisos (notificaciones) de plata de las apps uruguayas: MiDinero, Prex, OCA, Itaú y Mercado Pago/Libre.

No entra a ninguna app ni usa claves: solo lee las notificaciones que ya aparecen en el teléfono
(como si las miraras en la cortina). Para eso Termux:API necesita "Acceso a notificaciones".
Nada se aprueba ni se mueve: es solo lectura.

  python notifs_apps.py --ver      # muestra los avisos que hay ahora de esas apps y guarda una copia en Descargas
  python notifs_apps.py --todas    # igual, pero de TODAS las apps (para encontrar el nombre de una app)
  python notifs_apps.py            # queda corriendo: cada 60 s anota los avisos nuevos en ~/movimientos_apps.csv

Paso 1 (ahora): juntar avisos reales para ver cómo escribe cada app ("Recibiste $ 1.500 de ...").
Paso 2: con esos ejemplos, sacar fecha, monto y nombre, y mandarlos a la planilla.
"""
import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import time

CADA_S = 60
HOME = os.path.expanduser('~')
CSV = os.path.join(HOME, 'movimientos_apps.csv')
DESCARGAS = os.path.join(HOME, 'storage', 'downloads')
COLUMNAS = ['visto', 'hora_aviso', 'app', 'paquete', 'titulo', 'texto', 'monto', 'moneda', 'clave']

# Se reconoce la app por una parte del nombre del paquete (ej. uy.com.prex.app → "prex").
# Si alguna no aparece con --ver, buscala con --todas y agregá su parte acá.
APPS = {
    'midinero': 'MiDinero',
    'prex': 'Prex',
    'oca': 'OcaBlue',
    'ocablue': 'OcaBlue',
    'itau': 'Itau',
    'mercadopago': 'MercadoPago',
    'mercadolibre': 'MercadoLibre',
}

# "$ 1.500", "$U 1.500,50", "UYU 1500", "U$S 20", "USD 20,00"
MONTO = re.compile(r'(U\$S|US\$|USD|\$U|UYU|\$)\s?(\d{1,3}(?:[.\s]\d{3})+(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?)')


def app_de(paquete):
    """'uy.com.prex.app' → 'Prex'. None si no es una de las apps."""
    for parte in (paquete or '').lower().split('.'):
        if parte in APPS:
            return APPS[parte]
    return None


def leer_avisos():
    r = subprocess.run(['termux-notification-list'], capture_output=True, text=True, timeout=30)
    if r.returncode != 0 or not r.stdout.strip():
        raise SystemExit('termux-notification-list no respondió. ¿Le diste "Acceso a notificaciones" a Termux:API?\n'
                         + (r.stderr or '').strip())
    return json.loads(r.stdout)


def monto_de(texto):
    """Primer monto del texto → (número, moneda). Formato uruguayo: punto de miles, coma decimal."""
    m = MONTO.search(texto or '')
    if not m:
        return '', ''
    moneda = 'USD' if m.group(1) in ('U$S', 'US$', 'USD') else 'UYU'
    num = m.group(2).replace(' ', '')
    if ',' in num:
        num = num.replace('.', '').replace(',', '.')
    elif re.fullmatch(r'\d{1,3}(\.\d{3})+', num):
        num = num.replace('.', '')
    return num, moneda


def clave_de(n):
    """Misma notificación = misma clave, aunque la veamos en varias vueltas."""
    base = '|'.join(str(n.get(k, '')) for k in ('packageName', 'when', 'title', 'content'))
    return hashlib.sha1(base.encode('utf-8')).hexdigest()[:16]


def claves_guardadas():
    if not os.path.exists(CSV):
        return set()
    with open(CSV, newline='', encoding='utf-8') as f:
        return {fila['clave'] for fila in csv.DictReader(f)}


def guardar(filas):
    nuevo = not os.path.exists(CSV)
    with open(CSV, 'a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS)
        if nuevo:
            w.writeheader()
        w.writerows(filas)


def fila_de(n, app):
    texto = n.get('content') or ''
    monto, moneda = monto_de((n.get('title') or '') + ' ' + texto)
    return {'visto': time.strftime('%Y-%m-%d %H:%M:%S'), 'hora_aviso': n.get('when', ''), 'app': app,
            'paquete': n.get('packageName', ''), 'titulo': n.get('title', ''), 'texto': texto,
            'monto': monto, 'moneda': moneda, 'clave': clave_de(n)}


def ver(todas):
    avisos = leer_avisos()
    elegidos = [n for n in avisos if todas or app_de(n.get('packageName'))]
    print('Avisos en el teléfono: %d. De las apps: %d.' % (len(avisos), len(elegidos)))
    for n in elegidos:
        f = fila_de(n, app_de(n.get('packageName')) or '-')
        print('\n[%s] %s  (%s)\n  %s\n  %s\n  → monto: %s %s'
              % (f['app'], f['hora_aviso'], f['paquete'], f['titulo'], f['texto'], f['monto'] or '?', f['moneda']))
    if os.path.isdir(DESCARGAS):
        ruta = os.path.join(DESCARGAS, 'avisos_apps_%s.json' % time.strftime('%Y%m%d_%H%M'))
        with open(ruta, 'w', encoding='utf-8') as f:
            json.dump(elegidos, f, ensure_ascii=False, indent=1)
        print('\nCopia guardada en Descargas: %s' % os.path.basename(ruta))


def vigilar():
    vistas = claves_guardadas()
    print('%s Vigilando avisos cada %d s → %s' % (time.strftime('%d/%m %H:%M'), CADA_S, CSV), flush=True)
    while True:
        try:
            nuevas = []
            for n in leer_avisos():
                app = app_de(n.get('packageName'))
                if app and clave_de(n) not in vistas:
                    nuevas.append(fila_de(n, app))
                    vistas.add(nuevas[-1]['clave'])
            if nuevas:
                guardar(nuevas)
                for f in nuevas:
                    print('%s %s %s %s | %s' % (f['visto'][5:16], f['app'], f['monto'] or '?', f['titulo'], f['texto']),
                          flush=True)
        except Exception as e:  # que una vuelta fallida no corte la vigilancia; queda en el log
            print('%s Error: %s' % (time.strftime('%d/%m %H:%M'), e), flush=True)
        time.sleep(CADA_S)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--ver', action='store_true', help='muestra los avisos de las apps y sale')
    p.add_argument('--todas', action='store_true', help='como --ver, pero de todas las apps')
    a = p.parse_args()
    if a.ver or a.todas:
        ver(a.todas)
    else:
        vigilar()
