"""Relie à IMDb les séries que seul TMDB connaît : les sources de liens ne comprennent pas tmdb: pour une série.
Une série reliée prend son vrai identifiant dans data/extras.db et data/tmdb.db ; une série sans fiche IMDb va dans unlinked.

Usage : uv run python -m engine.tmdb_links   (après engine.tmdb_all ; reprend là où il s'était arrêté)
"""
import concurrent.futures as cf
from . import extras, tmdb
from .imdb_index import DB_PATH

WORKERS = 16


def imdb_id(key, tid):
    """(tid, tt) ; tt vaut '' sans fiche IMDb, None si TMDB ne répond pas : la série sera reprise au prochain passage."""
    try:
        return tid, tmdb.get(key, f'/tv/{tid.rsplit(":", 1)[1]}/external_ids').get('imdb_id') or ''
    except OSError:
        return tid, None


def rename(db, meta, old, tt, indexed):
    for table in ('presence', 'offers', 'ratings', 'posters', 'extra'):
        db.execute(f'UPDATE OR IGNORE {table} SET id = ? WHERE id = ?', (tt, old))
        db.execute(f'DELETE FROM {table} WHERE id = ?', (old,))
    if tt in indexed:  # l'index a déjà la fiche : la garder en double la ferait sortir deux fois
        db.execute('DELETE FROM extra WHERE id = ?', (tt,))
    meta.execute('UPDATE OR REPLACE meta SET id = ? WHERE id = ?', (tt, old))


def link(key, db, meta, indexed):
    todo = [r[0] for r in db.execute("SELECT id FROM extra WHERE id >= 'tmdb:tv:' AND id < 'tmdb:tv;'"
                                     ' AND id NOT IN (SELECT id FROM unlinked) AND id NOT IN (SELECT old FROM merged) ORDER BY votes DESC')]
    print(len(todo), 'séries à relier', flush=True)
    with cf.ThreadPoolExecutor(WORKERS) as ex:
        for i, (old, tt) in enumerate(ex.map(lambda t: imdb_id(key, t), todo), 1):
            if tt:
                rename(db, meta, old, tt, indexed)
            elif tt == '':
                db.execute('INSERT OR IGNORE INTO unlinked VALUES (?)', (old,))
            if i % 500 == 0:
                db.commit()
                meta.commit()
                print(f'{i}/{len(todo)}', flush=True)
    db.commit()
    meta.commit()


def main():
    db, meta = extras.open_db(), tmdb.open_db()
    meta.execute('ATTACH DATABASE ? AS idx', (DB_PATH,))
    link(tmdb.api_key(), db, meta, {r[0] for r in meta.execute('SELECT id FROM idx.titles')})
    print(db.execute("SELECT COUNT(*) FROM extra WHERE id LIKE 'tt%'").fetchone(), 'titres IMDb hors index,',
          db.execute('SELECT COUNT(*) FROM unlinked').fetchone(), 'séries sans fiche', flush=True)


if __name__ == '__main__':
    main()
