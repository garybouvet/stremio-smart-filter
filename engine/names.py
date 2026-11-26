"""Recherche par titre, en français ou en version originale, sans se soucier des accents ni de la casse.

Usage : uv run python -m engine.names   (après engine.merge ; ~1 min) -> data/names.db, reconstruite en entier.
Noms : titre IMDb, titre original, titre français de TMDB, titres hors index.
"""
import os, re, sqlite3, unicodedata
from . import extras, tmdb
from .imdb_index import DATA, DB_PATH, install

NAMES_DB = os.path.join(DATA, 'names.db')
LIMIT = 20


def norm(name):
    """« Plan cœur » -> « plan coeur » : minuscules, sans accents, ponctuation en espaces."""
    flat = unicodedata.normalize('NFKD', (name or '').casefold().replace('œ', 'oe').replace('æ', 'ae'))
    flat = ''.join(c for c in flat if not unicodedata.combining(c))
    return ' '.join(re.split(r'[^\w]+', flat)).strip()


def build(path=NAMES_DB):
    tmp = path + '.tmp'
    if os.path.exists(tmp):
        os.remove(tmp)
    db = sqlite3.connect(tmp)
    db.execute('CREATE TABLE names (norm TEXT, id TEXT, type TEXT, votes INT, PRIMARY KEY (norm, id)) WITHOUT ROWID')
    db.execute('ATTACH DATABASE ? AS idx', (DB_PATH,))
    db.execute('ATTACH DATABASE ? AS t', (tmdb.TMDB_DB,))
    db.execute('ATTACH DATABASE ? AS h', (extras.EXTRAS_DB,))
    db.create_function('norm', 1, norm, deterministic=True)
    titles = ('SELECT id, type, votes FROM idx.titles UNION ALL'
              ' SELECT id, type, votes FROM h.extra WHERE id NOT IN (SELECT old FROM h.merged)')
    for source in ('SELECT t.id, t.type, t.votes, i.name AS n FROM idx.titles i JOIN ({titles}) t ON t.id = i.id',
                   'SELECT t.id, t.type, t.votes, o.name AS n FROM idx.originals o JOIN ({titles}) t ON t.id = o.id',
                   'SELECT t.id, t.type, t.votes, m.name_fr AS n FROM t.meta m JOIN ({titles}) t ON t.id = m.id',
                   'SELECT t.id, t.type, t.votes, e.name AS n FROM h.extra e JOIN ({titles}) t ON t.id = e.id'):
        db.execute(f'INSERT OR IGNORE INTO names SELECT norm(n), id, type, votes FROM ({source.format(titles=titles)})'
                   ' WHERE n IS NOT NULL AND norm(n) != ""')
    db.commit()
    count = db.execute('SELECT COUNT(*) FROM names').fetchone()[0]
    if os.path.exists(path):
        install(db, path)  # recopiée dans l'ancienne : Windows refuse de remplacer un fichier qu'une recherche lit
        db.close()
        os.remove(tmp)
    else:
        db.close()
        os.replace(tmp, path)
    return count


def find(text, typ, path=NAMES_DB):
    """Identifiants des titres dont le nom contient tous les mots tapés : nom exact, puis début de nom, puis les plus votés."""
    words = norm(text).split()
    if not words or not os.path.exists(path) or len(''.join(words)) < 2:
        return []
    db = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    try:
        whole = ' '.join(words)
        rows = db.execute('SELECT id, MIN(CASE WHEN norm = ? THEN 0 WHEN norm LIKE ? THEN 1 ELSE 2 END) AS fit, MAX(votes) AS v FROM names'
                          f' WHERE type = ? AND {" AND ".join("norm LIKE ?" for _ in words)} GROUP BY id'
                          ' ORDER BY fit, v IS NULL, v DESC LIMIT ?',
                          [whole, f'{whole}%', typ, *[f'%{w}%' for w in words], LIMIT]).fetchall()
    finally:
        db.close()
    return [r[0] for r in rows]


if __name__ == '__main__':
    print(build(), 'noms', flush=True)
