"""Aspire en entier les catalogues des addons vus dans le panneau, genre par genre, dans data/extras.db.

Usage : uv run python -m engine.harvest
Un fil par addon et une pause entre les pages : ces addons sont tenus par des bénévoles.
Les addons TMDB sont sautés : tmdb_all lit la même source, en entier et sans passer par eux.
"""
import concurrent.futures as cf, json, sqlite3, threading, time, urllib.request
from . import catalogs, extras
from .imdb_index import DB_PATH
from .settings import setting

PAUSE = float(setting('HARVEST_PAUSE', '0.2'))  # l'installeur met plus : ces addons sont tenus par des bénévoles
_lock = threading.Lock()


def jobs(manifest):
    """(type, catalogue, libellé, extra) à lire : le catalogue, puis chaque choix de son premier menu (souvent le genre)."""
    for c in manifest.get('catalogs', []):
        menus = [e for e in c.get('extra') or [] if e.get('options')]
        required = [e for e in c.get('extra') or [] if e.get('isRequired')]
        # Recherche ou liste d'identifiants obligatoire : pas un catalogue qu'on peut parcourir.
        if c.get('type') not in ('movie', 'series') or any(not e.get('options') for e in required):
            continue
        label = extras.place_name(c.get('name') or c['id'])
        if not required:
            yield c['type'], c['id'], label, []
        for e in menus[:1]:
            for option in e['options']:
                yield c['type'], c['id'], label, [(e['name'], option)]


def walk(base, job, save):
    """Lit un catalogue jusqu'au bout : page vide, ou page déjà vue (certains addons ignorent skip)."""
    typ, cid, label, extra = job
    skip, seen, total = 0, set(), 0
    while True:
        try:
            page = catalogs.fetch_page(base, typ, cid, skip, extra)
        except (OSError, ValueError):
            return total
        ids = {str(m.get('id')) for m in page}
        if not page or ids <= seen:
            return total
        seen |= ids
        metas = catalogs.identified(page, typ)
        save(metas, typ, label)
        total += len(metas)
        skip += len(page)
        time.sleep(PAUSE)


def saver(db, known):
    def save(metas, typ, label):
        outside = [m for m in metas if m['id'] not in known and m.get('name')]
        poster = lambda m: str(m.get('poster') or '')
        with _lock:
            db.executemany('INSERT OR IGNORE INTO presence VALUES (?,?)', [(m['id'], label) for m in metas])
            db.executemany('INSERT OR IGNORE INTO extra VALUES (?,?,?,?,?,?,?,?)', [catalogs.row_of(m, typ) for m in outside])
            db.executemany('INSERT OR IGNORE INTO posters VALUES (?,?)', [(m['id'], poster(m)) for m in outside if poster(m)])
            # Affiches avec les notes dessinées dessus : à préférer partout.
            db.executemany('INSERT OR REPLACE INTO posters VALUES (?,?)',
                           [(m['id'], poster(m)) for m in metas if 'ratingposterdb' in poster(m)])
            db.commit()
    return save


def harvest_addon(url, save):
    base = catalogs.addon_base(url)
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'stremio-custom'}), timeout=20) as r:
        manifest = json.load(r)
    if 'tmdb' in str(manifest.get('id')).lower() or url.endswith('/filtres/manifest.json'):
        return manifest.get('name'), 0
    return manifest.get('name'), sum(walk(base, job, save) for job in jobs(manifest))


def main():
    urls = extras.addons()
    print(len(urls), 'addons à lire', flush=True)
    idx = sqlite3.connect(f'file:{DB_PATH}?mode=ro', uri=True)
    known = {r[0] for r in idx.execute('SELECT id FROM titles')}
    idx.close()
    db = extras.open_db()
    save = saver(db, known)

    def run(url):
        try:
            name, n = harvest_addon(url, save)
            print(f'{name} : {n} titres lus', flush=True)
        except (OSError, ValueError) as e:
            print(f'addon indisponible : {type(e).__name__}', flush=True)  # jamais l'adresse : elle contient des clés

    with cf.ThreadPoolExecutor(max(1, len(urls))) as ex:
        list(ex.map(run, urls))
    print(dict(db.execute('SELECT "lieux", COUNT(DISTINCT place) FROM presence')), db.execute('SELECT COUNT(DISTINCT id) FROM presence').fetchone(), flush=True)


if __name__ == '__main__':
    main()
