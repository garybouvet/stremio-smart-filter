"""« Pour toi » : les recommandations TMDB des titres vus ou gardés dans la bibliothèque, réunies et classées.

Chaque titre de départ donne ses 20 recommandations TMDB (gardées 30 jours dans data/tmdb.db). Un titre recommandé par
plusieurs titres récents passe devant. Le résultat passe ensuite par les mêmes filtres que le reste.
"""
import concurrent.futures as cf, re, sqlite3, time
from . import tmdb
from .settings import setting

MAX_SEEDS = 60
KEPT = 30 * 86400
WORKERS = 8
SEED = re.compile(r'^(tt\d+|tmdb:\d+)$')


def open_cache():
    db = tmdb.open_db()
    db.execute('CREATE TABLE IF NOT EXISTS reco (kind TEXT, seed INT, rank INT, rec INT, at INT, PRIMARY KEY (kind, seed, rank)) WITHOUT ROWID')
    return db


def seeds_of(db, ids, typ):
    """[(rang, numéro TMDB)] des titres de départ de ce type, du plus récent au plus ancien."""
    out = []
    for rank, tid in enumerate(i for i in ids if SEED.fullmatch(i)):
        if tid.startswith('tmdb:'):
            row_id = tid.replace('tmdb:', 'tmdb:tv:') if typ == 'series' else tid
            found = db.execute('SELECT 1 FROM h.extra WHERE id = ? AND type = ?', (row_id, typ)).fetchone()
            number = int(tid.split(':')[1]) if found else None
        else:
            row = db.execute('SELECT m.tmdb_id FROM tmdb.meta m JOIN (SELECT id, type FROM main.titles UNION ALL'
                             ' SELECT id, type FROM h.extra) t ON t.id = m.id WHERE m.id = ? AND t.type = ?', (tid, typ)).fetchone()
            number = row[0] if row else None
        if number:
            out.append((rank, number))
    return out[:MAX_SEEDS]


def recommendations(kind, numbers, now=None):
    """{seed: [rec, ...]} depuis le cache, TMDB pour ce qui manque ou a plus de 30 jours."""
    now = now or time.time()
    cache = open_cache()
    try:
        known = {}
        for seed, rank, rec in cache.execute(f'SELECT seed, rank, rec FROM reco WHERE kind = ? AND at > ? AND seed IN ({",".join("?" * len(numbers))})'
                                             ' ORDER BY seed, rank', [kind, now - KEPT, *numbers]):
            known.setdefault(seed, []).append(rec)
        missing = [n for n in numbers if n not in known]
        key = setting('TMDB_API_KEY')
        if missing and key:
            def ask(n):
                try:
                    return n, [r['id'] for r in (tmdb.get(key, f'/{kind}/{n}/recommendations', language='fr-FR') or {}).get('results', [])]
                except OSError:
                    return n, None  # TMDB injoignable : ce titre de départ compte la prochaine fois
            with cf.ThreadPoolExecutor(WORKERS) as ex:
                fetched = [(n, recs) for n, recs in ex.map(ask, missing) if recs is not None]
            try:
                cache.executemany('DELETE FROM reco WHERE kind = ? AND seed = ?', [(kind, n) for n, _ in fetched])
                cache.executemany('INSERT INTO reco VALUES (?,?,?,?,?)', [(kind, n, r, rec, int(now)) for n, recs in fetched for r, rec in enumerate(recs)])
                cache.commit()
            except sqlite3.OperationalError:
                pass  # base occupée par une tâche de fond : le cache sera rempli une autre fois
            known.update(fetched)
        return known
    finally:
        cache.close()


def scores(seeds, recs):
    """{numéro TMDB: score} : plus le titre de départ est récent et la recommandation haute, plus elle compte."""
    out = {}
    for rank, number in seeds:
        weight = 1 / (1 + rank / 10)
        for position, rec in enumerate(recs.get(number, [])):
            out[rec] = out.get(rec, 0) + weight * (1 - position / 25)
    for _, number in seeds:
        out.pop(number, None)  # pas les titres de départ eux-mêmes
    return out


def candidates(db, typ, ids):
    """Crée temp.cand(id, score) pour search.where et search.SORTS['foryou']. Renvoie le nombre de candidats."""
    seeds = seeds_of(db, ids, typ)
    kind = 'tv' if typ == 'series' else 'movie'
    by_number = scores(seeds, recommendations(kind, [n for _, n in seeds])) if seeds else {}
    db.execute('CREATE TEMP TABLE IF NOT EXISTS cand (id TEXT PRIMARY KEY, score REAL)')
    db.execute('DELETE FROM cand')
    if by_number:
        prefix = 'tmdb:tv:' if typ == 'series' else 'tmdb:'
        numbers = list(by_number)
        rows = db.execute(f'SELECT m.tmdb_id, m.id FROM tmdb.meta m WHERE m.tmdb_id IN ({",".join("?" * len(numbers))})', numbers).fetchall()
        linked = [(tid, by_number[n]) for n, tid in rows] + [(f'{prefix}{n}', s) for n, s in by_number.items()]
        db.executemany('INSERT OR REPLACE INTO cand VALUES (?,?)', linked)
    return len(by_number)
