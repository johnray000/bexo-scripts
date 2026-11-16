#!/usr/bin/env python3
"""Tablero P2P: servidor chiquito para el VPS (solo librería estándar, ~15 MB de RAM).

- Cada 10 min le pide los números al Apps Script (DASH_URL, que ya trae ?dash=1&k=TOKEN) y los guarda en data.json.
- Sirve index.html y data.json con usuario y clave (Basic Auth). Nada más.
- Configuración en /etc/dashboard-p2p.env (no está en el repo):
    DASH_URL=https://script.google.com/macros/s/.../exec?dash=1&k=...
    DASH_USUARIO=john
    DASH_CLAVE=...
    DASH_PUERTO=8090
Lo instala vps/dashboard_instalar.sh como servicio systemd "dashboard-p2p".
"""
import base64
import hmac
import json
import os
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CARPETA = os.path.dirname(os.path.abspath(__file__))
DATOS = os.path.join(CARPETA, 'data.json')
URL = os.environ.get('DASH_URL', '')
USUARIO = os.environ.get('DASH_USUARIO', 'john')
CLAVE = os.environ.get('DASH_CLAVE', '')
PUERTO = int(os.environ.get('DASH_PUERTO', '8090'))
CADA = int(os.environ.get('DASH_CADA_SEG', '600'))
ULTIMO_PEDIDO = 0
ESPERADO = 'Basic ' + base64.b64encode(f'{USUARIO}:{CLAVE}'.encode()).decode()


def log(msg):
    print(time.strftime('%d/%m %H:%M:%S'), msg, flush=True)


BINANCE = 'https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search'


def pagina_binance(asset, tipo_taker, pagina):
    cuerpo = {'asset': asset, 'fiat': 'UYU', 'tradeType': tipo_taker, 'page': pagina, 'rows': 20, 'payTypes': []}
    req = urllib.request.Request(BINANCE, data=json.dumps(cuerpo).encode(),
                                 headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r).get('data') or []


def anuncios_binance_vivos():
    """Busca tus anuncios de Binance (los n° que mandó el Apps Script la vez anterior) en el listado público UYU.
    Devuelve {n°: {tipo, cripto, precio, puesto, total, mejor, visible}}. Si Binance falla, devuelve {}."""
    global ESTADO_BINANCE
    try:
        with open(DATOS, encoding='utf-8') as f:
            mios = json.load(f).get('misAnunciosBinance') or {}
    except Exception:  # noqa: BLE001
        mios = {}
    ESTADO_BINANCE = {'buscados': len(mios), 'encontrados': 0, 'error': ''}
    if not mios:
        ESTADO_BINANCE['error'] = 'todavía no sé cuáles son tus anuncios (la planilla no mandó la lista)'
        return {}
    vivos = {}
    grupos = {}
    for ad, info in mios.items():
        # Tu anuncio de VENTA lo ve quien quiere COMPRAR (tradeType BUY) y al revés.
        taker = 'BUY' if info.get('tipo') == 'Venta' else 'SELL'
        grupos.setdefault((info.get('cripto') or 'USDT', taker), []).append(ad)
    for (asset, taker), ads in grupos.items():
        faltan = set(ads)
        puesto, mejor = 0, None
        try:
            for pagina in range(1, 6):
                lista = pagina_binance(asset, taker, pagina)
                for a in lista:
                    puesto += 1
                    n = str(a['adv']['advNo'])
                    precio = float(a['adv']['price'])
                    if n in faltan:
                        faltan.discard(n)
                        vivos[n] = {'tipo': mios[n]['tipo'], 'cripto': asset, 'precio': precio, 'puesto': puesto, 'visible': True}
                    elif mejor is None:
                        mejor = precio
                if len(lista) < 20:
                    break
        except Exception as e:  # noqa: BLE001
            log(f'Binance {asset} {taker}: {e}')
            ESTADO_BINANCE['error'] = f'Binance no respondió: {e}'[:160]
            continue
        for n in ads:
            if n in vivos:
                vivos[n].update(total=puesto, mejor=mejor)
            else:
                vivos[n] = {'tipo': mios[n]['tipo'], 'cripto': asset, 'visible': False}
    ESTADO_BINANCE['encontrados'] = sum(1 for v in vivos.values() if v.get('visible'))
    log(f"Binance en vivo: {ESTADO_BINANCE['encontrados']} de {len(mios)} anuncios encontrados")
    return vivos


ESTADO_BINANCE = {}


def actualizar():
    """Pide los números al Apps Script. Si falla, deja el data.json anterior y anota el error."""
    try:
        url = URL
        vivos = anuncios_binance_vivos()
        if vivos:
            url += '&vivos=' + urllib.parse.quote(json.dumps(vivos, separators=(',', ':')))
        with urllib.request.urlopen(url, timeout=90) as r:   # sigue solo la redirección de Google
            datos = json.loads(r.read().decode('utf-8'))
        if 'error' in datos:
            raise ValueError(datos['error'])
        datos['servidor'] = {'ok': True, 'hora': int(time.time()), 'binance': ESTADO_BINANCE}
    except Exception as e:  # noqa: BLE001
        log(f'No pude actualizar: {e}')
        try:
            with open(DATOS, encoding='utf-8') as f:
                datos = json.load(f)
        except Exception:  # noqa: BLE001
            datos = {}
        datos['servidor'] = {'ok': False, 'hora': int(time.time()), 'error': str(e)[:200]}
    tmp = DATOS + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(datos, f, ensure_ascii=False)
    os.replace(tmp, DATOS)


def bucle():
    while True:
        actualizar()
        time.sleep(CADA)


class Pagina(BaseHTTPRequestHandler):
    def log_message(self, *a):  # sin log por cada pedido
        pass

    def _mandar(self, codigo, cuerpo, tipo):
        self.send_response(codigo)
        self.send_header('Content-Type', tipo)
        self.send_header('Content-Length', str(len(cuerpo)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        if not CLAVE or not hmac.compare_digest(self.headers.get('Authorization', ''), ESPERADO):
            self.send_response(401)
            self.send_header('WWW-Authenticate', 'Basic realm="Tablero P2P", charset="UTF-8"')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        ruta = self.path.split('?')[0]
        if ruta in ('/', '/index.html'):
            archivo, tipo = 'index.html', 'text/html; charset=utf-8'
        elif ruta == '/data.json':
            archivo, tipo = 'data.json', 'application/json; charset=utf-8'
        elif ruta == '/actualizar':   # botón "actualizar ahora" de la página (como mucho 1 vez por minuto)
            global ULTIMO_PEDIDO
            if time.time() - ULTIMO_PEDIDO > 60:
                ULTIMO_PEDIDO = time.time()
                actualizar()
            archivo, tipo = 'data.json', 'application/json; charset=utf-8'
        else:
            return self._mandar(404, b'', 'text/plain')
        try:
            with open(os.path.join(CARPETA, archivo), 'rb') as f:
                self._mandar(200, f.read(), tipo)
        except FileNotFoundError:
            self._mandar(503, b'{"error":"todavia sin datos"}', 'application/json')


if __name__ == '__main__':
    if not URL or not CLAVE:
        raise SystemExit('Falta DASH_URL o DASH_CLAVE en /etc/dashboard-p2p.env')
    threading.Thread(target=bucle, daemon=True).start()
    log(f'Tablero P2P en el puerto {PUERTO}, actualiza cada {CADA // 60} min')
    ThreadingHTTPServer(('0.0.0.0', PUERTO), Pagina).serve_forever()
