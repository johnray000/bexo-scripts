#!/usr/bin/env python3
"""Diagnóstico del bot por etapas (corre en el VPS; lo llama el botón del teléfono por SSH).

  python3 diagnostico.py                 todas las etapas, resumen arriba y detalle abajo
  python3 diagnostico.py vigilar         lo mismo, pero no imprime nada si todo está bien
  python3 diagnostico.py rastrear TEXTO  últimos mensajes de un cliente (nombre o número) que vio WAHA

Etapas:
  1 VPS        memoria, contenedor WAHA, relay Binance, túnel (MiDinero)
  2 WAHA       sesión WORKING, último mensaje ENTRANTE (detecta "sorda"), errores de stream
  3 Webhook    apunta al /exec de la planilla con el evento message
  4 Planilla   el /exec responde (mensaje falso "saliente": la planilla lo ignora, no guarda nada)
  5-6          Movimientos y pre-orden: los responde la planilla (parte 2, todavía no)

No manda mensajes, no cambia nada. Solo lee. Python 3.8, sin librerías extra.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

TZ = timezone(timedelta(hours=-3))
WAHA = 'http://localhost:8080'
RELAY = 'http://localhost:8082'
SESION = 'default'
HOME = os.path.expanduser('~')

OK, AVISO, FALLA = '✅', '⚠️', '❌'
resultados = []   # (etapa, nivel, texto)


def anotar(etapa, nivel, texto):
    resultados.append((etapa, nivel, texto))


def leer_env(ruta, clave, sudo=False):
    try:
        if sudo:
            txt = subprocess.run(['sudo', '-n', 'cat', ruta], capture_output=True, text=True, timeout=10).stdout
        else:
            txt = open(os.path.expanduser(ruta)).read()
    except Exception:
        return ''
    for linea in txt.splitlines():
        m = re.match(r'\s*(?:export\s+)?([A-Z_]*' + clave + r')\s*=\s*(.*)', linea)
        if m:
            return m.group(2).strip().strip('"\'')
    return ''


def pedir(url, datos=None, cabeceras=None, espera=20):
    """Devuelve (código, texto). Código 0 si no hubo respuesta."""
    req = urllib.request.Request(url, data=datos, headers=cabeceras or {})
    try:
        with urllib.request.urlopen(req, timeout=espera) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')
    except Exception as e:
        return 0, str(e)


def hace(seg):
    seg = int(seg)
    if seg < 90:
        return '%d s' % seg
    if seg < 5400:
        return '%d min' % (seg // 60)
    if seg < 172800:
        return '%d h %02d min' % (seg // 3600, seg % 3600 // 60)
    return '%d días' % (seg // 86400)


def hora(ts):
    return datetime.fromtimestamp(ts, TZ).strftime('%d/%m %H:%M')


def cmd(*args):
    try:
        return subprocess.run(list(args), capture_output=True, text=True, timeout=15).stdout
    except Exception:
        return ''


def docker(*args):
    try:
        r = subprocess.run(['sudo', '-n', 'docker'] + list(args), capture_output=True, text=True, timeout=30)
        return r.stdout + r.stderr
    except Exception as e:
        return str(e)


CLAVE = leer_env('~/waha.env', 'API_KEY')
CAB = {'X-Api-Key': CLAVE, 'Accept': 'application/json'}


def waha_json(ruta, espera=20):
    c, t = pedir(WAHA + ruta, cabeceras=CAB, espera=espera)
    if c != 200:
        return None, c
    try:
        return json.loads(t), c
    except ValueError:
        return None, c


def es_chat_de_persona(cid):
    return not (cid.endswith('@g.us') or cid.startswith('status@') or cid.endswith('@newsletter') or cid.endswith('@broadcast'))


def chats_recientes(n):
    chats, _ = waha_json('/api/%s/chats?limit=%d&sortBy=conversationTimestamp&sortOrder=desc' % (SESION, n))
    if not isinstance(chats, list):   # versiones de WAHA sin orden: se traen todos y se ordenan acá
        chats, _ = waha_json('/api/%s/chats?limit=5000' % SESION, espera=40)
    if not isinstance(chats, list):
        return []
    chats = [c for c in chats if es_chat_de_persona(str(c.get('id', '')))]
    chats.sort(key=lambda c: -int(c.get('conversationTimestamp') or c.get('timestamp') or 0))
    return chats


def entrantes(chat_id, n=3):
    msgs, _ = waha_json('/api/%s/chats/%s/messages?limit=%d&downloadMedia=false&filter.fromMe=false'
                        % (SESION, urllib.parse.quote(chat_id), n))
    return [m for m in (msgs or []) if not m.get('fromMe')]


# ---------------- Etapa 1: VPS ----------------
def etapa_vps():
    mem = {}
    for linea in open('/proc/meminfo'):
        k, v = linea.split(':')
        mem[k] = int(v.split()[0]) // 1024
    disp = mem.get('MemAvailable', 0)
    swap = mem.get('SwapTotal', 0) - mem.get('SwapFree', 0)
    nivel = FALLA if disp < 120 else AVISO if disp < 200 else OK
    anotar(1, nivel, 'Memoria libre %d MB de %d (swap usada %d MB)' % (disp, mem.get('MemTotal', 0), swap))

    pesados = cmd('pgrep', '-f', 'chrom').strip()
    if pesados:
        anotar(1, AVISO, 'Hay Chrome/Chromium corriendo en el VPS (le quita memoria a WAHA)')

    estado = docker('inspect', '-f', '{{.State.Status}} {{.State.StartedAt}}', 'waha').strip()
    if not estado.startswith('running'):
        anotar(1, FALLA, 'El contenedor de WAHA no está corriendo (%s)' % (estado[:80] or 'sin respuesta'))
    else:
        try:
            ini = datetime.strptime(estado.split()[1][:19], '%Y-%m-%dT%H:%M:%S').replace(tzinfo=timezone.utc)
            anotar(1, OK, 'WAHA prendido hace %s' % hace(time.time() - ini.timestamp()))
        except Exception:
            anotar(1, OK, 'WAHA prendido')

    token = leer_env('/etc/relay-binance.env', 'RELAY_TOKEN', sudo=True)
    t0 = time.time()
    c, t = pedir('%s/anuncios?token=%s&fiat=VES&tipo=SELL&filas=1' % (RELAY, urllib.parse.quote(token)), espera=25)
    if c == 200:
        anotar(1, OK, 'Relay Binance responde (%.1f s)' % (time.time() - t0))
    else:
        anotar(1, FALLA, 'Relay Binance no responde (código %s)' % c)

    tunel = cmd('ss', '-ltn')
    if ':1080 ' in tunel:
        anotar(1, OK, 'Túnel del teléfono conectado (MiDinero)')
    else:
        anotar(1, AVISO, 'Túnel del teléfono desconectado (solo hace falta para MiDinero los martes)')


ENTRANTES_POR_CHAT = {}   # último mensaje entrante por chat según WAHA (lo llena etapa_waha, lo cruza la etapa 5)
CORTE_RE = re.compile(r'stream errored|connection (?:closed|lost|failure)|conflict|logged ?out|restart required', re.I)


def cortes_waha(desde):
    """Cortes con WhatsApp según el log de WAHA. Las líneas a menos de 60 s entre sí cuentan como UN corte
    (un corte deja varias líneas: error, cierre, reconexión). Devuelve [(datetime, primera línea), ...]."""
    eventos = []
    for linea in docker('logs', '--since', desde, '--timestamps', 'waha').splitlines():
        if not CORTE_RE.search(linea):
            continue
        try:
            ts = datetime.strptime(linea[:19], '%Y-%m-%dT%H:%M:%S').replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if eventos and (ts - eventos[-1][0]).total_seconds() < 60:
            continue
        eventos.append((ts, linea[31:].strip()[:160]))
    return eventos


# ---------------- Etapa 2: WAHA recibe ----------------
def etapa_waha():
    ses, c = waha_json('/api/sessions/%s' % SESION)
    if not ses:
        anotar(2, FALLA, 'WAHA no contesta (código %s)' % c)
        return None
    st = ses.get('status')
    anotar(2, OK if st == 'WORKING' else FALLA, 'Sesión %s' % st)

    ultimo = None   # (ts, quién)
    for ch in chats_recientes(12)[:6]:
        for m in entrantes(ch['id'], 2):
            ts = int(m.get('timestamp') or 0)
            quien = ch.get('name') or ch['id'].split('@')[0]
            if ts:
                ENTRANTES_POR_CHAT[quien] = max(ts, ENTRANTES_POR_CHAT.get(quien, 0))
            if ts and (not ultimo or ts > ultimo[0]):
                ultimo = (ts, quien)
    ahora = time.time()
    if not ultimo:
        anotar(2, AVISO, 'No encontré mensajes entrantes en WAHA')
    else:
        edad = ahora - ultimo[0]
        local = datetime.fromtimestamp(ahora, TZ).hour
        de_dia = 9 <= local < 23
        nivel = AVISO if (de_dia and edad > 2 * 3600) else OK
        txt = 'Último mensaje ENTRANTE: %s, hace %s (%s)' % (hora(ultimo[0]), hace(edad), ultimo[1])
        if nivel == AVISO:
            txt += '. Si alguien te escribió después, WAHA está sorda'
        anotar(2, nivel, txt)

    ev = cortes_waha('1h')
    if ev:
        # Solo aviso: si WAHA sigue WORKING y recibiendo, los cortes no son una falla (todavía). Se investigan aparte.
        anotar(2, AVISO, '%d cortes con WhatsApp en la última hora (último %s). Detalle: diagnostico.py cortes'
               % (len(ev), ev[-1][0].astimezone(TZ).strftime('%H:%M')))
    return ses


# ---------------- Etapa 3: webhook ----------------
def etapa_webhook(ses):
    exec_url = leer_env('~/.subir-ordenes.env', 'WEBAPP_URL')
    if not ses:
        anotar(3, AVISO, 'No se pudo revisar (WAHA no contesta)')
        return exec_url
    hooks = (ses.get('config') or {}).get('webhooks') or []
    if not hooks:
        anotar(3, FALLA, 'WAHA no tiene webhook configurado: los mensajes no llegan a la planilla')
        return exec_url
    h = hooks[0]
    url, eventos = h.get('url', ''), h.get('events') or []
    if 'message' not in eventos and 'message.any' not in eventos:
        anotar(3, FALLA, 'El webhook no tiene el evento "message" (tiene %s)' % ','.join(eventos))
    elif exec_url and url.rstrip('/') != exec_url.rstrip('/'):
        anotar(3, AVISO, 'El webhook apunta a otro /exec que el de ~/.subir-ordenes.env. ¿Cambió la implementación?')
    else:
        anotar(3, OK, 'Webhook configurado al /exec de la planilla')
    logs = docker('logs', '--since', '1h', 'waha')
    errs = len(re.findall(r'webhook[^\n]*(?:error|fail|timeout|ECONN)', logs, re.I))
    if errs:
        anotar(3, AVISO, '%d errores de entrega del webhook en la última hora' % errs)
    return url or exec_url


# ---------------- Etapa 4: la planilla responde ----------------
def consultar_planilla(url, buscar=''):
    """Pide a la planilla las etapas 5-6 (18_Diagnostico.gs). Devuelve (dict|None, código, texto, segundos).
    Va marcado fromMe: si la planilla todavía no tiene 18_Diagnostico.gs, doPost lo ignora sin guardar nada."""
    token = leer_env('~/.subir-ordenes.env', 'ORDENES_TOKEN')
    cuerpo = json.dumps({'diagnostico': True, 'token': token, 'buscar': buscar, 'event': 'message', 'session': SESION,
                         'payload': {'fromMe': True, 'from': 'diagnostico@c.us', 'body': 'diagnostico'}}).encode()
    t0 = time.time()
    c, t = pedir(url, datos=cuerpo, cabeceras={'Content-Type': 'application/json'}, espera=60)
    seg = time.time() - t0
    try:
        return json.loads(t), c, t, seg
    except ValueError:
        return None, c, t, seg


def etapa_planilla(url):
    if not url:
        anotar(4, AVISO, 'No sé cuál es el /exec (falta WEBAPP_URL en ~/.subir-ordenes.env)')
        return None
    d, c, t, seg = consultar_planilla(url)
    lenta = AVISO if seg > 40 else OK   # Apps Script tarda varios segundos en arrancar en frío
    if d and d.get('ok'):
        anotar(4, lenta, 'La planilla responde (%.1f s)' % seg)
        return d
    if 'ignorado_saliente' in t:
        anotar(4, lenta, 'La planilla responde (%.1f s)' % seg)
        anotar(5, AVISO, 'Falta instalar 18_Diagnostico.gs en Apps Script (ver diagnostico/LEEME.md)')
        return None
    if d and d.get('error') == 'no autorizado':
        anotar(4, lenta, 'La planilla responde (%.1f s)' % seg)
        anotar(5, AVISO, 'La planilla no aceptó el token (ORDENES_TOKEN de ~/.subir-ordenes.env)')
        return None
    if d and d.get('error'):
        anotar(4, FALLA, 'La planilla dio error: %s' % d['error'][:100])
    elif c == 0:
        anotar(4, FALLA, 'La planilla no responde: %s' % t[:80])
    else:
        anotar(4, FALLA, 'La planilla respondió raro (código %s): %s' % (c, re.sub(r'<[^>]+>', ' ', t)[:100].strip()))
    return None


def desc(f):
    return '%s %s %s %s' % (hora(f['recibido'] / 1000), f['nombre'][:18], f['moneda'] or '', ('%g' % f['monto']) if f['monto'] else '')


# ---------------- Etapas 5 y 6: Movimientos y pre-orden ----------------
ESPERA_MIN = 10   # un comprobante sin leer o sin pre-orden después de esto es sospechoso


def etapas_planilla(d):
    ahora = d['ahora'] / 1000
    comp = d.get('comprobantes') or []

    # 5: llegó a Movimientos y se leyó
    if comp:
        anotar(5, OK, '%d comprobantes en 24 h, el último %s (%s)' % (len(comp), hora(comp[0]['recibido'] / 1000), comp[0]['nombre'][:20]))
    else:
        anotar(5, OK, 'Sin comprobantes en las últimas 24 h')
    # Último mensaje que llegó a la planilla (Buffer, Bandeja_Entrada o Historial; el Buffer solo se vacía).
    # Si la planilla es vieja y no lo manda, no se cruza: mejor no decir nada que dar una falla falsa.
    ult = (d.get('ultimoMensaje') or 0) / 1000
    if 'ultimoMensaje' in d:
        sin_msj = ahora - ult if ult else 999999
        de_dia = 9 <= datetime.fromtimestamp(ahora, TZ).hour < 23
        txt = 'Último mensaje que llegó a la planilla: %s' % (('%s, hace %s' % (hora(ult), hace(sin_msj))) if ult else 'ninguno')
        # De día, 2 h sin ningún mensaje es lo que pasa cuando WAHA queda sorda (10/11 y 11/11). Es falla, no aviso:
        # si de verdad nadie escribió, el costo es tocar DIAGNÓSTICO una vez.
        if de_dia and sin_msj > 2 * 3600:
            waha_mas_nuevo = [q for q, ts in ENTRANTES_POR_CHAT.items() if ts > ult + 600]
            causa = ('WAHA sí recibió (%s): el webhook no entrega' % ', '.join(waha_mas_nuevo[:2])) if waha_mas_nuevo \
                else 'WAHA tampoco recibió nada: probablemente sorda (re-vincular)'
            anotar(5, FALLA, '%s. %s' % (txt, causa))
        else:
            anotar(5, OK, txt)
        # Cruce WAHA ↔ planilla: 2+ chats con mensajes en WAHA que la planilla nunca vio (10 min de margen).
        # Se exigen 2 chats para no confundir con un número bloqueado a propósito (BLACKLIST de doPost).
        perdidos = [q for q, ts in ENTRANTES_POR_CHAT.items() if ts > ult + 600 and ahora - ts > 600]
        if len(perdidos) >= 2 and not (de_dia and sin_msj > 2 * 3600):
            anotar(5, FALLA, 'WAHA recibió mensajes de %s que no llegaron a la planilla (webhook cortado)' % ', '.join(perdidos[:3]))
    else:
        anotar(5, AVISO, 'Actualizá 18_Diagnostico.gs (la versión instalada no dice cuándo llegó el último mensaje)')
    trabados = [f for f in comp if f['estado'] == 'PENDIENTE' and ahora - f['recibido'] / 1000 > ESPERA_MIN * 60]
    for f in trabados[:3]:
        anotar(5, FALLA, 'Sin leer (PENDIENTE hace %s): %s' % (hace(ahora - f['recibido'] / 1000), desc(f)))
    revisar = [f for f in comp if f['estado'] == 'REVISAR']
    for f in revisar[:3]:
        anotar(5, AVISO, 'En REVISAR, no sale pre-orden hasta que lo revises: %s' % desc(f))
    if len(revisar) > 3:
        anotar(5, AVISO, 'y %d más en REVISAR' % (len(revisar) - 3))
    if d.get('lecturaAgendadaHace') and d['lecturaAgendadaHace'] > 600:
        anotar(5, FALLA, 'Hay una lectura agendada hace %s que no corrió' % hace(d['lecturaAgendadaHace']))
    errs = d.get('errores') or []
    recientes = [e for e in errs if ahora - e['cuando'] / 1000 < 3600]
    if recientes:
        e = recientes[0]
        anotar(5, AVISO, '%d errores en Debug_Errores la última hora. Último: %s %s' % (len(recientes), e['etapa'], e['detalle'][:60]))
    elif errs:
        anotar(5, OK, '%d errores en Debug_Errores en 24 h (ninguno en la última hora)' % len(errs))

    # 6: salió la pre-orden
    if d.get('preorden') is False:
        anotar(6, FALLA, 'Pre-órdenes APAGADAS (casilla K3 del Dashboard)')
    sin = [f for f in comp if f['estado'] == 'LEIDO' and f['llevaPreorden'] and not f['orden']
           and ahora - f['recibido'] / 1000 > ESPERA_MIN * 60 and f['monto'] > 0]
    for f in sin[:3]:
        anotar(6, FALLA, 'Leído y sin pre-orden (hace %s): %s' % (hace(ahora - f['recibido'] / 1000), desc(f)))
    for f in [f for f in comp if f['orden'].upper().startswith('NO ENVIADA')][:3]:
        anotar(6, FALLA, 'Pre-orden NO ENVIADA (no te llegó): %s' % desc(f))
    for f in [f for f in comp if f['orden'].upper().startswith('ENVIANDO')
              and ahora - f['recibido'] / 1000 > 20 * 60][:3]:
        anotar(6, FALLA, 'Pre-orden trabada en ENVIANDO (no te llegó): %s' % desc(f))
    con = [f for f in comp if f['orden'] and not f['orden'].upper().startswith(('NO ENVIADA', 'ENVIANDO'))]
    if con:
        anotar(6, OK, 'Última pre-orden: %s (%s)' % (desc(con[0]), con[0]['orden']))
    elif d.get('preorden') is not False and not sin:
        anotar(6, OK, 'Ninguna pre-orden pendiente')


# ---------------- Rastrear un cliente ----------------
def fotos_waha(texto):
    """Fotos/PDF que WAHA recibió del cliente (nombre o número). Devuelve (nombre, [(ts, cuerpo)], detalle)."""
    q = texto.lower().strip()
    dig = re.sub(r'\D', '', q)
    chats = chats_recientes(400)
    hallados = [c for c in chats
                if (len(dig) >= 6 and dig[-8:] in re.sub(r'\D', '', c['id']))
                or (q and not dig and q in str(c.get('name') or '').lower())]
    fotos, detalle, nombre = [], [], ''
    for c in hallados[:3]:
        nombre = nombre or c.get('name') or c['id'].split('@')[0]
        for m in entrantes(c['id'], 15):
            ts = int(m.get('timestamp') or 0)
            cuerpo = re.sub(r'\s+', ' ', str(m.get('body') or ''))[:40]
            detalle.append((ts, '📷' if m.get('hasMedia') else '💬', cuerpo, c.get('name') or c['id'].split('@')[0]))
            if m.get('hasMedia'):
                fotos.append((ts, cuerpo))
    return nombre, hallados, sorted(fotos, reverse=True), sorted(detalle, reverse=True)


def veredicto(f):
    """Qué pasó con un comprobante de Movimientos, en palabras."""
    plata = '%s %s' % (f['moneda'] or '', ('{:,.0f}'.format(f['monto']).replace(',', '.')) if f['monto'] else '')
    est, orden = f['estado'], f['orden']
    # 11_PreOrden marca "ENVIANDO …" y pasa a ENVIADA solo si WAHA contestó bien; "NO ENVIADA" = falló 3 veces
    if orden.upper().startswith('NO ENVIADA'):
        return '❌', '%s · pre-orden NO ENVIADA (falló el envío, mirá Debug_Errores)' % plata.strip()
    if orden.upper().startswith('ENVIANDO'):
        if time.time() - f['recibido'] / 1000 > 20 * 60:
            return '❌', '%s · pre-orden trabada en ENVIANDO, no te llegó' % plata.strip()
        return '⏳', '%s · pre-orden saliendo (ENVIANDO)' % plata.strip()
    if orden and orden != 'RECUPERADO':
        return '✅', '%s · pre-orden %s' % (plata.strip(), orden)
    if est == 'DESCARTADO':
        return '➖', 'DESCARTADO: el lector dijo que no era un comprobante'
    if est == 'DUPLICADO':
        return '➖', 'DUPLICADO: esa referencia ya estaba cargada'
    if est == 'REVISAR':
        return '⚠️', '%s · en REVISAR: revisalo en Movimientos para que salga la pre-orden' % plata.strip()
    if est == 'PENDIENTE':
        return '⏳', 'todavía sin leer (PENDIENTE)'
    if est == 'CONTADO':
        return '✅', '%s · CONTADO' % plata.strip()
    if est == 'LEIDO' and not f['llevaPreorden']:
        return '✅', '%s · leído (esta moneda/cuenta no lleva pre-orden)' % plata.strip()
    if est == 'LEIDO':
        return '❌', '%s · leído pero SIN pre-orden' % plata.strip()
    return '⚠️', '%s · %s' % (plata.strip(), est or 'sin estado')


def rastrear(texto):
    """Primero un veredicto por cada foto (lo que importa), después el detalle de WAHA y de la planilla."""
    nombre, hallados, fotos, detalle = fotos_waha(texto)
    ses, _ = waha_json('/api/sessions/%s' % SESION)
    hooks = ((ses or {}).get('config') or {}).get('webhooks') or []
    url = (hooks[0].get('url') if hooks else '') or leer_env('~/.subir-ordenes.env', 'WEBAPP_URL')
    d, c, t, seg = consultar_planilla(url, texto) if url else (None, 0, 'sin /exec', 0)
    planilla_ok = bool(d and d.get('ok'))
    filas = (d or {}).get('cliente') or []
    dirs = (d or {}).get('directorio') or []

    titulo = nombre or (dirs[0]['nombre'] if dirs else texto)
    print('Rastreo de %s' % titulo)
    if planilla_ok and not dirs:
        print('❌ No está en el Directorio: sus fotos se tiran y nunca generan comprobante. Agregalo al Directorio.')
    if not hallados:
        print('⚠️ WAHA no tiene un chat con "%s". Probá con el número.' % texto)

    # Cada foto de WAHA se empareja con la fila de Movimientos que llegó entre 2 min antes y 15 min después
    usadas = set()
    for ts, cuerpo in fotos[:6]:
        fila = None
        for k, f in enumerate(filas):
            if k not in usadas and -120 <= f['recibido'] / 1000 - ts <= 900:
                fila = (k, f)
                break
        if fila:
            usadas.add(fila[0])
            marca, txt = veredicto(fila[1])
        elif not planilla_ok:
            marca, txt = '❔', 'no pude consultar la planilla'
        elif time.time() - ts < 180:
            marca, txt = '⏳', 'recién llegó, todavía no está en la planilla'
        else:
            marca, txt = '❌', 'WAHA la recibió pero NO está en Movimientos. Avisame y la recuperamos (cargarFaltantes)'
        print('%s %s 📷 → %s' % (marca, hora(ts), txt))
    # Comprobantes de la planilla sin foto en WAHA (cargados a mano o recuperados)
    for k, f in enumerate(filas[:6]):
        if k not in usadas and f['recibido'] / 1000 > (fotos[-1][0] - 3600 if fotos else 0):
            marca, txt = veredicto(f)
            print('%s %s (en la planilla) → %s' % (marca, hora(f['recibido'] / 1000), txt))
    if not fotos and hallados:
        print('➖ WAHA no tiene fotos recientes de este cliente. Si vos las ves en el teléfono, WAHA no las recibió.')

    print('— Detalle WAHA')
    for ts, tipo, cuerpo, quien in detalle[:8]:
        print('  %s %s %s' % (hora(ts), tipo, cuerpo))
    print('— Detalle planilla')
    if not planilla_ok:
        print('  No pude consultarla (%s)' % ('falta instalar 18_Diagnostico.gs' if 'ignorado_saliente' in t else t[:80]))
    for f in filas[:6]:
        print('  %s · %s · %s' % (desc(f), f['estado'] or '¿?', f['orden'] or '-'))


def main():
    modo = sys.argv[1] if len(sys.argv) > 1 else 'todo'
    if modo == 'evidencia':   # para buscar la causa de fondo de la sordera: todo junto, para pegar en el chat
        print('== Ahora: %s' % datetime.now(TZ).strftime('%d/%m %H:%M'))
        # Dos contenedores con la misma sesión vinculada se pisan ("conflict"/"replaced") y uno queda sordo
        print('== Contenedores:\n%s' % docker('ps', '-a', '--format', '{{.Names}} | {{.Image}} | {{.Status}} | {{.Ports}}').strip())
        print('== Contenedor: %s' % docker('inspect', '-f', '{{.Config.Image}} reinicios={{.RestartCount}} desde={{.State.StartedAt}} oom={{.State.OOMKilled}}', 'waha').strip())
        print('== Motor: %s' % re.findall(r'WHATSAPP_DEFAULT_ENGINE=\w+', docker('inspect', '-f', '{{.Config.Env}}', 'waha')))
        print('== Memoria MB (total usada libre compartida cache disponible): %s' % ' '.join(cmd('free', '-m').split()[7:13]))
        print('== OOM del kernel (24 h): %s' % (cmd('sudo', '-n', 'journalctl', '-k', '--since', '24 hours ago', '--no-pager').lower().count('out of memory')))
        ev = cortes_waha('24h')
        print('== %d cortes en 24 h' % len(ev))
        for ts, txt in ev:
            print('%s  %s' % (ts.astimezone(TZ).strftime('%d/%m %H:%M:%S'), txt[:110]))
        ses, _ = waha_json('/api/sessions/%s' % SESION)
        print('== Sesión: %s' % json.dumps({k: (ses or {}).get(k) for k in ('status', 'engine', 'me')}, ensure_ascii=False)[:300])
        print('== Últimas 40 líneas raras del log (12 h)')
        raras = [l for l in docker('logs', '--since', '12h', '--timestamps', 'waha').splitlines()
                 if re.search(r'error|warn|fail|close|stream|decrypt|conflict|timeout|logout|restart', l, re.I)]
        for l in raras[-40:]:
            print(l[11:19], l[31:][:150])
        return 0
    if modo == 'cortes':   # para investigar el motivo: cada corte de las últimas 24 h con su línea de log
        ev = cortes_waha('24h')
        print('%d cortes con WhatsApp en 24 h' % len(ev))
        for ts, txt in ev:
            print('%s  %s' % (ts.astimezone(TZ).strftime('%d/%m %H:%M:%S'), txt))
        return 0
    if modo == 'rastrear':
        rastrear(' '.join(sys.argv[2:]))
        return 0
    def seguro(etapa, f, *a):
        try:
            return f(*a)
        except Exception as e:   # una etapa rota no corta el resto del diagnóstico
            anotar(etapa, FALLA, 'El chequeo falló: %s' % e)
    seguro(1, etapa_vps)
    ses = seguro(2, etapa_waha)
    url = seguro(3, etapa_webhook, ses)
    d = seguro(4, etapa_planilla, url)
    if d:
        seguro(5, etapas_planilla, d)

    peor = FALLA if any(n == FALLA for _, n, _ in resultados) else AVISO if any(n == AVISO for _, n, _ in resultados) else OK
    if modo == 'vigilar' and peor != FALLA:
        return 0
    nombres = {1: 'VPS', 2: 'WAHA', 3: 'Webhook', 4: 'Planilla', 5: 'Comprobantes', 6: 'Pre-órdenes'}

    def nivel(etapa):
        ns = [n for e, n, _ in resultados if e == etapa]
        return FALLA if FALLA in ns else AVISO if AVISO in ns else OK if ns else '·'
    # La notificación corta el texto largo: arriba las 6 etapas en una línea, después solo lo que no está bien
    # (fallas primero), y al final el detalle completo.
    print('%s %s' % (peor, ' · '.join('%d %s %s' % (e, nombres[e], nivel(e)) for e in sorted(nombres))))
    for marca in (FALLA, AVISO):
        for e, n, t in resultados:
            if n == marca:
                print('%s %d: %s' % (n, e, t))
    print('— Detalle')
    for etapa in sorted(nombres):
        print('— %d %s' % (etapa, nombres[etapa]))
        for e, n, t in resultados:
            if e == etapa:
                print('  %s %s' % (n, t))
    return 2 if peor == FALLA else 1 if peor == AVISO else 0


if __name__ == '__main__':
    sys.exit(main())
