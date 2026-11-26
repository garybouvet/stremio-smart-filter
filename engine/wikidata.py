"""Pays d'origine et langue originale par Wikidata, pour les titres IMDb que TMDB ne situe pas.

Usage : uv run python -m engine.wikidata   (après engine.tmdb ; rapide : quelques dizaines de requêtes)
Mesuré le 26/11/2026 : Wikidata donne un pays à 85 titres sur 300 parmi ceux qui n'en avaient pas.
"""
import json, sqlite3, sys, time, urllib.error, urllib.parse, urllib.request
from . import tmdb
from .imdb_index import DB_PATH

API = 'https://query.wikidata.org/sparql'
BATCH = 200
MIN_VOTES = 100
PAUSE = 1  # service gratuit et partagé
QUERY = """SELECT ?imdb (GROUP_CONCAT(DISTINCT ?cc; separator=",") AS ?countries) (SAMPLE(?lc) AS ?lang) WHERE {
  VALUES ?imdb { %s }
  ?item wdt:P345 ?imdb .
  OPTIONAL { ?item wdt:P495 ?c . ?c wdt:P297 ?cc . }
  OPTIONAL { ?item wdt:P364 ?l . ?l wdt:P218 ?lc . }
} GROUP BY ?imdb"""


def ask(ids):
    body = urllib.parse.urlencode({'query': QUERY % ' '.join(f'"{i}"' for i in ids), 'format': 'json'}).encode()
    req = urllib.request.Request(API, data=body, headers={'User-Agent': 'stremio-custom/1.0 (usage personnel)',
                                                          'Accept': 'application/sparql-results+json'})
    with urllib.request.urlopen(req, timeout=90) as r:
        rows = json.load(r)['results']['bindings']
    out = []
    for r in rows:
        countries = sorted({c for c in r.get('countries', {}).get('value', '').split(',') if len(c) == 2})
        lang = r.get('lang', {}).get('value') or None
        if countries or lang:
            out.append((r['imdb']['value'], ',' + ','.join(countries) + ',' if countries else None, lang))
    return out


def store(meta, found):
    """Ne remplace jamais ce que TMDB sait déjà ; crée la fiche si TMDB n'en a aucune."""
    meta.executemany('INSERT OR IGNORE INTO meta (id) VALUES (?)', [(tt,) for tt, _, _ in found])
    meta.executemany('UPDATE meta SET countries = COALESCE(countries, ?), lang = COALESCE(lang, ?) WHERE id = ?',
                     [(countries, lang, tt) for tt, countries, lang in found])
    meta.commit()


def main():
    meta = tmdb.open_db()
    meta.execute('ATTACH DATABASE ? AS idx', (DB_PATH,))
    todo = [r[0] for r in meta.execute('SELECT t.id FROM idx.titles t LEFT JOIN meta m ON m.id = t.id'
                                       ' WHERE t.votes >= ? AND m.countries IS NULL ORDER BY t.votes DESC', (MIN_VOTES,))]
    print(len(todo), 'titres sans pays', flush=True)
    done = 0
    for start in range(0, len(todo), BATCH):
        try:
            found = ask(todo[start:start + BATCH])
        except (OSError, ValueError) as e:  # Wikidata surchargé : ce lot sera repris la semaine prochaine
            print(f'lot perdu : {type(e).__name__}', flush=True)
            continue
        store(meta, found)
        done += sum(1 for _, countries, _ in found if countries)
        time.sleep(PAUSE)
    print(done, 'pays trouvés', flush=True)


if __name__ == '__main__':
    main()
