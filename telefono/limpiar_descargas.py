#!/usr/bin/env python3
"""Ordena y limpia la carpeta Descargas del teléfono (Termux: ~/storage/downloads).

  python limpiar_descargas.py                     # SOLO MUESTRA qué hay (no borra nada)
  python limpiar_descargas.py --borrar-scripts    # borra lo que generaron los scripts (capturas, xml, grabaciones)
  python limpiar_descargas.py --borrar-viejos 30  # borra TUS archivos con más de 30 días (no toca carpetas)

Siempre muestra la lista de lo que va a borrar y pide escribir BORRAR para seguir.
Nunca borra los datos que usan los scripts (PROTEGIDOS), ni carpetas que no sean grabaciones de los scripts.
"""
import os
import re
import shutil
import sys
import time

CARPETA = os.path.expanduser('~/storage/downloads')

# Datos que leen o escriben los scripts: NUNCA se borran.
PROTEGIDOS = re.compile(r'^(prex|mercadopago|itau|ocablue)_entradas\.csv$|^okx_enlaces\.txt$')
# Lo que dejan los scripts para ver qué pasó (capturas, pantallas, grabaciones): se puede borrar.
DE_SCRIPTS = re.compile(
    r'^(binance_|okx_fallo_|okx_pantalla_|peya_|prex_ingreso|prex_fallo|oca_fallo|oca_trabado|itau_fallo|'
    r'itau_trabado|mp_fallo|grabacion)[^/]*\.(png|xml|tgz|txt)$')
CARPETAS_DE_SCRIPTS = re.compile(r'^binance_grabacion(_\d+)?$')
TIPOS = [
    ('Imágenes', ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.heic')),
    ('PDF', ('.pdf',)),
    ('Instaladores (APK)', ('.apk', '.xapk', '.apks')),
    ('Videos y audios', ('.mp4', '.mkv', '.mov', '.3gp', '.mp3', '.m4a', '.ogg', '.opus', '.wav')),
    ('Documentos y planillas', ('.doc', '.docx', '.xls', '.xlsx', '.csv', '.txt', '.odt', '.ods', '.ppt', '.pptx')),
    ('Comprimidos', ('.zip', '.rar', '.7z', '.tgz', '.gz', '.tar')),
]


def tam(n):
    for u in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or u == 'GB':
            return ('%.0f %s' if u in ('B', 'KB') else '%.1f %s') % (n, u)
        n /= 1024.0


def peso(ruta):
    if os.path.isdir(ruta):
        return sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(ruta) for f in fs)
    return os.path.getsize(ruta)


def tipo(nombre):
    ext = os.path.splitext(nombre)[1].lower()
    for t, exts in TIPOS:
        if ext in exts:
            return t
    return 'Otros'


def clasificar(carpeta):
    """Devuelve (de_scripts, protegidos, tuyos, carpetas_tuyas): listas de (nombre, bytes, días)."""
    de_scripts, protegidos, tuyos, carpetas = [], [], [], []
    ahora = time.time()
    for nombre in sorted(os.listdir(carpeta)):
        ruta = os.path.join(carpeta, nombre)
        try:
            dato = (nombre, peso(ruta), int((ahora - os.path.getmtime(ruta)) // 86400))
        except OSError:
            continue
        if os.path.isdir(ruta):
            (de_scripts if CARPETAS_DE_SCRIPTS.match(nombre) else carpetas).append(dato)
        elif PROTEGIDOS.match(nombre):
            protegidos.append(dato)
        elif DE_SCRIPTS.match(nombre):
            de_scripts.append(dato)
        else:
            tuyos.append(dato)
    return de_scripts, protegidos, tuyos, carpetas


def mostrar(carpeta):
    de_scripts, protegidos, tuyos, carpetas = clasificar(carpeta)
    total = sum(x[1] for x in de_scripts + protegidos + tuyos + carpetas)
    print('Descargas: %d cosas, %s en total\n' % (len(de_scripts + protegidos + tuyos + carpetas), tam(total)))
    print('1) GENERADO POR LOS SCRIPTS (capturas y pantallas de fallos, grabaciones): %d, %s' %
          (len(de_scripts), tam(sum(x[1] for x in de_scripts))))
    print('   → se borra con: --borrar-scripts')
    for pre in sorted({re.match(r'^[a-z]+', n).group(0) for n, _, _ in de_scripts}):
        grupo = [x for x in de_scripts if x[0].startswith(pre)]
        print('     %-12s %4d   %s' % (pre, len(grupo), tam(sum(x[1] for x in grupo))))
    print('\n2) DATOS QUE USAN LOS SCRIPTS (no se borran nunca): %d' % len(protegidos))
    for n, b, d in protegidos:
        print('     %s  (%s, hace %d días)' % (n, tam(b), d))
    print('\n3) TUS ARCHIVOS: %d, %s   → los viejos se borran con: --borrar-viejos DÍAS' %
          (len(tuyos), tam(sum(x[1] for x in tuyos))))
    for t in [t for t, _ in TIPOS] + ['Otros']:
        grupo = [x for x in tuyos if tipo(x[0]) == t]
        if grupo:
            print('     %-24s %4d   %9s   el más viejo: hace %d días' %
                  (t, len(grupo), tam(sum(x[1] for x in grupo)), max(x[2] for x in grupo)))
    if tuyos:
        print('\n   Los 10 más pesados:')
        for n, b, d in sorted(tuyos, key=lambda x: -x[1])[:10]:
            print('     %9s  hace %3d días  %s' % (tam(b), d, n))
    if carpetas:
        print('\n4) CARPETAS (no se tocan nunca): %s' % ', '.join('%s (%s)' % (n, tam(b)) for n, b, _ in carpetas))
    print('\nNo borré nada.')


def confirmar_y_borrar(carpeta, lista, que):
    if not lista:
        print('No hay %s para borrar.' % que)
        return
    for n, b, d in lista[:40]:
        print('  %9s  hace %3d días  %s' % (tam(b), d, n))
    if len(lista) > 40:
        print('  … y %d más' % (len(lista) - 40))
    print('\nVoy a borrar %d (%s): %s. Esto no se puede deshacer.' % (len(lista), tam(sum(x[1] for x in lista)), que))
    if input('Escribí BORRAR para seguir: ').strip() != 'BORRAR':
        print('No borré nada.')
        return
    borrados = 0
    for n, _, _ in lista:
        ruta = os.path.join(carpeta, n)
        if PROTEGIDOS.match(n):            # doble seguro
            continue
        try:
            shutil.rmtree(ruta) if os.path.isdir(ruta) else os.remove(ruta)
            borrados += 1
        except OSError as e:
            print('  no pude borrar %s: %s' % (n, e))
    print('Listo: borré %d.' % borrados)


def main(args, carpeta=CARPETA):
    if not os.path.isdir(carpeta):
        sys.exit('No encuentro %s. Corré termux-setup-storage una vez y probá de nuevo.' % carpeta)
    if not args:
        mostrar(carpeta)
    elif args[0] == '--borrar-scripts':
        confirmar_y_borrar(carpeta, clasificar(carpeta)[0], 'lo generado por los scripts')
    elif args[0] == '--borrar-viejos' and len(args) > 1 and args[1].isdigit():
        dias = int(args[1])
        viejos = [x for x in clasificar(carpeta)[2] if x[2] > dias]
        confirmar_y_borrar(carpeta, viejos, 'tus archivos con más de %d días' % dias)
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == '__main__':
    main(sys.argv[1:])
