#!/usr/bin/env python3
"""Alarma en el teléfono por las órdenes de TUS anuncios de Binance P2P (compra y venta).

La app de Binance no avisa bien y, si no atendés a tiempo, las órdenes se cancelan y te cierran el anuncio
(16/11: 9 ventas canceladas por compradores entre 12:23 y 14:46 → anuncios de venta cerrados por 1 día).
Cada 30 s mira tus órdenes (key de solo lectura, la de ~/.subir-ordenes.env) y avisa con notificación + sonido + voz:
  - COMPRA abierta en tu anuncio, esperando que pagues: pitidos agudos al máximo, repite cada 5 min.
    "YA ME ENTERÉ" la calla 30 min; si después sigue sin pagar, vuelve con más pitidos.
  - VENTA nueva en tu anuncio: un ding-ding ("caja registradora") al 75% del volumen. Si en 10 min no tocaste
    "YA ME ENTERÉ", suena UNA vez más al máximo y nada más. Pagada, liberada o cancelada: no suena.

  python alerta_compras.py            # queda corriendo (lo arranca telefono/alerta.sh)
  python alerta_compras.py --probar   # una sola vuelta, muestra lo que ve y suena una alarma de prueba
"""
import argparse
import json
import math
import os
import struct
import subprocess
import sys
import time
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from subir_ordenes import firmar_y_pedir, hora_binance_ms, leer_env  # noqa: E402

CADA_S = 30
HORA_MS = 3600 * 1000
VENTANA_VENTAS_H = 6                      # ventana de ventas que se piden a Binance
HOME = os.path.expanduser('~')
PITIDOS = {False: 3, True: 10}            # alarma normal / alarma después de "YA ME ENTERÉ"
CANCELADAS = ('CANCELLED', 'CANCELLED_BY_SYSTEM')
VOLUMEN_SUAVE = 0.75                      # ventas: primero al 75% del volumen multimedia...
SUBIR_VOLUMEN_S = 10 * 60                 # ...y si en 10 min no tocaste YA ME ENTERÉ, una vez más al máximo

# (tipo, estado de Binance) → qué decir. repetir/silencio en segundos; veces: máximo de alarmas por orden.
AVISOS = {
    ('BUY', 'PENDING'): 'compra', ('BUY', 'TRADING'): 'compra',
    ('SELL', 'PENDING'): 'venta', ('SELL', 'TRADING'): 'venta',
}
TEXTOS = {
    'compra': dict(repetir=5 * 60, silencio=30 * 60,
                   titulo='🚨 COMPRA ABIERTA: pagá %s', insiste='🚨🚨 SIGUE SIN PAGAR: %s',
                   voz='Orden de compra abierta. Pagá %s', voz_insiste='Todavía no pagaste la compra de %s'),
    'venta': dict(repetir=SUBIR_VOLUMEN_S, veces=2, sonido=1, silencio=7 * 24 * 3600,
                  titulo='💰 VENTA NUEVA: %s · abrí el chat', insiste='',
                  voz='Venta nueva de %s', voz_insiste=''),
}


def mis_ordenes(cfg, tipo, horas):
    """Órdenes de tus propios anuncios (MAKER) de las últimas `horas`, de compra (BUY) o venta (SELL)."""
    ahora = hora_binance_ms()
    r = firmar_y_pedir(cfg, {'tradeType': tipo, 'startTimestamp': ahora - horas * HORA_MS,
                             'endTimestamp': ahora, 'page': 1, 'rows': 50})
    return [dict(o, tradeType=tipo) for o in (r.get('data') or []) if o.get('advertisementRole') != 'TAKER']


def archivo_pitido(n):
    """WAV con n pitidos de 4000 Hz: bien agudo y todavía fuerte en el parlante de un teléfono."""
    ruta = os.path.join(HOME, '.alerta_pitido_%d.wav' % n)
    if not os.path.exists(ruta):
        tasa, tono, pausa = 44100, 0.25, 0.12
        muestras = []
        for _ in range(n):
            muestras += [int(32000 * math.sin(2 * math.pi * 4000 * i / tasa)) for i in range(int(tasa * tono))]
            muestras += [0] * int(tasa * pausa)
        with wave.open(ruta, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(tasa)
            w.writeframes(struct.pack('<%dh' % len(muestras), *muestras))
    return ruta, n * 0.37


# Sonidos para elegir el de las ventas (python alerta_compras.py --sonidos los toca uno por uno).
# Cada nota: (Hz al empezar, Hz al terminar, segundos, silencio después, campana). campana=True: golpe y se apaga.
DO, MI, SOL, DO2, MI2 = 1047, 1319, 1568, 2093, 2637
SONIDOS = {
    1: ('caja registradora: ding-ding agudo, como plata que entra',
        [(MI2, MI2, 0.35, 0.05, True), (DO2 * 2, DO2 * 2, 0.6, 0.3, True)]),   # elegida para las ventas (17/11)
    2: ('escalera: cuatro notas que suben rápido, dos veces',
        [(DO, DO, 0.11, 0.02, False), (MI, MI, 0.11, 0.02, False), (SOL, SOL, 0.11, 0.02, False),
         (DO2, DO2, 0.3, 0.35, False)] * 2),
    3: ('sirena corta: tres barridos de grave a agudo',
        [(700, 1800, 0.45, 0.12, False)] * 3),
}


def archivo_sonido(n):
    """WAV de la opción n de SONIDOS (se arma una vez y queda en ~)."""
    ruta = os.path.join(HOME, '.alerta_sonido_%d_v2.wav' % n)
    notas = SONIDOS[n][1]
    if not os.path.exists(ruta):
        tasa = 44100
        muestras = []
        for f0, f1, dura, pausa, campana in notas:
            total, fase = int(tasa * dura), 0.0
            for i in range(total):
                fase += 2 * math.pi * (f0 + (f1 - f0) * i / total) / tasa
                ataque = min(1.0, i / (tasa * 0.005))
                cola = math.exp(-5 * i / total) if campana else min(1.0, (total - i) / (tasa * 0.01))
                muestras.append(int(30000 * ataque * cola * math.sin(fase)))
            muestras += [0] * int(tasa * pausa)
        with wave.open(ruta, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(tasa)
            w.writeframes(struct.pack('<%dh' % len(muestras), *muestras))
    return ruta, sum(n_[2] + n_[3] for n_ in notas)


def tocar(ruta, dura, volumen=1.0):
    """Pone el volumen multimedia en `volumen` (fracción del máximo) mientras suena y después lo deja como estaba."""
    antes = None
    try:
        vols = json.loads(subprocess.run(['termux-volume'], capture_output=True, text=True).stdout or '[]')
        musica = next(v for v in vols if v.get('stream') == 'music')
        antes = musica['volume']
        subprocess.run(['termux-volume', 'music', str(max(1, round(musica['max_volume'] * volumen)))], check=False)
    except Exception:
        pass
    subprocess.run(['termux-media-player', 'play', ruta], check=False, capture_output=True)
    time.sleep(dura + 0.5)
    if antes is not None:
        subprocess.run(['termux-volume', 'music', str(antes)], check=False)


def pitar(n):
    tocar(*archivo_pitido(n))


def probar_sonidos():
    """Toca las opciones de venta al 75% del volumen, cada una dos veces y anunciada por voz."""
    for n, (desc, _) in sorted(SONIDOS.items()):
        print('Opción %d: %s' % (n, desc), flush=True)
        subprocess.run(['termux-tts-speak', '-s', 'ALARM', 'Opción %d' % n], check=False)
        time.sleep(0.5)
        for _ in range(2):
            tocar(*archivo_sonido(n), volumen=VOLUMEN_SUAVE)
            time.sleep(0.8)
        time.sleep(1.5)
    print('Para escuchar una sola de nuevo: python ~/bexo-scripts/alerta_compras.py --sonidos 2')


def marca_ya(n, clase):
    """Archivo que toca el botón YA ME ENTERÉ. Va por orden Y estado: callar 'venta nueva' no calla 'te pagaron'."""
    return os.path.join(HOME, '.alerta_ya_%s_%s' % (n[-9:], clase))


def montos(o):
    try:
        monto = '{:,}'.format(int(float(o.get('totalPrice')))).replace(',', '.')
        hablado = str(int(float(o.get('totalPrice'))))
    except (TypeError, ValueError):
        monto = hablado = str(o.get('totalPrice'))
    return '%s %s' % (monto, o.get('fiat') or ''), hablado


def notificar(id_, titulo, contenido, pitidos, frase, boton=None, sonido=None, volumen=1.0):
    cmd = ['termux-notification', '--id', id_, '--title', titulo, '--content', contenido,
           '--icon', 'warning', '--led-color', 'ff0000',
           '--priority', 'max', '--vibrate', '1000,500,1000,500,1000']
    if boton:
        cmd += ['--button1', 'YA ME ENTERÉ', '--button1-action', 'touch %s; termux-notification-remove %s' % (boton, id_)]
    subprocess.run(cmd, check=False)
    if sonido:
        tocar(*archivo_sonido(sonido), volumen=volumen)
    else:
        pitar(pitidos)
    subprocess.run(['termux-tts-speak', '-s', 'ALARM', frase], check=False)


# Cómo se dice cada método de pago (se busca el pedazo, sin mayúsculas ni acentos, en lo que manda Binance).
BANCOS = (('prex', 'Prex'), ('itau', 'Itaú'), ('midinero', 'Mi Dinero'), ('redpagos', 'Mi Dinero'),
          ('mercado', 'Mercado Pago'), ('oca', 'OCA'))
CAMPOS_METODO = ('payMethodName', 'tradeMethodName', 'payMethod', 'payType')


def banco(o):
    """Método de pago de la orden dicho lindo ('Prex', 'Itaú'…), o '' si Binance no lo manda."""
    crudo = next((str(o[k]) for k in CAMPOS_METODO if o.get(k)), '')
    plano = crudo.lower().replace('ú', 'u').replace(' ', '').replace('_', '')
    return next((lindo for clave, lindo in BANCOS if clave in plano), crudo)


def sonar(o, clase, insiste=False, fuerte=True):
    """fuerte=False: las ventas suenan al 75% del volumen; si en 10 min no tocaste YA ME ENTERÉ, una vez más al máximo."""
    n = str(o.get('orderNumber'))
    t = TEXTOS[clase]
    monto, hablado = montos(o)
    if clase == 'venta' and banco(o):
        monto, hablado = '%s por %s' % (monto, banco(o)), '%s por %s' % (hablado, banco(o))
    cant = '%s %s' % (o.get('amount'), o.get('asset'))
    minutos = int((hora_binance_ms() - int(o.get('createTime') or 0)) / 60000)
    notificar(n[-9:], t['insiste' if insiste else 'titulo'] % monto,
              '%s · abierta hace %d min · orden …%s' % (cant, minutos, n[-6:]),
              PITIDOS[insiste], t['voz_insiste' if insiste else 'voz'] % hablado, boton=marca_ya(n, clase),
              sonido=t.get('sonido'), volumen=1.0 if fuerte else VOLUMEN_SUAVE)
    print(time.strftime('%Y-%m-%d %H:%M:%S'), 'alarma', clase, 'insiste' if insiste else '', monto, '…' + n[-6:],
          flush=True)


class Estado:
    def __init__(self):
        self.avisadas = {}          # orden → (clase, cuándo sonó la última vez)


def revisar_activas(activas, est, ahora, limpiar=True):
    for o, clase in activas:
        n = str(o.get('orderNumber'))
        marca = marca_ya(n, clase)
        ya = os.path.getmtime(marca) if os.path.exists(marca) else 0
        t = TEXTOS[clase]
        if ya and ahora - ya < t['silencio']:
            continue
        clase_antes, ultimo, primera, veces = est.avisadas.get(n, (None, 0, ahora, 0))
        if clase_antes != clase:
            ultimo, primera, veces = 0, ahora, 0
        if veces >= t.get('veces', 10 ** 9):
            continue
        # Al terminar el silencio suena enseguida; después, cada `repetir` hasta otro "YA ME ENTERÉ".
        if ahora - ultimo >= t['repetir'] or (ya and ultimo < ya + t['silencio']):
            sonar(o, clase, insiste=bool(ya), fuerte=clase != 'venta' or ahora - primera >= SUBIR_VOLUMEN_S)
            est.avisadas[n] = (clase, ahora, primera, veces + 1)
    if not limpiar:                         # Binance falló en una mitad: no borrar lo que no se pudo ver
        return
    vivas = {str(o.get('orderNumber')): clase for o, clase in activas}
    for n in list(est.avisadas):
        if n not in vivas:
            del est.avisadas[n]
            subprocess.run(['termux-notification-remove', n[-9:]], check=False)
    for archivo in os.listdir(HOME):        # borra las marcas de órdenes que ya no esperan nada
        if archivo.startswith('.alerta_ya_'):
            partes = archivo[len('.alerta_ya_'):].split('_', 1)
            if not any(n[-9:] == partes[0] and vivas[n] == (partes[1] if len(partes) > 1 else '') for n in vivas):
                try:
                    os.remove(os.path.join(HOME, archivo))
                except OSError:
                    pass


def vuelta(cfg, est):
    """Una revisión. Si Binance falla en compras o en ventas, la otra mitad igual se revisa."""
    activas, error = [], None
    ventas = None
    for tipo, horas in (('BUY', 2), ('SELL', VENTANA_VENTAS_H)):
        try:
            lista = mis_ordenes(cfg, tipo, horas)
        except (Exception, SystemExit) as e:
            error = e
            continue
        if tipo == 'SELL':
            ventas = lista
        activas += [(o, AVISOS[(tipo, o.get('orderStatus'))]) for o in lista
                    if (tipo, o.get('orderStatus')) in AVISOS]
    revisar_activas(activas, est, time.time(), limpiar=error is None)
    if error:
        raise error
    return activas, ventas or []


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--probar', action='store_true')
    ap.add_argument('--sonidos', nargs='?', type=int, const=0, help='prueba los sonidos de venta (o solo el número dado)')
    args = ap.parse_args()
    if args.sonidos is not None:
        if args.sonidos:
            tocar(*archivo_sonido(args.sonidos), volumen=VOLUMEN_SUAVE)
        else:
            probar_sonidos()
        sys.exit(0)
    cfg = leer_env()
    if args.probar:
        est = Estado()
        activas, ventas = vuelta(cfg, est)
        for clase in ('compra', 'venta'):
            print('%-8s' % clase, sum(1 for _, c in activas if c == clase))
        print('Ventas de tus anuncios en las últimas %d h: %d (canceladas: %d)' % (
            VENTANA_VENTAS_H, len(ventas), sum(1 for o in ventas if o.get('orderStatus') in CANCELADAS)))
        # Qué campos manda Binance en tus ventas (para confirmar de dónde sale el banco). No muestra apodos.
        ultimas = mis_ordenes(cfg, 'SELL', 72)
        if ultimas:
            o = ultimas[0]
            print('Campos de tu última venta:', ', '.join(sorted(o)))
            print('Banco que se diría:', repr(banco(o)),
                  {k: o.get(k) for k in o if any(x in k.lower() for x in ('pay', 'method', 'bank'))})
        else:
            print('No hay ventas en las últimas 72 h para ver los campos')
        sonar({'orderNumber': '000000000', 'totalPrice': '1500', 'fiat': 'UYU', 'amount': '34.48',
               'asset': 'USDT', 'createTime': hora_binance_ms(), 'payMethodName': 'Prex'}, 'venta')
        sys.exit(0)
    est = Estado()
    print(time.strftime('%Y-%m-%d %H:%M'), 'alerta de compras y ventas arrancada', flush=True)
    while True:
        try:
            vuelta(cfg, est)
        except (Exception, SystemExit) as e:   # sin internet o Binance caído: sigue intentando
            print(time.strftime('%Y-%m-%d %H:%M'), 'error:', e, flush=True)
        time.sleep(CADA_S)
