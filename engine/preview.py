"""Aperçu d'un titre choisi dans Découvrir : résumé français, casting, bande-annonce (TMDB à la demande, rien n'est stocké),
plus les notes des autres sites, les plateformes et les noms connus du titre (l'interface repère ainsi un lien d'un autre film)."""
import re, threading
from . import tmdb, trailer
from .settings import setting

ID = re.compile(r'^(tt\d+|tmdb:\d+)$')
CAST = 4
MAX_CACHED = 500
_cache, _lock = {}, threading.Lock()


def row_id(tid, typ):
    """Identifiant en base : les séries de TMDB y portent tmdb:tv:N (voir search.to_meta)."""
    return tid.replace('tmdb:', 'tmdb:tv:') if typ == 'series' and tid.startswith('tmdb:') else tid


def tmdb_id(db, tid, typ, key):
    if tid.startswith('tmdb:'):
        return int(tid.split(':')[1])
    row = db.execute('SELECT tmdb_id FROM tmdb.meta WHERE id = ?', (tid,)).fetchone()
    if row:
        return row[0]
    found = tmdb.get(key, f'/find/{tid}', external_source='imdb_id') or {}
    hits = found.get('tv_results' if typ == 'series' else 'movie_results') or [{}]
    return hits[0].get('id')


def online(number, typ, key):
    kind = 'tv' if typ == 'series' else 'movie'
    ask = lambda lang: tmdb.get(key, f'/{kind}/{number}', language=lang, append_to_response='credits,videos',
                                include_video_language='fr,en,null') or {}
    body = ask('fr-FR')
    credits = body.get('credits') or {}
    video, lang = trailer.choose((body.get('videos') or {}).get('results', []), body.get('original_language'))
    directors = [p['name'] for p in credits.get('crew', []) if p.get('job') == 'Director'] if kind == 'movie' else \
                [p['name'] for p in body.get('created_by') or []]
    date = body.get('release_date') or body.get('first_air_date') or ''
    return {'names': [body[k] for k in ('title', 'original_title', 'name', 'original_name') if body.get(k)],
            'year': int(date[:4]) if date[:4].isdigit() else None,
            'description': body.get('overview') or ask('en-US').get('overview') or None,
            'cast': [p['name'] for p in credits.get('cast', [])[:CAST]], 'directors': directors[:2],
            'trailer': video, 'trailerLang': lang, 'runtime': body.get('runtime') or None}


def preview(db, tid, typ):
    """Lève ValueError si l'identifiant n'est pas reconnu. TMDB en panne ou sans clé : notes et plateformes quand même."""
    if typ not in ('movie', 'series') or not ID.fullmatch(tid):
        raise ValueError('titre invalide')
    row = row_id(tid, typ)
    out = {'ratings': dict(db.execute('SELECT source, value FROM h.ratings WHERE id = ?', (row,))),
           'places': [p for (p,) in db.execute('SELECT DISTINCT place FROM h.offers WHERE id = ? ORDER BY place', (row,))]}
    # Le même titre sous un autre numéro IMDb (voir merge.py) : ses liens peuvent être meilleurs.
    twin = db.execute("SELECT new FROM h.merged WHERE old = ? AND new LIKE 'tt%' UNION SELECT old FROM h.merged WHERE new = ? AND old LIKE 'tt%'",
                      (row, row)).fetchone()
    out['twin'] = twin[0] if twin else None
    names = [n for (n,) in db.execute('SELECT name FROM main.titles WHERE id = ? UNION SELECT name_fr FROM tmdb.meta WHERE id = ?', (row, row)) if n]
    with _lock:
        hit = _cache.get((tid, typ))
    if hit is None:
        key = setting('TMDB_API_KEY')
        try:
            number = tmdb_id(db, tid, typ, key) if key else None
            hit = online(number, typ, key) if number else {}
        except OSError:
            hit = None
        if hit is not None:
            with _lock:
                if len(_cache) >= MAX_CACHED:
                    _cache.clear()
                _cache[(tid, typ)] = hit
    hit = hit or {}
    return {**hit, **out, 'names': sorted({*names, *hit.get('names', [])})}
