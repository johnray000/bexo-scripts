#!/usr/bin/env python3
"""Libera espacio en el teléfono: lo que dejaron las pruebas, capturas de pantalla y fotos/documentos de WhatsApp.

  python ~/bexo-scripts/telefono/limpiar_telefono.py          # menú: muestra los grupos, elegís números, confirmás
  python ~/bexo-scripts/telefono/limpiar_telefono.py --ver 4  # lista los archivos del grupo 4 (no borra)

Nunca borra sin que escribas BORRAR, y nunca toca los datos que usan los scripts (PROTEGIDOS).
Las fotos de WhatsApp de hoy y ayer no se ofrecen (puede haber algo pendiente). Lo que se borra no vuelve:
los comprobantes igual quedan en Drive/WAHA.
Necesita termux-setup-storage (una vez). Python 3.8, sin librerías extra.
"""
import os
import re
import shutil
import subprocess
import sys
import time

INTERNO = os.path.expanduser('~/storage/shared')
DESCARGAS = os.path.expanduser('~/storage/downloads')
DIA = 86400
DIAS_WHATSAPP = 2          # fotos y documentos de WhatsApp: se ofrecen los de más de 2 días
DIAS_CAPTURAS = 14         # capturas de pantalla: "recientes" (las pruebas) y "más viejas"
DIAS_DESCARGAS = 30        # tus archivos en Descargas

# Datos que leen o escriben los scripts: NUNCA se borran.
PROTEGIDOS = re.compile(r'^(prex|mercadopago|itau|ocablue)_entradas\.csv$|^okx_enlaces\.txt$')
# Lo que dejan los scripts y las pruebas en Descargas.
DE_SCRIPTS = re.compile(
    r'^(binance_|okx_fallo_|okx_pantalla_|peya_|prex_ingreso|prex_fallo|oca_fallo|oca_trabado|itau_fallo|'
    r'itau_trabado|mp_fallo|grabacion|chats_waha)[^/]*\.(png|jpg|xml|tgz|txt|gz|json)$|\.tgz$')
CARPETAS_DE_SCRIPTS = re.compile(r'^(binance_grabacion(_\d+)?|grabacion[^/]*)$')

CAPTURAS = ['DCIM/Screenshots', 'Pictures/Screenshots', 'DCIM/Capturas de pantalla']
# WhatsApp y WhatsApp Business, en la ruta nueva (Android 11+) y en la vieja
WHATSAPP = [r for app, carpeta in (('com.whatsapp', 'WhatsApp'), ('com.whatsapp.w4b', 'WhatsApp Business'))
            for r in ('Android/media/%s/%s/Media' % (app, carpeta), '%s/Media' % carpeta)]
FOTOS_WA = ('WhatsApp Images', 'WhatsApp Business Images')
DOCS_WA = ('WhatsApp Documents', 'WhatsApp Business Documents')


def tam(n):
    for u in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or u == 'GB':
            return ('%.0f %s' if u in ('B', 'KB') else '%.1f %s') % (n, u)
        n /= 1024.0


def archivos(carpeta, recursivo=True):
    """(ruta, bytes, días) de cada archivo, sin .nomedia."""
    ahora, out = time.time(), []
    if not os.path.isdir(carpeta):
        return out
    for d, subdirs, fs in os.walk(carpeta):
        for f in fs:
            if f == '.nomedia':
                continue
            r = os.path.join(d, f)
            try:
                out.append((r, os.path.getsize(r), int((ahora - os.path.getmtime(r)) // DIA)))
            except OSError:
                pass
        if not recursivo:
            subdirs[:] = []
    return out


def peso_carpeta(r):
    return sum(x[1] for x in archivos(r))


def grupos(interno=INTERNO, descargas=DESCARGAS):
    """Lista de (título, [(ruta, bytes, días)], es_carpeta)."""
    g = []
    # 1. pruebas y fallas en Descargas (archivos + carpetas de grabación)
    scripts = []
    if os.path.isdir(descargas):
        ahora = time.time()
        for n in sorted(os.listdir(descargas)):
            r = os.path.join(descargas, n)
            try:
                dias = int((ahora - os.path.getmtime(r)) // DIA)
                if os.path.isdir(r) and CARPETAS_DE_SCRIPTS.match(n):
                    scripts.append((r, peso_carpeta(r), dias))
                elif os.path.isfile(r) and DE_SCRIPTS.search(n) and not PROTEGIDOS.match(n):
                    scripts.append((r, os.path.getsize(r), dias))
            except OSError:
                pass
    g.append(('Pruebas y fallas de los scripts en Descargas (capturas, xml, grabaciones)', scripts))
    # 2-3. capturas de pantalla
    caps = [x for c in CAPTURAS for x in archivos(os.path.join(interno, c))]
    g.append(('Capturas de pantalla de los últimos %d días' % DIAS_CAPTURAS, [x for x in caps if x[2] < DIAS_CAPTURAS]))
    g.append(('Capturas de pantalla más viejas', [x for x in caps if x[2] >= DIAS_CAPTURAS]))
    # 4-6. WhatsApp
    recibidas, mandadas, docs = [], [], []
    for base in WHATSAPP:
        for sub in FOTOS_WA:
            for x in archivos(os.path.join(interno, base, sub)):
                if x[2] >= DIAS_WHATSAPP:
                    (mandadas if os.sep + 'Sent' + os.sep in x[0] else recibidas).append(x)
        for sub in DOCS_WA:
            docs += [x for x in archivos(os.path.join(interno, base, sub)) if x[2] >= DIAS_WHATSAPP]
    g.append(('Fotos de WhatsApp recibidas (comprobantes) de más de %d días' % DIAS_WHATSAPP, recibidas))
    g.append(('Fotos de WhatsApp que mandaste vos, de más de %d días' % DIAS_WHATSAPP, mandadas))
    g.append(('PDF y documentos de WhatsApp de más de %d días' % DIAS_WHATSAPP, docs))
    # 7. tus archivos viejos en Descargas (solo archivos sueltos, no carpetas)
    tuyos = [x for x in archivos(descargas, recursivo=False)
             if x[2] > DIAS_DESCARGAS and not PROTEGIDOS.match(os.path.basename(x[0]))
             and not DE_SCRIPTS.search(os.path.basename(x[0]))]
    g.append(('Tus archivos de Descargas con más de %d días' % DIAS_DESCARGAS, tuyos))
    return g


def mostrar(g):
    total = 0
    print('\nLo que se puede borrar:\n')
    for i, (titulo, lista) in enumerate(g, 1):
        b = sum(x[1] for x in lista)
        total += b
        rango = (' · de hace %d a %d días' % (min(x[2] for x in lista), max(x[2] for x in lista))) if lista else ''
        print('  %d) %-74s %5d  %9s%s' % (i, titulo, len(lista), tam(b), rango))
    print('\n  En total se pueden liberar %s.' % tam(total))


def ver(g, n):
    titulo, lista = g[n - 1]
    print('%s: %d' % (titulo, len(lista)))
    for r, b, d in sorted(lista, key=lambda x: -x[1])[:60]:
        print('  %9s  hace %3d días  %s' % (tam(b), d, os.path.relpath(r, INTERNO) if r.startswith(INTERNO) else r))
    if len(lista) > 60:
        print('  … y %d más (los más pesados primero)' % (len(lista) - 60))


def borrar(lista):
    hechos, fallas, liberado, carpetas = 0, [], 0, set()
    for r, b, _ in lista:
        if PROTEGIDOS.match(os.path.basename(r)):   # doble seguro
            continue
        try:
            shutil.rmtree(r) if os.path.isdir(r) else os.remove(r)
            hechos += 1
            liberado += b
            carpetas.add(os.path.dirname(r))
        except OSError as e:
            fallas.append((r, e))
    # que la galería se entere (si está Termux:API); si no, se actualiza sola más tarde
    for c in carpetas:
        try:
            subprocess.run(['termux-media-scan', '-r', c], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=60, check=False)
        except (OSError, subprocess.SubprocessError):
            break
    return hechos, fallas, liberado


def menu(g, entrada=input):
    mostrar(g)
    elegir = entrada('\n¿Qué números borro? (ej: 1 2 4 · Enter = nada): ').replace(',', ' ').split()
    nums = sorted({int(x) for x in elegir if x.isdigit() and 1 <= int(x) <= len(g)})
    lista = [x for n in nums for x in g[n - 1][1]]
    if not lista:
        print('No borré nada.')
        return 0
    for n in nums:
        print('  · %s: %d (%s)' % (g[n - 1][0], len(g[n - 1][1]), tam(sum(x[1] for x in g[n - 1][1]))))
    print('\nVoy a borrar %d archivos y carpetas (%s). No se puede deshacer.' % (len(lista), tam(sum(x[1] for x in lista))))
    if entrada('Escribí BORRAR para seguir: ').strip() != 'BORRAR':
        print('No borré nada.')
        return 0
    hechos, fallas, liberado = borrar(lista)
    print('Listo: borré %d y liberé %s.' % (hechos, tam(liberado)))
    if fallas:
        print('No pude borrar %d (Android no deja tocar algunos archivos de WhatsApp desde Termux).' % len(fallas))
        print('Esos borralos desde WhatsApp → Ajustes → Almacenamiento y datos → Administrar almacenamiento.')
    return hechos


def main(args):
    if not os.path.isdir(INTERNO):
        sys.exit('No encuentro el almacenamiento. Corré termux-setup-storage una vez y probá de nuevo.')
    print('Revisando el teléfono…')
    g = grupos()
    if args[:1] == ['--ver'] and len(args) > 1 and args[1].isdigit() and 1 <= int(args[1]) <= len(g):
        ver(g, int(args[1]))
    elif not args:
        menu(g)
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == '__main__':
    main(sys.argv[1:])
