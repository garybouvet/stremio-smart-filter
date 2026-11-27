"""Moteur : addons Stremio, plus (en local seulement) l'API de filtres, l'interface stremio-web modifiée
et le relais du serveur de streaming.

Usage : uv run python -m engine.server
Sur un serveur : PUBLIC=1 (addons, plus l'interface et l'API sous /app/<WEB_TOKEN>/ ; limite par IP),
HOST=0.0.0.0 derrière le proxy HTTPS.
"""
import hmac, json, os, re, sys, urllib.parse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from . import addon_routes, catalogs, extras, foryou, names, preview, proxy, ratelimit, search
from .imdb_index import DB_PATH
from .settings import setting

PORT = 11480
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_BUILD = os.path.join(ROOT, 'stremio-web', 'build')
PUBLIC = setting('PUBLIC') == '1'
# En local, l'interface vient du disque : le cache de Stremio ne ferait que servir une ancienne version après une
# recompilation. Le navigateur relit ce fichier à chaque ouverture ; celui-ci efface le cache et recharge la page.
NO_CACHE_WORKER = b"""self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil((async () => {
    await Promise.all((await caches.keys()).map((key) => caches.delete(key)));
    await self.registration.unregister();
    (await self.clients.matchAll({ type: 'window' })).forEach((client) => client.navigate(client.url));
})()));
"""
APP = re.compile(r'^/app/([^/]+)(/.*)?$')


class Handler(SimpleHTTPRequestHandler):
    def client_ip(self):
        # Derrière Caddy, l'IP du visiteur est dans X-Forwarded-For (Caddy remplace ce qu'envoie le client).
        fwd = self.headers.get('X-Forwarded-For') if PUBLIC else None
        return fwd.split(',')[0].strip() if fwd else self.client_address[0]

    def refused_in_public(self):
        """En mode public : addons, /health et l'interface sous /app/<WEB_TOKEN>/, avec une limite par IP.
        True si la requête est refusée (réponse déjà envoyée)."""
        if not PUBLIC:
            return False
        u = urllib.parse.urlsplit(self.path)
        path = u.path
        m = APP.match(path)
        if m:
            token = setting('WEB_TOKEN')
            if not token or not hmac.compare_digest(m.group(1), token):
                sys.stderr.write(f"sécurité : adresse d'interface refusée pour {self.client_ip()}\n")
                self.reply(404, {'error': 'introuvable'})
                return True
            if not m.group(2):  # chemins relatifs de l'interface : il faut le « / » final
                self.send_response(301)
                self.send_header('Location', path + '/')
                self.end_headers()
                return True
            # Pas de serveur de streaming sur le serveur : le relais /ss/ reste réservé au PC.
            if m.group(2).startswith(proxy.PREFIX):
                self.reply(404, {'error': 'introuvable'})
                return True
            # La suite est traitée comme en local (interface, API) ; le jeton n'apparaît plus dans les journaux.
            self.path = m.group(2) + (f'?{u.query}' if u.query else '')
            path = m.group(2)
            if not path.startswith('/api/'):
                return False  # fichiers de l'interface : le premier chargement en demande des dizaines
        elif not (path.startswith('/addon/') or path == '/health'):
            self.reply(404, {'error': 'introuvable'})
            return True
        if not ratelimit.allow(self.client_ip()):
            sys.stderr.write(f'sécurité : limite dépassée pour {self.client_ip()}\n')
            self.reply(429, {'error': 'trop de requêtes'}, addon_routes.CORS)
            return True
        return False

    def do_POST(self):
        if self.refused_in_public():
            return
        if self.path.startswith(proxy.PREFIX):
            return proxy.relay(self)
        self.send_error(405)

    def do_HEAD(self):
        if self.refused_in_public():
            return
        if self.path.startswith(proxy.PREFIX):
            return proxy.relay(self)
        super().do_HEAD()

    def do_OPTIONS(self):
        # Pré-vol CORS des addons : Stremio (web.stremio.com) appelle le moteur local.
        if self.path.startswith('/addon/'):
            return self.reply(204, None, addon_routes.CORS)
        self.send_error(405)

    def do_GET(self):
        if self.refused_in_public():
            return
        u = urllib.parse.urlsplit(self.path)
        if u.path == '/health':
            return self.reply(200, {'ok': True})
        if u.path == '/service-worker.js' and not PUBLIC:
            return self.send(200, NO_CACHE_WORKER, 'text/javascript; charset=utf-8')
        if u.path.startswith(proxy.PREFIX):
            return proxy.relay(self)
        if u.path.startswith('/addon/'):
            try:
                code, body = addon_routes.handle(u.path)
                if code == 404 and u.path.count('/') >= 4:
                    sys.stderr.write(f"sécurité : adresse d'addon refusée pour {self.client_ip()}\n")
                return self.reply(code, body, addon_routes.CORS)
            except ValueError:
                return self.reply(400, {'error': 'paramètres invalides'}, addon_routes.CORS)
            except Exception as e:
                sys.stderr.write(f'erreur {type(e).__name__} sur {addon_routes.redact(u.path)} : {e}\n')
                return self.reply(502, {'error': 'source indisponible'}, addon_routes.CORS)
        if not u.path.startswith('/api/'):
            return super().do_GET()
        # En-tête maison : une page web tierce ne peut pas l'envoyer sans pré-vol CORS, qu'on ne sert pas.
        # En local, un autre nom d'hôte (rebinding DNS : piege.com -> 127.0.0.1) est refusé comme pour le relais.
        if self.headers.get('X-Stremio-Custom') != '1' or (not PUBLIC and proxy.foreign(self.headers, self.server.server_port)):
            return self.reply(403, {'error': 'interdit'})
        q = urllib.parse.parse_qs(u.query)
        try:
            db = search.connect()
            try:
                if u.path == '/api/options':
                    return self.reply(200, search.options(db))
                if u.path == '/api/find':
                    typ = q.get('type', ['movie'])[0]
                    if typ not in ('movie', 'series'):
                        raise ValueError('type inconnu')
                    return self.reply(200, {'metas': search.by_ids(db, names.find(q.get('q', [''])[0][:100], typ))})
                if u.path == '/api/preview':
                    return self.reply(200, preview.preview(db, q.get('id', [''])[0], q.get('type', [''])[0], q.get('lang', ['fr'])[0]))
                f = search.parse(q)
                if u.path == '/api/search':
                    return self.reply(200, self.page(db, f))
                if u.path == '/api/foryou':
                    foryou.candidates(db, f['type'], f['seeds'])
                    return self.reply(200, self.page(db, {**f, 'foryou': True}))
                if u.path == '/api/catalog':
                    base = catalogs.addon_base(q.get('addon', [''])[0])
                    extra = [(k, v) for k, v in urllib.parse.parse_qsl(q.get('extra', [''])[0]) if k != 'skip']
                    metas, nxt = catalogs.filtered(db, base, q.get('catalog', [''])[0], f,
                                                   start=f['skip'], want=f['limit'], extra=extra)
                    return self.reply(200, {'metas': metas, 'next': nxt})
                if u.path == '/api/sources':
                    sources = q.get('sources', ['{}'])[0]
                    if not PUBLIC:
                        extras.remember(url for url in json.loads(sources))
                    if db.execute('SELECT 1 FROM h.presence LIMIT 1').fetchone():  # déjà aspiré : plus de limite ni d'attente
                        return self.reply(200, self.page(db, {**f, 'harvested': True}))
                    metas, nxt = catalogs.everywhere(db, catalogs.sources_of(sources), f)
                    return self.reply(200, {'metas': metas, 'next': nxt})
                return self.reply(404, {'error': 'introuvable'})
            finally:
                db.close()
        except ValueError:
            return self.reply(400, {'error': 'paramètres invalides'})
        except Exception as e:
            sys.stderr.write(f'erreur {type(e).__name__} sur {u.path} : {e}\n')
            return self.reply(502, {'error': 'source indisponible'})

    def page(self, db, f):
        metas, total = search.page(db, f, counted=not f['skip'])  # compté une fois, sur la première page
        body = {'metas': metas, 'next': f['skip'] + len(metas) if len(metas) == f['limit'] else None}
        return body if f['skip'] else {**body, 'total': total}

    def end_headers(self):
        # Revalider à chaque fois : sinon le navigateur garde l'ancien index.html après une recompilation.
        if not self.path.startswith(proxy.PREFIX):
            self.send_header('Cache-Control', 'no-cache')
        super().end_headers()

    def reply(self, code, body, headers=None):
        data = b'' if body is None else json.dumps(body, ensure_ascii=False).encode()
        self.send(code, data, 'application/json; charset=utf-8', headers)

    def send(self, code, data, kind, headers=None):
        self.send_response(code)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        # Jamais la chaîne de requête (adresses d'addons avec leurs clés) ni le jeton des addons.
        path = APP.sub(r'/app/***\2', urllib.parse.urlsplit(self.path).path)
        sys.stderr.write('%s %s\n' % (self.command, addon_routes.redact(path)))


def main():
    if not os.path.exists(DB_PATH):
        sys.exit('Index absent : lancer d\'abord  uv run python -m engine.imdb_index --download')
    extras.open_db().close()  # crée les tables ajoutées depuis : la recherche ouvre cette base en lecture seule
    host = setting('HOST', '127.0.0.1')
    srv = ThreadingHTTPServer((host, PORT), partial(Handler, directory=WEB_BUILD))
    print(f'http://{host}:{PORT}/' + (' (mode public : addons et /app/<jeton>/)' if PUBLIC else ''), flush=True)
    srv.serve_forever()


if __name__ == '__main__':
    main()
