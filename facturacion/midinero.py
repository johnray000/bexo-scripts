#!/usr/bin/env python3
"""Lee los movimientos de MiDinero desde su web (webpersonas.midinero.com.uy), en el VPS, sin el teléfono.

La app no deja leer su pantalla, así que se usa la web con un navegador sin ventana (Playwright + Chromium).
El navegador guarda su perfil en ~/.midinero_perfil: si la web pide un código la primera vez, lo escribís vos
en la terminal y después recuerda el dispositivo. Solo lee: no toca transferir ni nada que mueva plata.

  python3 midinero.py --explorar   # entra, guarda cada pantalla y los datos que trae la web en ~/midinero_explorar
  python3 midinero.py --probar     # muestra las entradas de los últimos 9 días (no manda nada)
  python3 midinero.py --desde 01/10/2026 --hasta 31/10/2026   # un mes entero
  python3 midinero.py              # lee los últimos 9 días y los manda a "Movs UY" (lo del cron de los martes)

Sale a internet por el túnel del teléfono (MiDinero bloquea IPs de fuera de Uruguay). Para mandar usa
WEBAPP_URL y ORDENES_TOKEN del mismo .env, como prex.py.

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
    for _ in range(12):   # si se cortó, el teléfono reconecta en unos segundos: espera hasta 2 minutos
        try:
            socket.create_connection(('127.0.0.1', PUERTO_TUNEL), timeout=3).close()
            break
        except OSError:
            time.sleep(10)
    else:
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
                cuerpo = r.request.post_data
                try:
                    cuerpo = tapar(json.loads(cuerpo)) if cuerpo else None
                except ValueError:
                    pass
                respuestas.append({'url': r.url, 'estado': r.status, 'metodo': r.request.method, 'envio': cuerpo,
                                   'datos': tapar(r.json())})
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
        if not re.search(r'midinero\.com\.uy/(api/(Account|transfer)|midinero\.svc/(?!getuser|obtenercuentas))',
                         r['url'], re.I):
            continue
        d = r['datos'][:2] if isinstance(r['datos'], list) else r['datos']
        print('\n  %s %s %s' % (r['estado'], r['metodo'], limpio(r['url'])))
        if r['envio']:
            print('  envía: %s' % json.dumps(r['envio'], ensure_ascii=False)[:800])
        print('  %s' % json.dumps(d, ensure_ascii=False)[:2500])
    print('\nTodo en %s. Copiá desde [01 entrada] hasta acá y pasáselo a Claude.' % EXPLORAR)


CTA = 'MiDinero'
MOVS_API = 'https://ms-serverside-personas.midinero.com.uy/api/Account/getMovements'
DETALLE_API = 'https://personas-ss.midinero.com.uy/api/transfer/transferDetail'
# Entradas que no son cobros (devoluciones de compras con tarjeta): no se mandan.
EXCLUIR = re.compile(r'^GOOGLE\*|DEVOLUCI|^DEV\.', re.I)


def entrar(p):
    """Abre la web por el túnel, entra con email y contraseña y espera la lista de movimientos.
    Devuelve (navegador, página, encabezados de la sesión por servidor, documento de John, n° de cuenta)."""
    cfg = leer_env()
    for k in ('MIDINERO_EMAIL', 'MIDINERO_CLAVE'):
        if not cfg.get(k):
            raise SystemExit('Falta %s en el .env' % k)
    sesion, doc = {}, {}

    def al_pedir(q):   # la web manda su sesión en los encabezados: se reusan para pedir los datos
        host = q.url.split('/')[2]
        if host.startswith(('ms-serverside-personas.', 'personas-ss.')) and q.resource_type in ('xhr', 'fetch'):
            h = {k: v for k, v in q.all_headers().items()
                 if k.lower() not in ('cookie', 'content-length', 'host') and not k.startswith(':')}
            if any(k.lower() == 'authorization' for k in h):
                sesion['detalle' if 'transferDetail' in q.url else host] = h
        m = re.search(r'customer-id=\d+_(\d+)', q.url)
        if m:
            doc['n'] = m.group(1)
        m = re.search(r'getMovements\?.*accountNumber=(\d+)', q.url)
        if m:   # la cuenta sale del pedido que hace la propia web (obtenercuentasv2 no acepta GET)
            doc['cuenta'] = m.group(1)

    nav = p.chromium.launch_persistent_context(PERFIL, headless=True, locale='es-UY', timezone_id='America/Montevideo',
                                               viewport={'width': 1280, 'height': 900}, user_agent=NAVEGADOR,
                                               proxy=proxy_telefono())
    page = nav.pages[0] if nav.pages else nav.new_page()
    page.on('request', al_pedir)
    login(page, cfg)
    if '/error/' in page.url:   # a veces el primer intento cae en error y el segundo entra
        page.goto(MOVIMIENTOS, wait_until='networkidle', timeout=60000)
    if '/app/movimientos' not in page.url:
        page.goto(MOVIMIENTOS, wait_until='networkidle', timeout=60000)
    time.sleep(5)
    if '/app/movimientos' not in page.url or not sesion or not doc.get('cuenta'):
        raise SystemExit('No pude entrar a MiDinero (quedó en %s).' % limpio(page.url))
    documento = doc.get('n') or cfg.get('MIDINERO_DOCUMENTO', '')
    if not documento:
        raise SystemExit('No encontré tu documento: agregá MIDINERO_DOCUMENTO=... al .env.')
    return nav, page, sesion, documento, doc['cuenta']


def pedir(nav, sesion, metodo, url, datos=None, tolerar=False):
    host = url.split('/')[2]
    # el detalle exige los encabezados exactos que manda la web al abrir un 🔎 (si no: "aplicación no activa")
    h = (sesion.get('detalle') if 'transferDetail' in url else None) or sesion.get(host) or next(iter(sesion.values()))
    if metodo == 'GET':
        r = nav.request.get(url, headers=h, timeout=60000)
    else:
        r = nav.request.post(url, headers=dict(h, **{'content-type': 'application/json'}), data=json.dumps(datos),
                             timeout=60000)
    if not r.ok and tolerar:   # un detalle que no se pudo leer no frena el resto
        print('  (sin detalle: %s %s)' % (r.status, re.sub(r'\s+', ' ', r.text())[:200]), flush=True)
        return {}
    if not r.ok:
        raise SystemExit('MiDinero respondió %s a %s' % (r.status, limpio(url)))
    return r.json()


def entradas(desde, hasta, intentos=3):
    """Como _entradas, reintentando si el túnel del teléfono se corta a mitad de camino."""
    for n in range(intentos):
        try:
            return _entradas(desde, hasta)
        except Exception as e:
            if 'PROXY' not in str(e) and 'ERR_CONNECTION' not in str(e) or n == intentos - 1:
                raise
            print('Se cortó el túnel del teléfono, reintento en 30 s...', flush=True)
            time.sleep(30)


def _entradas(desde, hasta):
    """Las entradas de plata entre dos fechas (datetime.date), con el nombre de quien mandó cada una."""
    from urllib.parse import urlencode
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        nav, page, sesion, documento, cuenta = entrar(p)
        try:
            q = urlencode({'from': desde.strftime('%Y-%m-%dT00:00:00'), 'to': hasta.strftime('%Y-%m-%dT23:59:59'),
                           'accountNumber': cuenta, 'limit': 1000})
            movs = pedir(nav, sesion, 'GET', MOVS_API + '?' + q)
            try:   # abre el 🔎 de una recarga para copiar los encabezados que usa la web en el detalle
                page.get_by_text(re.compile('RECARGA', re.I)).first.click(timeout=15000)
                page.wait_for_load_state('networkidle', timeout=30000)
                time.sleep(2)
            except Exception:
                pass
            if len(movs) >= 1000:
                print('Ojo: llegaron 1000 movimientos, puede haber más. Pedí menos días.', flush=True)
            filas = []
            for m in movs:
                monto = (m.get('amount') or {}).get('amount') or 0
                if monto <= 0 or EXCLUIR.search(m.get('description') or '') or EXCLUIR.search(m.get('typeName') or ''):
                    continue
                d = {}
                if m.get('extendedId'):
                    d = pedir(nav, sesion, 'POST', DETALLE_API, {'Document': documento, 'AccountNumber': int(cuenta),
                                                                 'ExtendedId': m['extendedId']}, tolerar=True)
                    if not d:   # a veces el primero choca con el detalle que abrió la web: un reintento
                        time.sleep(3)
                        d = pedir(nav, sesion, 'POST', DETALLE_API, {'Document': documento,
                                                                     'AccountNumber': int(cuenta),
                                                                     'ExtendedId': m['extendedId']}, tolerar=True)
                filas.append({'id': m['id'], 'fecha': m['date'], 'monto': monto, 'tipo': m.get('typeName') or '',
                              'desc': m.get('description') or '', 'titular': (d.get('accountOriginName') or '').strip(),
                              'doc_origen': d.get('accountOriginDocument') or '',
                              'concepto': (d.get('concept') or '').strip(), 'ref_md': d.get('referenceNumber') or ''})
            return filas
        finally:
            nav.close()


def para_planilla(f):
    """Una entrada con el formato que recibe 17_MovimientosUY.gs (el mismo de Prex e Itaú)."""
    dia, hora = f['fecha'][:10], f['fecha'][11:16]
    fecha = '%s/%s/%s - %s' % (dia[8:10], dia[5:7], dia[:4], hora)
    detalle = f['concepto'] or ('' if f['titular'] else f['desc'])
    return {'fecha_hora': fecha, 'monto': f['monto'], 'titular': f['titular'], 'descripcion': detalle,
            'referencia': 'MD-%s' % f['id'], 'cta': CTA}


def mandar(filas):
    """Manda las filas al Apps Script (WEBAPP_URL, ORDENES_TOKEN del .env). Igual que prex.mandar, sin ADB."""
    import urllib.request
    cfg = leer_env()
    cuerpo = json.dumps({'movimientosUY': filas, 'cta': CTA, 'token': cfg['ORDENES_TOKEN']}).encode()
    req = urllib.request.Request(cfg['WEBAPP_URL'], data=cuerpo, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode('utf-8', 'replace'))


def main():
    from datetime import date, datetime, timedelta
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--explorar', action='store_true', help='guarda cada pantalla y los datos de la web')
    ap.add_argument('--probar', action='store_true', help='muestra las entradas sin mandarlas a la planilla')
    ap.add_argument('--dias', type=int, default=9, help='cuántos días para atrás (por defecto 9)')
    ap.add_argument('--desde', help='dd/mm/aaaa')
    ap.add_argument('--hasta', help='dd/mm/aaaa (por defecto hoy)')
    a = ap.parse_args()
    if a.explorar:
        return explorar()
    hasta = datetime.strptime(a.hasta, '%d/%m/%Y').date() if a.hasta else date.today()
    desde = datetime.strptime(a.desde, '%d/%m/%Y').date() if a.desde else hasta - timedelta(days=a.dias)
    filas = entradas(desde, hasta)
    print('%d entradas de MiDinero del %s al %s' % (len(filas), desde.strftime('%d/%m'), hasta.strftime('%d/%m')))
    for f in filas:
        print('  %s  %10.2f  %-30s %s [%s]' % (f['fecha'][:16].replace('T', ' '), f['monto'], f['titular'][:30],
                                              f['concepto'] or f['desc'], f['tipo']))
    if a.probar or not filas:
        return
    print('Planilla:', mandar([para_planilla(f) for f in filas]))


if __name__ == '__main__':
    main()
