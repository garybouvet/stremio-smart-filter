"""uv run python -m unittest engine.test_origin : choix multiples, pays devinés, Wikidata, bibliothèque."""
import sqlite3, unittest
from unittest import mock
from . import names, wikidata
from .search import count, parse, search
from .test_engine import db, ids


def base():
    d = db()  # tt1 US en, tt2 JP ja, tt4 FR/BE fr ; tt3 sans fiche
    d.executemany("INSERT INTO titles VALUES (?, 'movie', ?, 2020, 100, 0, 7, 5000)", [('tt6', 'Inconnu hindi'), ('tt7', 'Inconnu')])
    d.executemany('INSERT INTO tmdb.meta VALUES (?,?,?,?,?)', [('tt6', None, 'hi', None, None), ('tt7', None, None, None, None)])
    d.executemany('INSERT INTO h.offers VALUES (?,?,?)', [('tt1', 'Netflix', 'movie'), ('tt2', 'Prime Video', 'movie'), ('tt4', 'Netflix', 'movie')])
    return d


def got(q):
    return set(ids(search(base(), parse({'limit': ['200'], **q}))))


class Choices(unittest.TestCase):
    def test_several_countries_in_or_out(self):
        self.assertEqual(got({'country': ['US,JP']}), {'tt1', 'tt2'})
        self.assertEqual(got({'country': ['FR'], 'country_not': ['BE']}), set())
        self.assertEqual(got({'country_not': ['US', 'JP']}), {'tt3', 'tt4', 'tt6', 'tt7'})

    def test_language_gives_the_country_when_unknown(self):
        self.assertEqual(got({'country': ['IN']}), {'tt6'})
        self.assertEqual(got({'country_not': ['IN']}), {'tt1', 'tt2', 'tt3', 'tt4', 'tt7'})
        self.assertEqual(got({'country_not': ['IN'], 'unknown_country': ['hide']}), {'tt1', 'tt2', 'tt4'})

    def test_languages_and_places(self):
        self.assertEqual(got({'language': ['ja,fr']}), {'tt2', 'tt4'})
        self.assertEqual(got({'language_not': ['en']}), {'tt2', 'tt3', 'tt4', 'tt6', 'tt7'})
        self.assertEqual(got({'place': ['Netflix', 'Prime Video']}), {'tt1', 'tt2', 'tt4'})
        self.assertEqual(got({'place': ['Netflix'], 'place_not': ['Prime Video']}), {'tt1', 'tt4'})

    def test_library(self):
        self.assertEqual(got({'exclude_ids': ['tt1,tt2']}), {'tt3', 'tt4', 'tt6', 'tt7'})
        self.assertEqual(got({'only_ids': ['tt2,tt4,tt99']}), {'tt2', 'tt4'})
        self.assertEqual(got({'only_ids': ['none']}), set())  # « Ma liste » vide : rien
        self.assertEqual(got({'exclude_ids': ["tt1,kitsu:12,yt_id:UC1,tt2') OR 1=1 --"]}), {'tt2', 'tt3', 'tt4', 'tt6', 'tt7'})
        d = db()
        d.execute("INSERT INTO h.extra VALUES ('tmdb:tv:8', 'series', 'Série TMDB', 2020, NULL, 0, 8, 50)")
        self.assertEqual(ids(search(d, parse({'type': ['series'], 'only_ids': ['tmdb:8']}))), ['tmdb:8'])

    def test_rejects_bad_values(self):
        for q in ({'country': ['fr']}, {'language': ['FRA']}, {'country': [','.join(['FR'] * 61)]}):
            self.assertRaises(ValueError, parse, q)
        self.assertEqual(count(base(), parse({'country': ['FR,FR']})), 1)


class Names(unittest.TestCase):
    def test_french_or_original_title_without_accents(self):
        import os, tempfile
        self.assertEqual(names.norm('  Plan cœur : L’ÉTÉ ! '), 'plan coeur l ete')
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'names.db')
            d = sqlite3.connect(path)
            d.execute('CREATE TABLE names (norm TEXT, id TEXT, type TEXT, votes INT, PRIMARY KEY (norm, id)) WITHOUT ROWID')
            d.executemany('INSERT INTO names VALUES (?,?,?,?)', [('les evades', 'tt1', 'movie', 3000000), ('the shawshank redemption', 'tt1', 'movie', 3000000),
                                                                ('les evades de la planete', 'tt9', 'movie', 50), ('plan coeur', 'tt8', 'series', 6000),
                                                                ('les evades', 'tt7', 'series', 10)])
            d.commit()
            d.close()
            self.assertEqual(names.find('Les Évadés', 'movie', path), ['tt1', 'tt9'])
            self.assertEqual(names.find('shawshank', 'movie', path), ['tt1'])
            self.assertEqual(names.find('PLAN cœur', 'series', path), ['tt8'])
            self.assertEqual(names.find('a', 'movie', path), [])
            self.assertEqual(names.find("evades' OR 1=1 --", 'movie', path), [])


class Wikidata(unittest.TestCase):
    def test_fills_only_what_is_missing(self):
        m = sqlite3.connect(':memory:')
        m.execute('CREATE TABLE meta (id TEXT PRIMARY KEY, tmdb_id INT, lang TEXT, countries TEXT, name_fr TEXT)')
        m.executemany('INSERT INTO meta VALUES (?,?,?,?,?)', [('tt1', None, 'en', None, None), ('tt2', 5, 'ja', ',JP,', None)])
        wikidata.store(m, [('tt1', ',US,', 'fr'), ('tt2', ',KR,', 'ko'), ('tt3', ',IN,', 'mr')])
        self.assertEqual(m.execute('SELECT id, lang, countries FROM meta ORDER BY id').fetchall(),
                         [('tt1', 'en', ',US,'), ('tt2', 'ja', ',JP,'), ('tt3', 'mr', ',IN,')])

    def test_reads_the_answer(self):
        answer = {'results': {'bindings': [{'imdb': {'value': 'tt1'}, 'countries': {'value': 'US,GB'}, 'lang': {'value': 'en'}},
                                           {'imdb': {'value': 'tt2'}, 'countries': {'value': ''}}]}}

        class Response:
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def read(self, *a): return __import__('json').dumps(answer).encode()
        with mock.patch.object(wikidata.urllib.request, 'urlopen', lambda *a, **k: Response()):
            self.assertEqual(wikidata.ask(['tt1', 'tt2']), [('tt1', ',GB,US,', 'en')])



class TitleLanguage(unittest.TestCase):
    def test_french_title_only_for_french_interface(self):
        from .search import to_meta
        row = ('tt1', 'movie', 'The Shawshank Redemption', 1994, 142, 0, 9.3, 3000000, 'Les Évadés', None)
        self.assertEqual(to_meta(row)['name'], 'Les Évadés')
        self.assertEqual(to_meta(row, 'en')['name'], 'The Shawshank Redemption')
        self.assertEqual(to_meta(row[:8] + (None, None), 'fr')['name'], 'The Shawshank Redemption')
        self.assertEqual(parse({'lang': ['en']})['lang'], 'en')
        self.assertEqual(parse({'lang': ['<x>']})['lang'], 'fr')

if __name__ == '__main__':
    unittest.main()
