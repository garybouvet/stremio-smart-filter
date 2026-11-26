"""Notes des autres sources (Rotten Tomatoes, Metacritic, Letterboxd, Trakt) par MDBList, dans data/extras.db.

Usage : uv run python -m engine.mdblist   (clé MDBLIST_API_KEY dans .env)
Lots de 200 titres, du plus populaire au moins connu. Compte gratuit : 1 000 lots par jour ; arrivé au quota, le
programme attend le jour suivant. Reprend là où il s'était arrêté.
"""
import json, sqlite3, sys, time, urllib.error, urllib.request
from . import extras
from .imdb_index import DB_PATH
from .settings import setting

API = 'https://api.mdblist.com'
BATCH = 200  # plafond mesuré : au-delà, MDBList ignore le reste sans le dire
SOURCES = ('tomatoes', 'popcorn', 'metacritic', 'metacriticuser', 'trakt', 'letterboxd')
KINDS = {'movie': 'movie', 'series': 'show'}


def ask(key, kind, ids):
    req = urllib.request.Request(f'{API}/imdb/{kind}/?apikey={key}', data=json.dumps({'ids': ids}).encode(),
                                 headers={'Content-Type': 'application/json', 'User-Agent': 'stremio-custom'})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def rows_of(items):
    """score : 0 à 100 quelle que soit l'échelle de la source ; ramené sur 10 comme les notes IMDb et TMDB."""
    return [(i['ids']['imdb'], r['source'], min(r['score'], 100) / 10) for i in items if (i.get('ids') or {}).get('imdb')
            for r in i.get('ratings') or [] if r.get('source') in SOURCES and r.get('score')]


def wait_time(error):
    """Secondes à attendre après un refus : Retry-After sur 5 minutes, x-ratelimit-reset pour le quota du jour."""
    reset = error.headers.get('x-ratelimit-reset')
    return max(int(error.headers.get('Retry-After') or 0), int(reset) - int(time.time()) if reset else 0, 60)


def main():
    key = setting('MDBLIST_API_KEY')
    if not key:  # facultative : sans clé, les notes du paquet de données restent celles du jour où il a été fait
        print('Pas de clé MDBList : notes non mises à jour', flush=True)
        return
    db = extras.open_db()
    db.execute('CREATE TABLE IF NOT EXISTS rated (id TEXT PRIMARY KEY) WITHOUT ROWID')
    done = {r[0] for r in db.execute('SELECT id FROM rated')}
    idx = sqlite3.connect(f'file:{DB_PATH}?mode=ro', uri=True)
    todo = [t for t in idx.execute('SELECT id, type FROM titles ORDER BY votes DESC') if t[0] not in done]
    idx.close()
    print(len(todo), 'titres à noter', flush=True)
    for typ, kind in KINDS.items():
        ids = [t[0] for t in todo if t[1] == typ]
        start = 0
        while start < len(ids):
            batch = ids[start:start + BATCH]
            try:
                items = ask(key, kind, batch)
            except urllib.error.HTTPError as e:
                if e.code != 429:
                    raise
                print('quota atteint : pause', wait_time(e), 's', flush=True)
                time.sleep(wait_time(e))
                continue
            except OSError:
                time.sleep(60)
                continue
            db.executemany('INSERT OR REPLACE INTO ratings VALUES (?,?,?)', rows_of(items))
            db.executemany('INSERT OR IGNORE INTO rated VALUES (?)', [(i,) for i in batch])
            db.commit()
            start += BATCH
            print(typ, start, '/', len(ids), flush=True)


if __name__ == '__main__':
    main()
