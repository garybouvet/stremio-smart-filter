"""Complète l'index avec TMDB : langue originale, pays, titre français. Stocké à part (data/tmdb.db)
pour survivre à la reconstruction quotidienne de l'index IMDb. Reprend là où il s'était arrêté.

Usage : uv run python -m engine.tmdb [--min-votes 1000]   (clé TMDB_API_KEY dans .env)
"""
import concurrent.futures as cf, json, os, sqlite3, sys, time, urllib.parse, urllib.request
from .imdb_index import DATA, DB_PATH
from .settings import setting

TMDB_DB = os.path.join(DATA, 'tmdb.db')
API = 'https://api.themoviedb.org/3'
COMPLETE_MAX = 300  # par requête : le reste sera complété aux suivantes, le résultat reste rapide
_imdb = {}  # (type, id TMDB) -> identifiant IMDb


def api_key():
    return setting('TMDB_API_KEY') or sys.exit('Clé absente : ajouter TMDB_API_KEY=... dans .env (voir .env.example)')


def get(key, path, **params):
    # Clé v3 (32 caractères) en paramètre, jeton v4 (long) en en-tête.
    headers = {'Accept': 'application/json'}
    if len(key) > 40:
        headers['Authorization'] = f'Bearer {key}'
    else:
        params['api_key'] = key
    req = urllib.request.Request(f'{API}{path}?{urllib.parse.urlencode(params)}', headers=headers)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if (e.code == 429 or e.code >= 500) and attempt < 4:  # quota dépassé ou panne passagère : on patiente
                time.sleep(2 ** attempt)
                continue
            if e.code == 404:
                return {}
            raise
        except OSError:  # coupure réseau : sur des heures de lecture, ça arrive forcément
            if attempt == 4:
                raise
            time.sleep(2 ** attempt)


def fetch(key, tt, series=False):
    found = get(key, f'/find/{tt}', external_source='imdb_id', language='fr-FR')
    # Un numéro IMDb de série peut sortir aussi un faux film : c'est le type de l'index qui tranche.
    kinds = ('tv_results', 'movie_results') if series else ('movie_results', 'tv_results')
    hit = (found.get(kinds[0]) or found.get(kinds[1]) or [None])[0]
    if not hit:
        return (tt, None, None, None, None)
    countries = hit.get('origin_country')
    if countries is None:  # films : le pays n'est donné que par la fiche détaillée
        countries = get(key, f'/movie/{hit["id"]}').get('origin_country') or []
    return (tt, hit['id'], hit.get('original_language'), ',' + ','.join(countries) + ',' if countries else None,
            hit.get('title') or hit.get('name'))


def try_fetch(key, tt, series=False):
    """fetch, ou None si TMDB ne répond toujours pas : le titre sera repris au prochain passage."""
    try:
        return fetch(key, tt, series)
    except OSError:
        return None


def open_db():
    db = sqlite3.connect(TMDB_DB)
    db.execute('CREATE TABLE IF NOT EXISTS meta (id TEXT PRIMARY KEY, tmdb_id INT, lang TEXT,'
               ' countries TEXT, name_fr TEXT)')
    db.execute('CREATE INDEX IF NOT EXISTS ix_lang ON meta (lang)')
    db.execute('CREATE INDEX IF NOT EXISTS ix_countries ON meta (countries)')
    return db


def imdb_of(typ, tmdb_id):
    """Identifiant IMDb d'un titre connu par son numéro TMDB ; None si TMDB ne le sait pas ou ne répond pas."""
    k = (typ, tmdb_id)
    if k not in _imdb:
        key = setting('TMDB_API_KEY')
        if not key:
            return None
        try:
            _imdb[k] = get(key, f'/{"tv" if typ == "series" else "movie"}/{tmdb_id}/external_ids').get('imdb_id')
        except OSError:
            return None
    return _imdb[k]


def complete(db, ids):
    """Langue et pays des titres d'un catalogue que enrich() n'a pas vus (il s'arrête à un nombre de votes)."""
    key = setting('TMDB_API_KEY')
    known = {r[0] for r in db.execute('SELECT id FROM tmdb.meta')}
    todo = [i for i in ids if i not in known][:COMPLETE_MAX]
    if not key or not todo:
        return

    with cf.ThreadPoolExecutor(16) as ex:
        rows = [r for r in ex.map(lambda tt: try_fetch(key, tt), todo) if r]
    out = open_db()
    try:
        out.executemany('INSERT OR REPLACE INTO meta VALUES (?,?,?,?,?)', rows)
        out.commit()
    except sqlite3.OperationalError as e:  # base occupée (mise à jour hebdomadaire) : ces titres seront repris plus tard
        sys.stderr.write(f'tmdb.db : {e}\n')
    finally:
        out.close()


def enrich(min_votes=1000, workers=16):
    key = api_key()
    out = open_db()
    out.execute('ATTACH DATABASE ? AS idx', (DB_PATH,))
    todo = out.execute('SELECT id, type FROM idx.titles WHERE votes >= ? AND id NOT IN'
                       ' (SELECT id FROM meta) ORDER BY votes DESC', (min_votes,)).fetchall()
    print(f'{len(todo)} titres à compléter')
    with cf.ThreadPoolExecutor(workers) as ex:
        for i, row in enumerate(ex.map(lambda t: try_fetch(key, t[0], t[1] == 'series'), todo), 1):
            if row:
                out.execute('INSERT OR REPLACE INTO meta VALUES (?,?,?,?,?)', row)
            if i % 500 == 0:
                out.commit()
                print(f'{i}/{len(todo)}')
    out.commit()


if __name__ == '__main__':
    enrich(int(sys.argv[sys.argv.index('--min-votes') + 1]) if '--min-votes' in sys.argv else 1000)
