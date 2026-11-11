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
            if ts and (not ultimo or ts > ultimo[0]):
                ultimo = (ts, ch.get('name') or ch['id'].split('@')[0])
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

    logs = docker('logs', '--since', '1h', 'waha')
    errs = len(re.findall(r'stream errored|Connection Closed|connection (?:closed|lost)', logs, re.I))
    if errs:
        anotar(2, AVISO if errs < 5 else FALLA, '%d cortes de conexión con WhatsApp en la última hora' % errs)
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
def etapa_planilla(url):
    if not url:
        anotar(4, AVISO, 'No sé cuál es el /exec (falta WEBAPP_URL en ~/.subir-ordenes.env)')
        return
    falso = json.dumps({'event': 'message', 'session': SESION, 'diagnostico': True,
                        'payload': {'fromMe': True, 'from': 'diagnostico@c.us', 'body': 'diagnostico'}}).encode()
    t0 = time.time()
    c, t = pedir(url, datos=falso, cabeceras={'Content-Type': 'application/json'}, espera=40)
    seg = time.time() - t0
    if 'ignorado_saliente' in t:
        anotar(4, OK if seg < 15 else AVISO, 'La planilla responde (%.1f s)' % seg)
    elif c == 0:
        anotar(4, FALLA, 'La planilla no responde: %s' % t[:80])
    else:
        anotar(4, FALLA, 'La planilla respondió raro (código %s): %s' % (c, re.sub(r'<[^>]+>', ' ', t)[:100].strip()))


# ---------------- Rastrear un cliente ----------------
def rastrear(texto):
    q = texto.lower().strip()
    dig = re.sub(r'\D', '', q)
    chats = chats_recientes(400)
    hallados = [c for c in chats
                if (len(dig) >= 6 and dig[-8:] in re.sub(r'\D', '', c['id']))
                or (q and not dig and q in str(c.get('name') or '').lower())]
    if not hallados:
        print('No encontré "%s" entre los chats de WAHA. Probá con el número.' % texto)
        return
    for c in hallados[:3]:
        nombre = c.get('name') or c['id'].split('@')[0]
        msgs = entrantes(c['id'], 8)
        print('%s (%s)' % (nombre, c['id'].split('@')[0]))
        if not msgs:
            print('  WAHA no tiene mensajes entrantes de este chat.')
        for m in sorted(msgs, key=lambda m: int(m.get('timestamp') or 0), reverse=True)[:6]:
            tipo = '📷' if m.get('hasMedia') else '💬'
            cuerpo = re.sub(r'\s+', ' ', str(m.get('body') or ''))[:40]
            print('  %s %s %s' % (hora(int(m.get('timestamp') or 0)), tipo, cuerpo))
    print('Si el 📷 está acá, WAHA lo recibió: el corte fue después (planilla, lectura o pre-orden).')
    print('Si no está y vos lo ves en el teléfono, WAHA no lo recibió (sorda).')


def main():
    modo = sys.argv[1] if len(sys.argv) > 1 else 'todo'
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
    seguro(4, etapa_planilla, url)

    peor = FALLA if any(n == FALLA for _, n, _ in resultados) else AVISO if any(n == AVISO for _, n, _ in resultados) else OK
    if modo == 'vigilar' and peor != FALLA:
        return 0
    malas = [(e, t) for e, n, t in resultados if n == peor and n != OK]
    if not malas:
        print('%s Todo bien en etapas 1-4 (VPS, WAHA, webhook, planilla)' % OK)
    else:
        e, t = malas[0]
        extra = len([1 for _, n, _ in resultados if n != OK]) - 1
        print('%s Etapa %d: %s%s' % (peor, e, t, ' (y %d más)' % extra if extra else ''))
    nombres = {1: 'VPS', 2: 'WAHA recibe', 3: 'Webhook', 4: 'Planilla'}
    for etapa in sorted(nombres):
        print('— %d %s' % (etapa, nombres[etapa]))
        for e, n, t in resultados:
            if e == etapa:
                print('  %s %s' % (n, t))
    print('— 5-6 Movimientos y pre-orden: todavía no (parte 2)')
    return 2 if peor == FALLA else 1 if peor == AVISO else 0


if __name__ == '__main__':
    sys.exit(main())
