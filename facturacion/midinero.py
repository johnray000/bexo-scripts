#!/usr/bin/env python3
"""Lee los movimientos de MiDinero desde su web (webpersonas.midinero.com.uy), en el VPS, sin el teléfono.

La app no deja leer su pantalla, así que se usa la web con un navegador sin ventana (Playwright + Chromium).
El navegador guarda su perfil en ~/.midinero_perfil: si la web pide un código la primera vez, lo escribís vos
en la terminal y después recuerda el dispositivo. Solo lee: no toca transferir ni nada que mueva plata.

  python3 midinero.py --explorar   # entra, guarda cada pantalla y los datos que trae la web en ~/midinero_explorar

Lee MIDINERO_EMAIL y MIDINERO_CLAVE de /etc/subir-ordenes.env (o ~/.subir-ordenes.env).
"""
import argparse
import json
import os
import re
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from subir_ordenes import leer_env  # noqa: E402

WEB = 'https://webpersonas.midinero.com.uy'
MOVIMIENTOS = WEB + '/app/movimientos'
PERFIL = os.path.expanduser('~/.midinero_perfil')
PUERTO_TUNEL = 1080
EXPLORAR = os.path.expanduser('~/midinero_explorar')
# Como un Chrome normal de Windows: algunas webs rechazan al navegador "sin ventana".
NAVEGADOR = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
             'Chrome/130.0.0.0 Safari/537.36')
# Campos que no se guardan en los archivos de exploración (sesión, claves).
SECRETO = re.compile(r'token|jwt|password|clave|secret|session|cookie|authorization', re.I)


def tapar(x):
    """Copia de x sin los valores de campos con nombre de secreto."""
    if isinstance(x, dict):
        return {k: ('***' if SECRETO.search(k) else tapar(v)) for k, v in x.items()}
    if isinstance(x, list):
        return [tapar(v) for v in x]
    return x


def proxy_telefono():
    """MiDinero bloquea las IP de fuera de Uruguay: el VPS sale por el túnel del teléfono (telefono/tunel_vps.sh),
    que deja un proxy en 127.0.0.1:1080 del VPS. Sin túnel no se puede entrar."""
    import socket
    try:
        socket.create_connection(('127.0.0.1', PUERTO_TUNEL), timeout=3).close()
    except OSError:
        raise SystemExit('El túnel del teléfono no está conectado (puerto %d). Mirá ~/tunel.log en Termux.' % PUERTO_TUNEL)
    return {'server': 'socks5://127.0.0.1:%d' % PUERTO_TUNEL}


def limpio(url):
    """La dirección sin códigos de sesión, corta, para mostrar en la terminal."""
    return re.sub(r'(code|state|session_state|sessionDataKey|token)=[^&]+', r'\1=…', url)[:160]


def visibles(page, selector):
    return [e for e in page.query_selector_all(selector) if e.is_visible()]


def resumen(page):
    """Lo que hay en pantalla, para la terminal: campos para escribir y botones."""
    campos = ['%s(%s)' % (e.get_attribute('type') or 'text', e.get_attribute('name') or e.get_attribute('placeholder') or '')
              for e in visibles(page, 'input')]
    botones = [(e.inner_text() or '').strip()[:30] for e in visibles(page, 'button, [role=button], a')]
    return 'URL %s\n  campos: %s\n  botones: %s' % (page.url, ', '.join(campos) or '-',
                                                     ', '.join(b for b in botones if b)[:400] or '-')


def guardar(page, n, nombre):
    base = os.path.join(EXPLORAR, '%02d_%s' % (n, nombre))
    page.screenshot(path=base + '.png', full_page=True)
    html = page.content()
    html = re.sub(r'(type="password"[^>]*value=")[^"]*', r'\1***', html)
    with open(base + '.html', 'w') as fh:
        fh.write(html)
    texto = re.sub(r'\s+', ' ', page.inner_text('body') or '').strip()
    print('\n[%02d %s]\n  %s\n  texto: %s' % (n, nombre, resumen(page), texto[:400]), flush=True)


def login(page, cfg):
    """Escribe email y contraseña si la web los pide. Si después pide un código, lo pedís en la terminal."""
    page.goto(MOVIMIENTOS, wait_until='networkidle', timeout=60000)
    if not visibles(page, 'input[type=password]'):
        return
    clave = visibles(page, 'input[type=password]')[0]
    email = [e for e in visibles(page, 'input') if (e.get_attribute('type') or 'text') in ('email', 'text')]
    if email:
        email[0].fill(cfg['MIDINERO_EMAIL'])
    clave.fill(cfg['MIDINERO_CLAVE'])
    boton = [b for b in visibles(page, 'button, input[type=submit]')
             if re.search(r'iniciar', (b.inner_text() or b.get_attribute('value') or ''), re.I)]
    if boton:
        boton[0].click()
    else:
        clave.press('Enter')
    page.wait_for_load_state('networkidle', timeout=60000)
    time.sleep(3)


def pedir_codigo(page):
    """Si quedó un campo para escribir (código por SMS o mail), lo escribís vos. Nunca se inventa ni se saltea."""
    campos = [e for e in visibles(page, 'input') if (e.get_attribute('type') or 'text') not in ('hidden', 'checkbox')]
    if not campos or not sys.stdin.isatty():
        return False
    codigo = input('\nLa web pide algo más (mirá 02_despues_login.png). Si es un código, escribilo acá '
                   '(Enter vacío para seguir sin escribir): ').strip()
    if not codigo:
        return False
    campos[0].fill(codigo)
    campos[0].press('Enter')
    page.wait_for_load_state('networkidle', timeout=60000)
    time.sleep(3)
    return True


def explorar():
    from playwright.sync_api import sync_playwright
    cfg = leer_env()
    for k in ('MIDINERO_EMAIL', 'MIDINERO_CLAVE'):
        if not cfg.get(k):
            raise SystemExit('Falta %s en el .env' % k)
    shutil.rmtree(EXPLORAR, ignore_errors=True)
    os.makedirs(EXPLORAR)
    respuestas = []

    def al_navegar(frame):
        if frame == frame.page.main_frame:
            print('  → %s' % limpio(frame.url), flush=True)

    def al_responder(r):
        tipo = r.request.resource_type
        if 'midinero.com.uy' in r.url and 'ahora.' not in r.url and (tipo in ('xhr', 'fetch') or r.status >= 400):
            print('  %s %s %s %s' % ('!' if r.status >= 400 else '·', r.status, tipo, limpio(r.url)), flush=True)
            if r.status >= 400:
                try:
                    print('      %s' % re.sub(r'\s+', ' ', r.text())[:300], flush=True)
                except Exception:
                    pass
        if 'json' in (r.headers.get('content-type') or '') and r.request.resource_type in ('xhr', 'fetch'):
            try:
                respuestas.append({'url': r.url, 'estado': r.status, 'datos': tapar(r.json())})
            except Exception:
                pass

    with sync_playwright() as p:
        nav = p.chromium.launch_persistent_context(PERFIL, headless=True, locale='es-UY',
                                                   timezone_id='America/Montevideo',
                                                   viewport={'width': 1280, 'height': 900},
                                                   user_agent=NAVEGADOR, proxy=proxy_telefono())
        page = nav.pages[0] if nav.pages else nav.new_page()
        page.on('response', al_responder)
        page.on('framenavigated', al_navegar)
        page.on('requestfailed', lambda q: print('  ✗ falló %s %s (%s)' % (q.resource_type, limpio(q.url), q.failure),
                                                  flush=True))
        page.on('console', lambda m: m.type == 'error' and print('  consola: %s' % m.text[:300], flush=True))
        page.goto(WEB, wait_until='networkidle', timeout=60000)
        guardar(page, 1, 'entrada')
        login(page, cfg)
        guardar(page, 2, 'despues_login')
        if '/app/movimientos' not in page.url and pedir_codigo(page):
            guardar(page, 3, 'despues_codigo')
        page.goto(MOVIMIENTOS, wait_until='networkidle', timeout=60000)
        time.sleep(5)
        guardar(page, 4, 'movimientos')
        antes = len(respuestas)
        try:   # abre el detalle (🔎) de la primera recarga, para ver qué datos trae
            page.get_by_text(re.compile('RECARGA', re.I)).first.click(timeout=10000)
            page.wait_for_load_state('networkidle', timeout=30000)
            time.sleep(4)
            guardar(page, 5, 'detalle')
        except Exception as e:
            print('  No pude abrir un detalle: %s' % str(e)[:200])
        print('\nRespuestas al abrir el detalle: %d' % (len(respuestas) - antes))
        nav.close()

    with open(os.path.join(EXPLORAR, 'datos_web.json'), 'w') as fh:
        json.dump(respuestas, fh, ensure_ascii=False, indent=1)
    print('\nDatos que trajo la web (%d respuestas):' % len(respuestas))
    for r in respuestas:
        if not re.search(r'midinero\.com\.uy/(api/Account|midinero\.svc/(?!getuser))', r['url']):
            continue
        d = r['datos'][:2] if isinstance(r['datos'], list) else r['datos']
        print('\n  %s %s\n  %s' % (r['estado'], limpio(r['url']), json.dumps(d, ensure_ascii=False)[:2500]))
    print('\nTodo en %s. Copiá desde [01 entrada] hasta acá y pasáselo a Claude.' % EXPLORAR)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--explorar', action='store_true', help='guarda cada pantalla y los datos de la web')
    a = ap.parse_args()
    if a.explorar:
        explorar()
    else:
        ap.print_help()


if __name__ == '__main__':
    main()
