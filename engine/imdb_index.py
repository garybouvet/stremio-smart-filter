"""Construit data/index.db à partir des fichiers IMDb officiels (datasets.imdbws.com).

Usage : uv run python -m engine.imdb_index [--download] [--weekly]   (--weekly : rien à faire si l'index a moins de 7 jours)
"""
import csv, gzip, os, sqlite3, sys, time, urllib.request

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
DB_PATH = os.path.join(DATA, 'index.db')
FILES = ('title.ratings.tsv.gz', 'title.basics.tsv.gz')

# Ordre figé : la position donne le bit du masque stocké en base. N'ajouter qu'à la fin.
GENRES = ['Action', 'Adult', 'Adventure', 'Animation', 'Biography', 'Comedy', 'Crime',
          'Documentary', 'Drama', 'Family', 'Fantasy', 'Film-Noir', 'Game-Show', 'History',
          'Horror', 'Music', 'Musical', 'Mystery', 'News', 'Reality-TV', 'Romance', 'Sci-Fi',
          'Short', 'Sport', 'Talk-Show', 'Thriller', 'War', 'Western']
GENRE_BIT = {g: 1 << i for i, g in enumerate(GENRES)}
TYPES = {'movie': 'movie', 'tvMovie': 'movie', 'tvSeries': 'series', 'tvMiniSeries': 'series'}


def genre_mask(names):
    return sum(GENRE_BIT.get(n, 0) for n in names)


def genre_names(mask):
    return [g for g, b in GENRE_BIT.items() if mask & b]


def download():
    os.makedirs(DATA, exist_ok=True)
    for f in FILES:
        print('téléchargement', f)
        urllib.request.urlretrieve(f'https://datasets.imdbws.com/{f}', os.path.join(DATA, f + '.part'))
        os.replace(os.path.join(DATA, f + '.part'), os.path.join(DATA, f))


def rows(name):
    with gzip.open(os.path.join(DATA, name), 'rt', encoding='utf-8', newline='') as f:
        yield from csv.DictReader(f, delimiter='\t', quoting=csv.QUOTE_NONE)


def num(v):
    return None if v == '\\N' else int(v)


def build():
    ratings = {r['tconst']: (float(r['averageRating']), int(r['numVotes'])) for r in rows(FILES[0])}
    tmp = DB_PATH + '.tmp'
    if os.path.exists(tmp):
        os.remove(tmp)
    db = sqlite3.connect(tmp)
    db.execute('CREATE TABLE titles (id TEXT PRIMARY KEY, type TEXT, name TEXT, year INT,'
               ' runtime INT, genres INT, rating REAL, votes INT)')

    # Titre original, quand il diffère : sert à reconnaître un titre que TMDB connaît sous ce nom (merge.py).
    db.execute('CREATE TABLE originals (id TEXT PRIMARY KEY, name TEXT) WITHOUT ROWID')
    originals = []

    def keep():
        for r in rows(FILES[1]):
            t = TYPES.get(r['titleType'])
            # Titres adultes et titres jamais notés ignorés : inutiles pour filtrer par note.
            if t and r['isAdult'] == '0' and r['tconst'] in ratings:
                if r['originalTitle'] != r['primaryTitle']:
                    originals.append((r['tconst'], r['originalTitle']))
                g = [] if r['genres'] == '\\N' else r['genres'].split(',')
                yield (r['tconst'], t, r['primaryTitle'], num(r['startYear']),
                       num(r['runtimeMinutes']), genre_mask(g), *ratings[r['tconst']])

    db.executemany('INSERT INTO titles VALUES (?,?,?,?,?,?,?,?)', keep())
    db.executemany('INSERT INTO originals VALUES (?,?)', originals)
    for col in ('rating', 'votes', 'year'):
        db.execute(f'CREATE INDEX ix_{col} ON titles (type, {col})')
    db.commit()
    n = db.execute('SELECT type, COUNT(*) FROM titles GROUP BY type').fetchall()
    install(db)
    db.close()
    os.remove(tmp)
    print('index construit :', dict(n))
    prune_extras()


def install(new, path=DB_PATH):
    """Recopie la nouvelle base dans l'ancienne. Remplacer le fichier échoue sous Windows dès qu'une tâche le tient ouvert ;
    la copie SQLite attend son tour, et les lecteurs voient l'ancien contenu puis le nouveau."""
    live = sqlite3.connect(path, timeout=60)
    try:
        new.backup(live)
    finally:
        live.close()


def prune_extras(extras_db=os.path.join(DATA, 'extras.db'), index_db=DB_PATH):
    """Un titre que l'index vient de recevoir sortirait deux fois dans les recherches ; un titre sans nom ne s'affiche pas."""
    if not os.path.exists(extras_db):
        return
    db = sqlite3.connect(extras_db, timeout=60)  # playable et mdblist écrivent dans cette base en même temps
    db.execute('ATTACH DATABASE ? AS idx', (index_db,))
    n = db.execute('DELETE FROM extra WHERE name IS NULL OR id IN (SELECT id FROM idx.titles)').rowcount
    db.commit()
    db.close()
    print(n, 'titres retirés de extras.db')


def fresh(path=DB_PATH, days=7):
    return os.path.exists(path) and time.time() - os.path.getmtime(path) < days * 86400


if __name__ == '__main__':
    if '--weekly' in sys.argv and fresh():
        print('index à jour')
    else:
        if '--download' in sys.argv:
            download()
        build()
