#!/usr/bin/env python3
"""Brújula P2P (tablero P2P): servidor chiquito para el VPS (solo librería estándar, ~15 MB de RAM).

- Cada 10 min le pide los números al Apps Script (DASH_URL, que ya trae ?dash=1&k=TOKEN) y los guarda en data.json.
- Sirve index.html y data.json con usuario y clave (Basic Auth).
- Hitos de Bitget (bitget.json): los cargás a mano desde la página (POST /bitget), copiando lo que muestra Bitget.
  No hay API de Bitget conectada: el tablero no los inventa ni los calcula.
- Configuración en /etc/dashboard-p2p.env (no está en el repo):
    DASH_URL=https://script.google.com/macros/s/.../exec?dash=1&k=...
    DASH_USUARIO=john
    DASH_CLAVE=...
    DASH_PUERTO=8090
    DASH_NTFY_TEMA=bexo-...   (opcional: con esto "Actualizar ahora" le pide al teléfono que suba las órdenes)
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
NTFY_TEMA = os.environ.get('DASH_NTFY_TEMA', '')   # el de ~/.bexo-ntfy del teléfono (opcional)
TELEFONO = {'pedido': 0}
ESPERADO = 'Basic ' + base64.b64encode(f'{USUARIO}:{CLAVE}'.encode()).decode()


def log(msg):
    print(time.strftime('%d/%m %H:%M:%S'), msg, flush=True)


BINANCE = 'https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search'
PAGINAS_MAX = 15   # 300 anuncios; UYU suele tener menos de 150


def pagina_binance(asset, tipo_taker, pagina):
    cuerpo = {'asset': asset, 'fiat': 'UYU', 'tradeType': tipo_taker, 'page': pagina, 'rows': 20, 'payTypes': []}
    req = urllib.request.Request(BINANCE, data=json.dumps(cuerpo).encode(),
                                 headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r).get('data') or []


YO = os.path.join(CARPETA, 'yo_binance.json')   # tu usuario de Binance (userNo y apodo), lo aprende solo


def leer_yo():
    try:
        with open(YO, encoding='utf-8') as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


def anuncios_binance_vivos():
    """Busca TUS anuncios de Binance en el listado público UYU, por tipo y cripto (Compra/Venta × USDT/USDC).

    Binance a veces cierra un anuncio (sin límite) y crea otro con otro número, así que no se sigue el n°:
    se reconoce tu usuario (userNo). Lo aprende la primera vez que encuentra uno de los n° de anuncio que mandó
    la planilla y lo guarda en yo_binance.json. Devuelve {"Venta|USDT": {...}, ...}:
      visible: True  -> precio, puesto, total, completo, mejor (el mejor de otro), metodos, cuantos (tus anuncios ahí)
      visible: False -> revisados (cuántos anuncios miré) y solo si recorrí el listado entero.
    Si no sé tu usuario o Binance falla, ese grupo no va (el tablero dice "precio de últ. orden")."""
    global ESTADO_BINANCE
    try:
        with open(DATOS, encoding='utf-8') as f:
            mios = json.load(f).get('misAnunciosBinance') or {}
    except Exception:  # noqa: BLE001
        mios = {}
    yo = leer_yo()
    ESTADO_BINANCE = {'grupos': 0, 'encontrados': 0, 'usuario': yo.get('apodo', ''), 'error': ''}
    if not yo and not mios:
        ESTADO_BINANCE['error'] = 'todavía no sé cuál es tu usuario de Binance (la planilla no mandó tus anuncios)'
        return {}
    vivos = {}
    for asset in ('USDT', 'USDC'):
        for tipo, taker in (('Venta', 'BUY'), ('Compra', 'SELL')):   # tu VENTA la ve quien quiere COMPRAR
            puesto, mejor, completo, mias = 0, None, False, []
            try:
                for pagina in range(1, PAGINAS_MAX + 1):
                    lista = pagina_binance(asset, taker, pagina)
                    for a in lista:
                        puesto += 1
                        adv, quien = a.get('adv') or {}, a.get('advertiser') or {}
                        n, uid = str(adv.get('advNo')), str(quien.get('userNo') or quien.get('nickName') or '')
                        if not yo.get('userNo') and n in mios and uid:   # aprende quién sos
                            yo = {'userNo': uid, 'apodo': quien.get('nickName') or ''}
                            with open(YO, 'w', encoding='utf-8') as f:
                                json.dump(yo, f)
                            log(f"Aprendí tu usuario de Binance: {yo['apodo']}")
                        if (uid and uid == yo.get('userNo')) or n in mios:
                            mias.append({'precio': float(adv['price']), 'puesto': puesto, 'ad': n,
                                         'metodos': [m.get('tradeMethodName') or m.get('identifier') or ''
                                                     for m in adv.get('tradeMethods') or []]})
                        elif mejor is None:
                            mejor = float(adv['price'])
                    if len(lista) < 20:
                        completo = True
                        break
            except Exception as e:  # noqa: BLE001
                log(f'Binance {asset} {taker}: {e}')
                ESTADO_BINANCE['error'] = f'Binance no respondió: {e}'[:160]
                continue
            clave = f'{tipo}|{asset}'
            ESTADO_BINANCE['grupos'] += 1
            if mias:
                m = mias[0]   # el mejor ubicado
                vivos[clave] = dict(m, tipo=tipo, cripto=asset, visible=True, total=puesto, completo=completo,
                                    mejor=mejor, cuantos=len(mias))
                ESTADO_BINANCE['encontrados'] += 1
            elif completo and puesto and yo.get('userNo'):   # listado vacío = no sé
                vivos[clave] = {'tipo': tipo, 'cripto': asset, 'visible': False, 'revisados': puesto}
            if not completo:
                log(f'Binance {asset} {taker}: más de {puesto} anuncios, no lo recorrí entero')
    ESTADO_BINANCE['usuario'] = yo.get('apodo', '')
    log(f"Binance en vivo: {ESTADO_BINANCE['encontrados']} grupos con anuncio tuyo visible")
    return vivos


ESTADO_BINANCE = {}

BITGET = os.path.join(CARPETA, 'bitget.json')   # lo que cargaste a mano de Bitget (no está en el repo)
BITGET_CAMPOS = {'ordenes': (0, 100000), 'usuarios': (0, 100000), 'tasa': (0, 100), 'volumen': (0, 10000000)}


def guardar_bitget(cuerpo):
    """Valida y guarda los números de Bitget que cargaste a mano. Devuelve (dict guardado, error)."""
    try:
        entrada = json.loads(cuerpo.decode('utf-8'))
    except Exception:  # noqa: BLE001
        return None, 'no entendí los datos'
    if not isinstance(entrada, dict):
        return None, 'no entendí los datos'
    nuevo = {}
    for campo, (lo, hi) in BITGET_CAMPOS.items():
        try:
            v = float(str(entrada.get(campo, '')).replace(',', '.'))
        except ValueError:
            return None, f'falta o está mal: {campo}'
        if not lo <= v <= hi:
            return None, f'fuera de rango: {campo}'
        nuevo[campo] = v
    alta = str(entrada.get('alta') or '')
    if alta and not (len(alta) == 10 and alta[4] == '-' and alta[7] == '-' and alta.replace('-', '').isdigit()):
        return None, 'la fecha de alta va como AAAA-MM-DD'
    nuevo['alta'] = alta
    nuevo['cargado'] = int(time.time())
    tmp = BITGET + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(nuevo, f)
    os.replace(tmp, BITGET)
    log(f'Bitget a mano: {nuevo}')
    return nuevo, ''


def actualizar(okx=False):
    """Pide los números al Apps Script. Si falla, deja el data.json anterior y anota el error."""
    try:
        url = URL + ('&okx=1' if okx else '')   # okx=1: el Apps Script trae antes las órdenes de OKX
        vivos = anuncios_binance_vivos()
        if vivos:
            url += '&vivos=' + urllib.parse.quote(json.dumps(vivos, separators=(',', ':')))
        with urllib.request.urlopen(url, timeout=90) as r:   # sigue solo la redirección de Google
            datos = json.loads(r.read().decode('utf-8'))
        if 'error' in datos:
            raise ValueError(datos['error'])
        datos['servidor'] = {'ok': True, 'hora': int(time.time()), 'binance': ESTADO_BINANCE,
                             'telefono': {'activo': bool(NTFY_TEMA), 'pedido': TELEFONO['pedido']}}
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


def pedir_al_telefono():
    """Le pide al teléfono (por ntfy, tema-cmd) que suba ya las órdenes de Binance y Bybit, y 90 s después
    vuelve a pedir los números a la planilla. Como mucho una vez cada 2 min. Devuelve True si mandó el pedido."""
    if not NTFY_TEMA or time.time() - TELEFONO['pedido'] < 120:
        return False
    try:
        req = urllib.request.Request(f'https://ntfy.sh/{NTFY_TEMA}-cmd', data=b'subir-ordenes')
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e:  # noqa: BLE001
        log(f'No pude avisarle al teléfono: {e}')
        return False
    TELEFONO['pedido'] = int(time.time())
    log('Le pedí al teléfono que suba las órdenes')

    def despues():
        time.sleep(90)
        actualizar()
    threading.Thread(target=despues, daemon=True).start()
    return True


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

    def _autorizado(self):
        if CLAVE and hmac.compare_digest(self.headers.get('Authorization', ''), ESPERADO):
            return True
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm="Brujula P2P", charset="UTF-8"')
        self.send_header('Content-Length', '0')
        self.end_headers()
        return False

    def do_POST(self):
        if not self._autorizado():
            return
        if self.path.split('?')[0] != '/bitget':
            return self._mandar(404, b'', 'text/plain')
        # Solo JSON: un formulario de otra página no puede mandarlo sin permiso del navegador.
        largo = int(self.headers.get('Content-Length') or 0)
        if not self.headers.get('Content-Type', '').startswith('application/json') or not 0 < largo <= 2000:
            return self._mandar(400, b'{"error":"pedido invalido"}', 'application/json')
        guardado, error = guardar_bitget(self.rfile.read(largo))
        if error:
            return self._mandar(400, json.dumps({'error': error}).encode(), 'application/json; charset=utf-8')
        self._mandar(200, json.dumps(guardado).encode(), 'application/json; charset=utf-8')

    def do_GET(self):
        if not self._autorizado():
            return
        ruta = self.path.split('?')[0]
        if ruta == '/bitget.json':
            try:
                with open(BITGET, 'rb') as f:
                    return self._mandar(200, f.read(), 'application/json; charset=utf-8')
            except FileNotFoundError:
                return self._mandar(200, b'{}', 'application/json; charset=utf-8')
        if ruta in ('/', '/index.html'):
            archivo, tipo = 'index.html', 'text/html; charset=utf-8'
        elif ruta == '/data.json':
            archivo, tipo = 'data.json', 'application/json; charset=utf-8'
        elif ruta == '/actualizar':   # botón "actualizar ahora" de la página (como mucho 1 vez por minuto)
            global ULTIMO_PEDIDO
            pedir_al_telefono()   # el teléfono sube Binance y Bybit, y en 90 s se vuelve a calcular
            if time.time() - ULTIMO_PEDIDO > 60:
                ULTIMO_PEDIDO = time.time()
                actualizar(okx=True)   # OKX lo trae el Apps Script desde su API, en el momento
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
    log(f'Brújula P2P en el puerto {PUERTO}, actualiza cada {CADA // 60} min')
    ThreadingHTTPServer(('0.0.0.0', PUERTO), Pagina).serve_forever()
