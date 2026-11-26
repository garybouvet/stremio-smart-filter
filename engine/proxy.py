"""Relais /ss/* -> serveur de streaming Stremio (127.0.0.1:11470).

Ce serveur n'accepte en CORS que les origines *.strem.io / *.stremio.com : servie depuis 127.0.0.1:11480,
l'interface ne peut l'appeler qu'en passant par ici (même origine). Les vidéos passent aussi par ce relais.
"""
import http.client

PREFIX = '/ss/'
TARGET = ('127.0.0.1', 11470)
CHUNK = 1 << 20
DROP = {'connection', 'keep-alive', 'transfer-encoding', 'host', 'origin', 'access-control-allow-origin'}


def foreign(headers, port):
    """Requête venue d'une autre page que l'interface : ce relais retire Origin, il ne doit donc pas servir de passe-droit.
    Le lecteur mpv n'envoie ni Origin ni Sec-Fetch-Site. Host : contre un nom de domaine étranger qui pointe vers ce PC."""
    own = {f'127.0.0.1:{port}', f'localhost:{port}'}
    origin = headers.get('Origin')
    return (headers.get('Host') not in own
            or (origin is not None and origin.split('://', 1)[-1] not in own)
            or headers.get('Sec-Fetch-Site', 'none') not in ('none', 'same-origin'))


def relay(handler):
    if foreign(handler.headers, handler.server.server_port):
        handler.send_error(403)
        return
    body = None
    if handler.command in ('POST', 'PUT'):
        body = handler.rfile.read(int(handler.headers.get('Content-Length') or 0))
    headers = {k: v for k, v in handler.headers.items() if k.lower() not in DROP}
    conn = http.client.HTTPConnection(*TARGET, timeout=60)
    try:
        conn.request(handler.command, '/' + handler.path[len(PREFIX):], body=body, headers=headers)
        resp = conn.getresponse()
        handler.send_response(resp.status)
        for k, v in resp.getheaders():
            if k.lower() not in DROP:
                handler.send_header(k, v)
        if resp.getheader('Content-Length') is None:
            # Longueur inconnue (réponse découpée côté serveur) : la fin de connexion marque la fin du corps.
            handler.send_header('Connection', 'close')
            handler.close_connection = True
        handler.end_headers()
        if handler.command != 'HEAD':
            while chunk := resp.read(CHUNK):
                handler.wfile.write(chunk)
    except (ConnectionError, TimeoutError):
        pass  # lecteur fermé ou vidéo abandonnée en cours de lecture : rien à faire
    finally:
        conn.close()
