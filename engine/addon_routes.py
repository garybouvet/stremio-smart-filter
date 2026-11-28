"""Routes des addons Stremio, sous /addon/<jeton>/<addon>/… (protocole des addons Stremio).

Le jeton (ADDON_TOKEN dans .env) rend l'adresse impossible à deviner : l'addon Langues interroge tes sources
avec tes clés Real-Debrid, il ne doit répondre qu'à toi.
"""
import hmac, re, urllib.parse
from . import addon_filtres, addon_langues, search
from .addon_texts import LANGS
from .settings import setting

ROUTE = re.compile(r'^/addon/([^/]+)/(filtres(?:-[a-z]{2})?|langues|(?:audio|subs)-[a-z]{2})/(.*)$')
STREAM = re.compile(r'^stream/(movie|series)/([^/]+)\.json$')
CORS = {'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*',
        'Access-Control-Allow-Private-Network': 'true'}


def redact(path):
    return ROUTE.sub(lambda m: f'/addon/***/{m.group(2)}/{m.group(3)}', path)


def handle(path):
    """Renvoie (code, corps JSON)."""
    m = ROUTE.match(path)
    token = setting('ADDON_TOKEN')
    if not m or not token or not hmac.compare_digest(m.group(1), token):
        return 404, {'error': 'introuvable'}
    addon, rest = m.group(2), m.group(3)
    if addon in addon_langues.VARIANTS:
        if rest == 'manifest.json':
            return 200, addon_langues.language_manifest(addon)
        s = STREAM.match(rest)
        if not s:
            return 404, {'error': 'introuvable'}
        return 200, {'streams': addon_langues.language_streams(addon, s.group(1), urllib.parse.unquote(s.group(2))),
                     'cacheMaxAge': 0}
    if addon == 'langues':
        if rest == 'manifest.json':
            return 200, addon_langues.manifest()
        s = STREAM.match(rest)
        if not s:
            return 404, {'error': 'introuvable'}
        return 200, {'streams': addon_langues.streams(s.group(1), urllib.parse.unquote(s.group(2))),
                     'cacheMaxAge': 0}
    # filtres : français (l'addon d'origine) ; filtres-en, filtres-es… : la même chose dans une autre langue.
    lang = addon[len('filtres-'):] if addon.startswith('filtres-') else 'fr'
    if not addon.startswith('filtres') or lang not in LANGS:
        return 404, {'error': 'introuvable'}
    db = search.connect()
    try:
        if rest == 'manifest.json':
            return 200, addon_filtres.manifest(search.options(db), lang)
        c = re.match(r'^catalog/(movie|series)/filtres(?:/([^/]+))?\.json$', rest)
        if not c:
            return 404, {'error': 'introuvable'}
        extra = dict(urllib.parse.parse_qsl(c.group(2) or ''))
        return 200, {'metas': addon_filtres.catalog(db, c.group(1), extra, lang), 'cacheMaxAge': 3600}
    finally:
        db.close()
