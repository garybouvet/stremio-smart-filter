"""Rapproche les titres que TMDB et IMDb connaissent sous deux numéros (Plan cœur : tt9170638 et tt8019344).

Usage : uv run python -m engine.merge   (après engine.tmdb_all et engine.tmdb_links)
Rien n'est supprimé : la table merged cache le titre hors index, et sa fiche TMDB (langue, pays, titre français,
affiche, notes, plateformes) est recopiée sur le titre de l'index.
"""
import sqlite3, sys, unicodedata
from . import extras, tmdb
from .imdb_index import DB_PATH


def norm(name):
    """« Plan cœur » et « Plan Coeur » : lettres et chiffres seulement, sans accents ni casse."""
    flat = unicodedata.normalize('NFKD', (name or '').casefold().replace('œ', 'oe').replace('æ', 'ae'))
    return ''.join(c for c in flat if c.isalnum())


def keys(typ, year, *names):
    return {(typ, year, n) for n in map(norm, names) if n and year}


def pairs(db):
    """[(ancien, gardé)] : un seul titre de chaque côté pour ce type, cette année et ce nom, que TMDB n'a pas déjà relié,
    et au moins un genre commun. Le moindre doute laisse les deux titres."""
    linked = {r[0] for r in db.execute('SELECT id FROM meta WHERE tmdb_id IS NOT NULL')}
    index, genres = {}, {}
    for tt, typ, year, name, mask, original in db.execute(
            'SELECT t.id, t.type, t.year, t.name, t.genres, o.name FROM idx.titles t LEFT JOIN idx.originals o ON o.id = t.id'):
        for k in keys(typ, year, name, original):
            index.setdefault(k, set()).add(tt)
            genres[tt] = mask
    outside = {}
    for old, typ, year, name, mask in db.execute(
            'SELECT id, type, year, name, genres FROM h.extra WHERE id NOT IN (SELECT old FROM h.merged)'):
        for k in keys(typ, year, name):
            outside.setdefault(k, []).append((old, mask))
    out = []
    for k, found in outside.items():
        twins = index.get(k, ())
        if len(found) != 1 or len(twins) != 1:
            continue
        (old, mask), tt = found[0], next(iter(twins))
        if tt not in linked and (not mask or not genres[tt] or mask & genres[tt]):
            out.append((old, tt))
    return out


def apply(db, found):
    for old, tt in found:
        db.execute('INSERT OR REPLACE INTO meta SELECT ?, tmdb_id, lang, countries, name_fr FROM meta WHERE id = ?', (tt, old))
        for table, columns in (('presence', 'place'), ('offers', 'place, kind'), ('ratings', 'source, value'), ('posters', 'poster')):
            db.execute(f'INSERT OR IGNORE INTO h.{table} SELECT ?, {columns} FROM h.{table} WHERE id = ?', (tt, old))
        db.execute('INSERT OR REPLACE INTO h.merged VALUES (?, ?)', (old, tt))
    db.commit()


def main():
    extras.open_db().close()
    db = tmdb.open_db()
    db.execute('PRAGMA busy_timeout = 60000')
    db.execute('ATTACH DATABASE ? AS idx', (DB_PATH,))
    db.execute('ATTACH DATABASE ? AS h', (extras.EXTRAS_DB,))
    try:
        db.execute('SELECT 1 FROM idx.originals LIMIT 1')
    except sqlite3.OperationalError:
        sys.exit("Titres originaux absents de l'index : lancer d'abord  uv run python -m engine.imdb_index --download")
    found = pairs(db)
    apply(db, found)
    print(len(found), 'doublons rapprochés', flush=True)


if __name__ == '__main__':
    main()
