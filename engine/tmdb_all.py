"""Lit tout TMDB par son moteur de découverte (20 titres par appel) : note TMDB de chaque titre, titres sans fiche IMDb,
affiches, plateformes en France (abonnement, gratuit) et pays des films. Résultat dans data/extras.db et data/tmdb.db.

Usage : uv run python -m engine.tmdb_all   (après engine.tmdb, qui relie les numéros TMDB à IMDb)
TMDB s'arrête à 500 pages par requête : une période trop chargée est coupée en deux, jusqu'à passer.
shortcut: les titres sans date ne sortent dans aucune période, y revenir si un manque se voit.
"""
import concurrent.futures as cf, datetime, sqlite3, sys
from . import extras, tmdb
from .catalogs import GENRE_NAMES
from .imdb_index import DB_PATH, GENRE_BIT
from .settings import setting

REGION = 'FR'
MAX_PAGES = 500
KINDS = {'movie': ('movie', 'primary_release_date'), 'tv': ('series', 'first_air_date')}
FREE = 'flatrate|free|ads'
IMAGE = 'https://image.tmdb.org/t/p/w342'


def genre_masks(key, kind):
    """Numéro de genre TMDB -> masque de l'index. « Sci-Fi & Fantasy » compte pour les deux."""
    out = {}
    for g in tmdb.get(key, f'/genre/{kind}/list', language='en-US')['genres']:
        out[g['id']] = sum(GENRE_BIT.get(GENRE_NAMES.get(n.strip().lower()), 0) for n in g['name'].split('&'))
    return out


def walk(key, kind, lo, hi, params, emit, ex):
    field = KINDS[kind][1]
    query = {'language': 'fr-FR', 'include_adult': 'false', 'sort_by': 'popularity.desc',
             f'{field}.gte': lo.isoformat(), f'{field}.lte': hi.isoformat(), **params}

    complete = True

    def ask(n):
        nonlocal complete
        try:
            return tmdb.get(key, f'/discover/{kind}', page=n, **query)
        except OSError as e:  # après les réessais de get : 20 titres perdus plutôt que des heures de lecture
            complete = False
            print(f'page perdue ({kind}, {lo} à {hi}, page {n}) : {type(e).__name__}', flush=True)
            return {}

    first = ask(1)
    pages = first.get('total_pages', 0)
    if pages > MAX_PAGES and lo < hi:
        mid = lo + (hi - lo) // 2
        return all([walk(key, kind, lo, mid, params, emit, ex),
                    walk(key, kind, mid + datetime.timedelta(days=1), hi, params, emit, ex)])
    emit(first.get('results', []))
    for page in ex.map(ask, range(2, min(pages, MAX_PAGES) + 1)):
        emit(page.get('results', []))
    return complete


def row_id(ids, kind, number):
    # Films et séries ont chacun leur numérotation TMDB : le même numéro désigne deux titres.
    return ids.get((KINDS[kind][0], number)) or f'tmdb:{"tv:" if kind == "tv" else ""}{number}'


def storer(db, meta, ids, kind, masks):
    typ = KINDS[kind][0]

    def emit(results):
        extra, names, scores, posters = [], [], [], []
        for r in results:
            tt = ids.get((typ, r['id']))
            tid = row_id(ids, kind, r['id'])
            votes = r.get('vote_count') or 0
            rating = r.get('vote_average') if votes else None
            if rating:
                scores.append((tid, 'tmdb', rating))
            if r.get('poster_path'):
                posters.append((tid, IMAGE + r['poster_path']))
            if tt:
                continue
            name = r.get('title') or r.get('name')
            date = r.get('release_date') or r.get('first_air_date') or ''
            mask = sum(masks.get(g, 0) for g in r.get('genre_ids') or [])
            countries = r.get('origin_country')
            extra.append((tid, typ, name, int(date[:4]) if date[:4].isdigit() else None, None, mask, rating, votes))
            names.append((tid, r['id'], r.get('original_language'), ',' + ','.join(countries) + ',' if countries else None, name))
        db.executemany('INSERT OR REPLACE INTO extra VALUES (?,?,?,?,?,?,?,?)', extra)
        db.executemany('INSERT OR REPLACE INTO ratings VALUES (?,?,?)', scores)
        db.executemany('INSERT OR IGNORE INTO posters VALUES (?,?)', posters)
        db.commit()
        meta.executemany('INSERT OR IGNORE INTO meta VALUES (?,?,?,?,?)', names)
        meta.commit()
    return emit


def store_country(meta, ids, kind, code):
    """La découverte ne donne pas le pays d'un film : on relit chaque pays et on l'ajoute à la fiche."""
    def emit(results):
        meta.executemany("UPDATE meta SET countries = COALESCE(countries, ',') || ? WHERE id = ? AND COALESCE(countries, '') NOT LIKE ?",
                         [(code + ',', row_id(ids, kind, r['id']), f'%,{code},%') for r in results])
        meta.commit()
    return emit


def subscriptions(key, kind, lo, hi):
    """{plateforme: numéros TMDB} des offres par abonnement ou gratuites. Une boutique (Apple TV Store, Canal VOD…) sort aussi
    dans la découverte, car TMDB ne relie pas le mode à la plateforme : elle loue plus de titres qu'elle n'en offre."""
    total = lambda number, mode: tmdb.get(key, f'/discover/{kind}', watch_region=REGION, with_watch_providers=number,
                                          with_watch_monetization_types=mode).get('total_results', 0)
    out = {}
    for p in tmdb.get(key, f'/watch/providers/{kind}', watch_region=REGION)['results']:
        number = p['provider_id']
        if total(number, 'rent|buy') <= total(number, FREE):
            out.setdefault(extras.place_name(p['provider_name']), []).append(str(number))
    return out


def store_offers(db, ids, kind, place, numbers, read):
    """Remplace les titres de cette plateforme par ceux d'aujourd'hui ; une lecture incomplète n'efface rien."""
    seen = set()
    complete = read(lambda results: seen.update(row_id(ids, kind, r['id']) for r in results))
    if complete:
        db.execute('DELETE FROM offers WHERE place = ? AND kind = ?', (place, kind))
    db.executemany('INSERT OR IGNORE INTO offers VALUES (?,?,?)', [(i, place, kind) for i in seen])
    db.commit()


def main():
    key = tmdb.api_key()
    db, meta = extras.open_db(), tmdb.open_db()
    meta.execute('ATTACH DATABASE ? AS idx', (DB_PATH,))
    ids = {(t, n): tt for t, n, tt in meta.execute('SELECT t.type, m.tmdb_id, t.id FROM meta m JOIN idx.titles t ON t.id = m.id'
                                                   ' WHERE m.tmdb_id IS NOT NULL')}
    # Titres hors index reliés par tmdb_links : sans ça, chaque relecture les recréerait en tmdb:.
    meta.execute('ATTACH DATABASE ? AS h', (extras.EXTRAS_DB,))
    ids.update({(t, n): tt for t, n, tt in meta.execute("SELECT e.type, m.tmdb_id, e.id FROM meta m JOIN h.extra e ON e.id = m.id"
                                                        " WHERE e.id LIKE 'tt%' AND m.tmdb_id IS NOT NULL AND e.id NOT IN (SELECT old FROM h.merged)")})
    print(len(ids), 'titres reliés à IMDb', flush=True)
    lo, hi = datetime.date(1870, 1, 1), datetime.date.today() + datetime.timedelta(days=730)
    with cf.ThreadPoolExecutor(16) as ex:
        for kind in KINDS:
            masks = genre_masks(key, kind)
            walk(key, kind, lo, hi, {}, storer(db, meta, ids, kind, masks), ex)
            print(kind, 'lu en entier', flush=True)
            for place, numbers in subscriptions(key, kind, lo, hi).items():
                params = {'watch_region': REGION, 'with_watch_providers': '|'.join(numbers), 'with_watch_monetization_types': FREE}
                store_offers(db, ids, kind, place, numbers, lambda emit: walk(key, kind, lo, hi, params, emit, ex))
            print(kind, 'plateformes lues', flush=True)
        for country in tmdb.get(key, '/configuration/countries'):
            code = country['iso_3166_1']
            walk(key, 'movie', lo, hi, {'with_origin_country': code}, store_country(meta, ids, 'movie', code), ex)
        print('pays des films lus', flush=True)
    print(db.execute('SELECT COUNT(*) FROM extra').fetchone(), db.execute('SELECT COUNT(*) FROM ratings').fetchone(), flush=True)


if __name__ == '__main__':
    main()
