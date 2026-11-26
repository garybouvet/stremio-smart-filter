"""Filtres cumulables sur l'index IMDb (+ TMDB attaché sous le nom `tmdb`) : SQL commun aux deux modes."""
import os, re, sqlite3
from . import extras, origin, tmdb
from .imdb_index import DB_PATH, GENRE_BIT, GENRES, genre_mask, genre_names

# Note pondérée (formule du Top 250 IMDb : 25 000 votes fictifs à 6,9) : un 10/10 sur 12 votes ne passe pas devant.
WEIGHTED = '(votes * rating + 25000 * 6.9) / (votes + 25000)'
SORTS = {'rating': f'{WEIGHTED} DESC', 'votes': 'votes DESC', 'year': 'year DESC, votes DESC',
         'year_asc': 'year IS NULL, year ASC, votes DESC'}  # sans année : à la fin, pas en tête des « plus anciens »
# Autres notes, pondérées de même par les votes IMDb : sinon un film noté par trois personnes sur Letterboxd passe devant.
# Un titre sans cette note finit en bas (NULL).
SCORE_SOURCES = ('tomatoes', 'popcorn', 'metacritic', 'metacriticuser', 'letterboxd', 'trakt', 'tmdb')
_weighted = lambda score: f'(votes * {score} + 25000 * 6.9) / (votes + 25000) DESC'
SORTS |= {s: _weighted(f"(SELECT value FROM h.ratings r WHERE r.id = titles.id AND r.source = '{s}')") for s in SCORE_SOURCES}
# Moyenne d'IMDb et des sites critiques (sans TMDB, trop proche d'IMDb), dès trois notes.
SORTS['average'] = _weighted('(SELECT (SUM(value) + COALESCE(titles.rating, 0)) / (COUNT(*) + (titles.rating IS NOT NULL))'
                             " FROM h.ratings r WHERE r.id = titles.id AND r.source != 'tmdb'"
                             ' HAVING COUNT(*) + (titles.rating IS NOT NULL) >= 3)')
# « Pour toi » : ordre des recommandations (table temporaire remplie par foryou.candidates).
SORTS['foryou'] = '(SELECT score FROM temp.cand c WHERE c.id = titles.id) DESC, votes DESC'
MMAP = 1 << 30
RANGES = {'rating_min': 'rating >=', 'rating_max': 'rating <=', 'votes_min': 'votes >=',
          'year_min': 'year >=', 'year_max': 'year <=', 'runtime_min': 'runtime >=',
          'runtime_max': 'runtime <='}


def connect():
    """Index IMDb en lecture seule, avec les données TMDB attachées sous le nom `tmdb`."""
    db = sqlite3.connect(f'file:{DB_PATH}?mode=ro', uri=True)
    if not os.path.exists(tmdb.TMDB_DB):
        tmdb.open_db().close()  # base TMDB vide tant que l'enrichissement n'a pas tourné
    db.execute(f"ATTACH DATABASE 'file:{tmdb.TMDB_DB}?mode=ro' AS tmdb")
    if not os.path.exists(extras.EXTRAS_DB):
        extras.open_db().close()
    db.execute(f"ATTACH DATABASE 'file:{extras.EXTRAS_DB}?mode=ro' AS h")
    # Lecture par la mémoire du système plutôt que page par page : une recherche sur toute la base passe de 0,75 à 0,35 s.
    for schema in ('main', 'tmdb', 'h'):
        db.execute(f'PRAGMA {schema}.mmap_size = {MMAP}')
    return db


def parse(q):
    """Paramètres d'URL (dict de listes, comme parse_qs) -> filtres typés. Lève ValueError si invalide."""
    one = lambda k: q.get(k, [None])[0]
    f = {'type': one('type') or 'movie', 'sort': one('sort') or 'rating'}
    if f['type'] not in ('movie', 'series') or f['sort'] not in SORTS:
        raise ValueError('type ou tri inconnu')
    for k in RANGES:
        if one(k) not in (None, ''):
            f[k] = float(one(k))
    for k in ('genres_all', 'genres_any', 'genres_none'):
        names = [g for v in q.get(k, []) for g in v.split(',') if g]
        if any(g not in GENRE_BIT for g in names):
            raise ValueError('genre inconnu')
        f[k] = genre_mask(names)
    f |= origin.parse(q, f['type'])
    f['seeds'] = [i for i in origin.values(q, 'seeds', None, origin.MAX_IDS) if origin.TITLE_ID.fullmatch(i)]
    f['foryou'] = 'seeds' in q
    if f['sort'] == 'foryou' and not f['foryou']:
        raise ValueError('tri « pour toi » sans titres de départ')
    f['known'] = one('known') == '1'
    if one('link'):
        if not re.fullmatch(r'[a-z]{2}(_cached)?', one('link')):
            raise ValueError('lien invalide')
        f['link'] = one('link')
    f['scores'] = {m[1]: float(one(k)) for k in q if (m := re.fullmatch(r'score_([a-z]+)_min', k)) and one(k)}
    f['skip'] = max(0, int(one('skip') or 0))
    f['limit'] = min(200, max(1, int(one('limit') or 50)))
    return f


def where(f):
    sql, args = ['type = ?'], [f['type']]
    for k, op in RANGES.items():
        if k in f:
            sql.append(f'{op} ?')
            args.append(f[k])
    if f.get('genres_all'):
        sql.append('genres & ? = ?')
        args += [f['genres_all']] * 2
    if f.get('genres_any'):
        sql.append('genres & ? != 0')
        args.append(f['genres_any'])
    if f.get('genres_none'):
        sql.append('genres & ? = 0')
        args.append(f['genres_none'])
    # Langue et pays : TMDB, puis Wikidata. Un pays inconnu passe une exclusion, sauf si on demande de le masquer.
    more, more_args = origin.clauses(f)
    sql += more
    args += more_args
    if f.get('foryou'):
        sql.append('titles.id IN (SELECT id FROM temp.cand)')
    if f.get('harvested'):
        sql.append('titles.id IN (SELECT id FROM h.presence)')
    if f.get('known'):
        # Connu : assez de votes, proposé par une plateforme, ou mis en avant par un addon qui ne donne pas les votes.
        sql.append('(votes >= floor OR titles.id IN (SELECT id FROM h.offers)'
                   ' OR (votes IS NULL AND titles.id IN (SELECT id FROM h.presence)))')
    for source, value in f.get('scores', {}).items():
        sql.append('titles.id IN (SELECT id FROM h.ratings WHERE source = ? AND value >= ?)')
        args += [source, value]
    if f.get('link'):
        lang, _, cached = f['link'].partition('_')
        sql.append('titles.id IN (SELECT id FROM h.playable WHERE lang = ?' + (' AND cached = 1)' if cached else ')'))
        args.append(lang)
    return ' AND '.join(sql), args


JOINS = 'LEFT JOIN tmdb.meta m ON m.id = titles.id LEFT JOIN h.posters p ON p.id = titles.id'
COLUMNS = 'id, type, name, year, runtime, genres, rating, votes'
SHOWN = ', '.join(f'titles.{c}' for c in COLUMNS.split(', ')) + ', m.name_fr, p.poster'
# floor : nombre de votes à partir duquel un titre compte comme connu. TMDB a bien moins de votants qu'IMDb.
ALL_TITLES = (f'(SELECT {COLUMNS}, 100 AS floor FROM main.titles UNION ALL'
              f' SELECT {COLUMNS}, 10 FROM h.extra WHERE id NOT IN (SELECT old FROM h.merged)) AS titles')


def to_meta(r):
    tt, typ, name, year, runtime, genres, rating, votes, name_fr, poster = r
    return {'id': tt.replace('tmdb:tv:', 'tmdb:'), 'type': typ, 'name': name_fr or name,  # Stremio distingue par le type
            'poster': poster or f'https://images.metahub.space/poster/small/{tt}/img',
            'releaseInfo': str(year or ''), 'year': year, 'runtime': f'{runtime} min' if runtime else None,
            'genres': genre_names(genres), 'imdbRating': None if rating is None else f'{rating:.1f}', 'votes': votes}


def search(db, f):
    return page(db, f, counted=False)[0]


def page(db, f, counted=True):
    """(titres de la page, nombre total ou None). Le total vient de la même lecture : un seul passage sur la base."""
    w, args = where(f)
    order = SORTS[f['sort']]
    total = ', COUNT(*) OVER () AS total' if counted else ', NULL AS total'
    # Noms et affiches joints après le tri : sur la page affichée, pas sur plus d'un million de titres.
    inner = f'SELECT *{total} FROM {ALL_TITLES} WHERE {w} ORDER BY {order} LIMIT ? OFFSET ?'
    rows = db.execute(f'SELECT {SHOWN}, titles.total FROM ({inner}) AS titles {JOINS} ORDER BY {order}',
                      args + [f['limit'], f['skip']]).fetchall()
    found = rows[0][-1] if rows else (0 if f['skip'] == 0 else None)
    return [to_meta(r[:-1]) for r in rows], found if counted else None


def by_ids(db, ids):
    """Titres dans l'ordre donné (résultats de recherche par nom)."""
    if not ids:
        return []
    rows = db.execute(f'SELECT {SHOWN} FROM {ALL_TITLES} {JOINS} WHERE titles.id IN ({",".join("?" * len(ids))})', ids).fetchall()
    found = {r[0]: to_meta(r) for r in rows}
    return [found[i] for i in ids if i in found]


def count(db, f):
    w, args = where(f)
    return db.execute(f'SELECT COUNT(*) FROM {ALL_TITLES} WHERE {w}', args).fetchone()[0]


def lookup(db, rows, f, ranked=False):
    """Parmi les titres d'un addon, ceux qui passent les filtres : {id: meta}. L'index IMDb prime ; un titre qu'il n'a pas
    est jugé sur les données de l'addon. rows : mêmes colonnes que titles. ranked : triés et paginés selon f."""
    db.execute('CREATE TEMP TABLE IF NOT EXISTS pool (id TEXT PRIMARY KEY, type TEXT, name TEXT, year INT,'
               ' runtime INT, genres INT, rating REAL, votes INT)')
    db.execute('DELETE FROM pool')
    db.executemany('INSERT OR IGNORE INTO pool VALUES (?,?,?,?,?,?,?,?)', rows)
    db.commit()  # sinon la transaction ouverte garde tmdb.db verrouillée pour tmdb.complete
    w, args = where(f)
    sql = (f'SELECT {SHOWN} FROM (SELECT {COLUMNS}, 0 AS floor FROM main.titles WHERE id IN (SELECT id FROM pool) UNION ALL'
           f' SELECT {COLUMNS}, 0 FROM pool WHERE id NOT IN (SELECT id FROM main.titles)) AS titles {JOINS} WHERE {w}')
    if ranked:
        sql += f' ORDER BY {SORTS[f["sort"]]} LIMIT ? OFFSET ?'
        args = args + [f['limit'], f['skip']]
    return {r[0]: to_meta(r) for r in db.execute(sql, args)}


def options(db):
    """Valeurs proposées dans l'interface : genres, et langues / pays présents dans les données TMDB."""
    langs = db.execute('SELECT lang FROM tmdb.meta WHERE lang IS NOT NULL GROUP BY lang HAVING COUNT(*) >= 20'
                       ' ORDER BY COUNT(*) DESC').fetchall()
    counts = {}
    for c, n in db.execute('SELECT countries, COUNT(*) FROM tmdb.meta WHERE countries IS NOT NULL GROUP BY countries'):
        for code in c.strip(',').split(','):
            counts[code] = counts.get(code, 0) + n
    places = db.execute('SELECT place FROM h.offers GROUP BY place HAVING COUNT(*) >= 20 ORDER BY COUNT(*) DESC').fetchall()
    return {'genres': GENRES, 'languages': [l for (l,) in langs],
            'countries': sorted((c for c, n in counts.items() if n >= 20), key=lambda c: -counts[c]),
            'places': [p for (p,) in places], 'scores': [s for (s,) in db.execute('SELECT DISTINCT source FROM h.ratings')],
            'links': [l for (l,) in db.execute('SELECT lang FROM h.playable GROUP BY lang ORDER BY COUNT(*) DESC')]}
