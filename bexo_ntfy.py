#!/usr/bin/env python3
"""Avisos a la app ntfy desde el teléfono (lo mismo que apps-script/21_Ntfy.gs del lado de Google).

El tema está en ~/.bexo-ntfy (no en el repo: el repo es público y ntfy.sh también; el nombre es la única protección).
  tema()          → 'bexo-…' o '' si no está configurado
  publicar(...)   → manda un aviso al tema; no frena al que lo llama si ntfy no responde
"""
import json
import os
import threading
import urllib.request

NTFY_URL = 'https://ntfy.sh'
ARCHIVO_TEMA = os.path.expanduser('~/.bexo-ntfy')


def tema():
    try:
        with open(ARCHIVO_TEMA) as f:
            return f.read().strip()
    except OSError:
        return ''


def _enviar(cuerpo):
    try:
        req = urllib.request.Request(NTFY_URL, data=json.dumps(cuerpo).encode(),
                                     headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req, timeout=10).read()
    except (OSError, ValueError):
        pass                               # un aviso que no llega no puede frenar el recorrido


def publicar(titulo, texto, prioridad=3, tags=(), esperar=False, acciones=()):
    """Publica en el tema de ~/.bexo-ntfy. En un hilo aparte (no demora el recorrido); Python espera a que termine
    antes de salir, así el último aviso llega igual. esperar=True: lo manda antes de volver.
    acciones: botones de ntfy (máximo 3), ver botones_orden()."""
    t = tema()
    if not t:
        return False
    cuerpo = {'topic': t, 'title': titulo, 'message': texto, 'priority': prioridad, 'tags': list(tags)}
    if acciones:
        cuerpo['actions'] = list(acciones)[:3]
    if esperar:
        _enviar(cuerpo)
    else:
        threading.Thread(target=_enviar, args=(cuerpo,)).start()
    return True


def botones_orden(link):
    """Botones del final del recorrido: "🔁 Rearmar" (vuelve a mandar el mismo link al tema de comandos: el teléfono
    lo arma otra vez) y "✅ FIN" (si el link trae fin=…: el Apps Script pasa el comprobante a CONTADO)."""
    t = tema()
    if not t or not link:
        return []
    b = [{'action': 'http', 'label': '🔁 Rearmar', 'url': '%s/%s-cmd' % (NTFY_URL, t), 'method': 'POST',
          'body': link, 'clear': False}]
    try:
        import urllib.parse
        fin = (urllib.parse.parse_qs(urllib.parse.urlparse(link).query).get('fin') or [''])[0]
    except ValueError:
        fin = ''
    if fin.startswith('https://'):
        b.append({'action': 'http', 'label': '✅ FIN', 'url': fin, 'method': 'GET', 'clear': True})
    return b
