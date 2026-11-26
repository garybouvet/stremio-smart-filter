"""Note dans data/extras.db les langues audio des liens de chaque titre, et si un lien est en cache Real-Debrid.

Usage : uv run python -m engine.playable
Titres connus seulement, du plus populaire au moins connu ; reprend là où il s'était arrêté, puis revérifie les titres vus il y a
plus de 30 jours (un lien quitte le cache). Série : jugée sur son premier épisode.
"""
import concurrent.futures as cf, json, sqlite3, sys, time, urllib.error, urllib.parse, urllib.request
from . import addon_langues, extras, stream_languages as sl
from .imdb_index import DB_PATH

MIN_VOTES = 1000  # au-delà, des jours de requêtes pour des titres presque toujours sans lien
OLD = 30 * 86400
WORKERS = 1
PAUSE = 2  # ces addons limitent les requêtes par adresse IP, et ce sont les mêmes qui servent à regarder
WAIT, MAX_WAIT = 600, 3600  # après un refus pour excès de requêtes : doublé à chaque refus de suite


class Refused(Exception):
    pass


def ask(manifest_url, typ, vid):
    base = manifest_url[:-len('/manifest.json')]
    req = urllib.request.Request(f'{base}/stream/{typ}/{urllib.parse.quote(vid, safe=":")}.json', headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r).get('streams') or []
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            raise Refused from e
        return None
    except (OSError, ValueError):
        return None


def offers(streams):
    """{(langue, en cache)} que proposent ces liens, selon les mêmes règles que les addons de langue."""
    out = set()
    for s in streams:
        d, cached = sl.detect(s), int(sl.is_cached_debrid(s))
        out |= {(lang, cached) for lang in addon_langues.AUDIO if addon_langues.offered(sl.audio_match(d, lang), d, lang)}
    return out


def check(title):
    """(id, offres) ; None si une source n'a pas répondu : le titre sera repris, pas noté « sans lien »."""
    tt, typ = title
    answers = [ask(u, typ, tt if typ == 'movie' else f'{tt}:1:1') for u in addon_langues.sources()]
    time.sleep(PAUSE)
    if any(a is None for a in answers):
        return None
    return tt, offers(s for a in answers for s in a)


def store(db, tt, offered, now):
    db.execute('DELETE FROM playable WHERE id = ?', (tt,))
    db.executemany('INSERT OR IGNORE INTO playable VALUES (?,?,?)', [(tt, lang, cached) for lang, cached in offered])
    db.execute('INSERT OR IGNORE INTO checked VALUES (?)', (tt,))
    db.execute('INSERT OR REPLACE INTO checked_at VALUES (?,?)', (tt, int(now)))


def remaining(db, titles, now):
    done = {r[0] for r in db.execute('SELECT id FROM checked')}
    fresh = {r[0] for r in db.execute('SELECT id FROM checked_at WHERE at > ?', (now - OLD,))}
    return [t for t in titles if t[0] not in done] + [t for t in titles if t[0] in done and t[0] not in fresh]


def main():
    if not addon_langues.sources():  # sans addon de liens (LANGUES_SOURCES), tout serait noté « sans lien »
        print('Pas de LANGUES_SOURCES : vérification des liens coupée', flush=True)
        return
    idx = sqlite3.connect(f'file:{DB_PATH}?mode=ro', uri=True)
    titles = idx.execute('SELECT id, type FROM titles WHERE votes >= ? ORDER BY votes DESC', (MIN_VOTES,)).fetchall()
    idx.close()
    db = extras.open_db()
    todo = remaining(db, titles, time.time())
    print(len(todo), 'titres à vérifier', flush=True)
    with cf.ThreadPoolExecutor(WORKERS) as ex:
        start, wait = 0, WAIT
        while start < len(todo):
            try:
                results = list(ex.map(check, todo[start:start + 50]))
            except Refused:  # on patiente puis on reprend ces 50 titres : les sauter ne ferait que saturer la source
                print(f'source saturée : pause de {wait} s', flush=True)
                time.sleep(wait)
                wait = min(wait * 2, MAX_WAIT)
                continue
            wait = WAIT
            for r in filter(None, results):
                store(db, r[0], r[1], time.time())
            db.commit()
            start += 50
            print(start, '/', len(todo), flush=True)
    db.close()


if __name__ == '__main__':
    main()
