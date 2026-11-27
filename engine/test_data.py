"""uv run python -m unittest engine.test_data : pays, plateformes, doublons, titres confidentiels, revérification, aperçu."""
import sqlite3, time, unittest
from unittest import mock
from . import extras, foryou, mdblist, merge, playable, preview, tmdb, tmdb_all, trailer
from .imdb_index import genre_mask
from .search import count, page, parse, search
from .test_engine import db, ids

DRAMA = genre_mask(['Drama'])


def stores():
    """meta (tmdb.db) avec l'index et extras.db attachés, comme dans les tâches de fond."""
    m = sqlite3.connect(':memory:')
    m.execute('CREATE TABLE meta (id TEXT PRIMARY KEY, tmdb_id INT, lang TEXT, countries TEXT, name_fr TEXT)')
    m.execute("ATTACH ':memory:' AS idx")
    m.execute('CREATE TABLE idx.titles (id TEXT PRIMARY KEY, type TEXT, name TEXT, year INT, runtime INT, genres INT, rating REAL, votes INT)')
    m.execute('CREATE TABLE idx.originals (id TEXT PRIMARY KEY, name TEXT)')
    m.execute("ATTACH ':memory:' AS h")
    extras.create(m, 'h')
    return m


class Countries(unittest.TestCase):
    def test_each_country_is_added_once(self):
        m = stores()
        m.executemany('INSERT INTO meta VALUES (?,?,?,?,?)', [('tt1', 1, 'en', ',US,', None), ('tmdb:2', 2, 'hi', None, None)])
        for code in ('US', 'IN', 'IN'):
            tmdb_all.store_country(m, {('movie', 1): 'tt1'}, 'movie', code)([{'id': 1}, {'id': 2}, {'id': 99}])
        self.assertEqual(m.execute('SELECT id, countries FROM meta ORDER BY id').fetchall(), [('tmdb:2', ',US,IN,'), ('tt1', ',US,IN,')])


class Offers(unittest.TestCase):
    def test_stores_are_left_out_and_resellers_joined(self):
        def get(key, path, **p):
            if path.startswith('/watch/providers'):
                return {'results': [{'provider_id': i, 'provider_name': n} for i, n in
                                    ((1, 'Netflix'), (2, 'Apple TV Store'), (3, 'HBO Max'), (4, 'HBO Max Amazon Channel'))]}
            rents = {1: 1300, 2: 19000, 3: 10, 4: 10}[p['with_watch_providers']]
            return {'total_results': rents if p['with_watch_monetization_types'] == 'rent|buy' else 7000}
        with mock.patch.object(tmdb, 'get', get):
            self.assertEqual(tmdb_all.subscriptions('k', 'movie', None, None), {'Netflix': ['1'], 'HBO Max': ['3', '4']})

    def test_a_title_that_left_is_removed_only_after_a_full_read(self):
        d = sqlite3.connect(':memory:')
        extras.create(d)
        now = lambda: sorted(r[0] for r in d.execute('SELECT id FROM offers'))

        def read(numbers, complete):
            return lambda emit: (emit([{'id': n} for n in numbers]), complete)[1]
        tmdb_all.store_offers(d, {}, 'movie', 'Netflix', ['8'], read([1, 2], True))
        tmdb_all.store_offers(d, {}, 'tv', 'Netflix', ['8'], read([1], True))
        tmdb_all.store_offers(d, {}, 'movie', 'Netflix', ['8'], read([3], False))
        self.assertEqual(now(), ['tmdb:1', 'tmdb:2', 'tmdb:3', 'tmdb:tv:1'])
        tmdb_all.store_offers(d, {}, 'movie', 'Netflix', ['8'], read([3], True))
        self.assertEqual(now(), ['tmdb:3', 'tmdb:tv:1'])


class Posters(unittest.TestCase):
    def test_indexed_titles_get_a_poster_without_losing_rpdb(self):
        d, m = sqlite3.connect(':memory:'), stores()
        extras.create(d)
        d.execute("INSERT INTO posters VALUES ('tt2', 'ratingposterdb.jpg')")
        tmdb_all.storer(d, m, {('movie', 1): 'tt1', ('movie', 2): 'tt2'}, 'movie', {})(
            [{'id': 1, 'poster_path': '/a.jpg'}, {'id': 2, 'poster_path': '/b.jpg'}])
        self.assertEqual(dict(d.execute('SELECT * FROM posters')), {'tt1': tmdb_all.IMAGE + '/a.jpg', 'tt2': 'ratingposterdb.jpg'})


class Merge(unittest.TestCase):
    def base(self):
        m = stores()
        m.executemany('INSERT INTO idx.titles VALUES (?,?,?,?,NULL,?,7,100)', [
            ('tt8', 'series', 'The Hookup Plan', 2018, DRAMA), ('tt1', 'movie', 'Return', 2015, DRAMA),
            ('tt2', 'movie', 'Return', 2015, DRAMA), ('tt3', 'movie', 'Linked', 2000, DRAMA), ('tt4', 'movie', 'Other', 2001, DRAMA)])
        m.execute("INSERT INTO idx.originals VALUES ('tt8', 'Plan Coeur')")
        m.executemany('INSERT INTO meta VALUES (?,?,?,?,?)', [('tt9', 83412, 'fr', ',FR,', 'Plan cœur'), ('tt8', None, None, None, None),
                                                              ('tt3', 33, 'en', ',US,', None)])
        m.executemany('INSERT INTO h.extra VALUES (?,?,?,?,NULL,?,6,10)', [
            ('tt9', 'series', 'Plan cœur', 2018, DRAMA), ('tmdb:1', 'movie', 'Return', 2015, DRAMA), ('tmdb:3', 'movie', 'Linked', 2000, DRAMA),
            ('tmdb:4', 'movie', 'Other', 2001, genre_mask(['Comedy']))])
        m.execute("INSERT INTO h.offers VALUES ('tt9', 'Netflix', 'tv')")
        return m

    def test_only_sure_twins_are_joined_and_nothing_is_deleted(self):
        m = self.base()  # Return : deux homonymes ; Linked : TMDB l'a déjà relié ; Other : aucun genre commun
        found = merge.pairs(m)
        self.assertEqual(found, [('tt9', 'tt8')])
        merge.apply(m, found)
        self.assertEqual(m.execute("SELECT lang, countries, name_fr FROM meta WHERE id = 'tt8'").fetchone(), ('fr', ',FR,', 'Plan cœur'))
        self.assertEqual(m.execute("SELECT place FROM h.offers WHERE id = 'tt8'").fetchall(), [('Netflix',)])
        self.assertEqual(m.execute('SELECT COUNT(*) FROM h.extra').fetchone(), (4,))
        self.assertEqual(merge.pairs(m), [])

    def test_a_joined_title_comes_out_once(self):
        d = db()
        d.execute("INSERT INTO h.extra VALUES ('tmdb:tv:5', 'series', 'Série', 2008, NULL, 0, 9, 300)")
        self.assertEqual(len(search(d, parse({'type': ['series']}))), 2)
        d.execute("INSERT INTO h.merged VALUES ('tmdb:tv:5', 'tt5')")
        self.assertEqual(ids(search(d, parse({'type': ['series']}))), ['tt5'])


class Known(unittest.TestCase):
    def test_obscure_titles_are_hidden_on_demand(self):
        d = db()  # tt4 : 40 votes
        d.executemany("INSERT INTO h.extra VALUES (?, 'movie', ?, 2020, NULL, 0, 7, ?)",
                      [('tmdb:1', 'Vu par douze', 12), ('tmdb:2', 'Vu par deux', 2), ('tmdb:3', 'Sur Netflix', 0), ('tt77', 'Addon', None)])
        d.execute("INSERT INTO h.offers VALUES ('tmdb:3', 'Netflix', 'movie')")
        d.execute("INSERT INTO h.presence VALUES ('tt77', 'Popular')")
        f = parse({'known': ['1']})
        self.assertEqual(set(ids(search(d, f))), {'tt1', 'tt2', 'tt3', 'tmdb:1', 'tmdb:3', 'tt77'})
        self.assertEqual((count(d, f), count(d, parse({}))), (6, 8))
        self.assertEqual(page(d, {**f, 'limit': 2})[1], 6)  # le total de la page vient de la même lecture
        self.assertEqual(page(d, {**f, 'skip': 99})[0], [])
        self.assertEqual(page(d, {**f, 'rating_min': 9.9}), ([], 0))


class OtherScores(unittest.TestCase):
    def test_sort_by_another_site_weighs_votes(self):
        d = db()  # tt1 3 M votes, tt2 900 000, tt4 40 votes
        d.executemany('INSERT INTO h.ratings VALUES (?,?,?)', [('tt1', 'letterboxd', 8.0), ('tt2', 'letterboxd', 9.0),
                                                               ('tt4', 'letterboxd', 10.0), ('tt1', 'tomatoes', 9), ('tt1', 'metacritic', 8)])
        self.assertEqual(ids(search(d, parse({'sort': ['letterboxd']})))[:3], ['tt2', 'tt1', 'tt4'])
        self.assertEqual(ids(search(d, parse({'sort': ['average']})))[0], 'tt1')  # le seul avec trois notes
        self.assertRaises(ValueError, parse, {'sort': ["tomatoes'; --"]})


class ForYou(unittest.TestCase):
    def test_recent_and_shared_recommendations_first(self):
        d = db()  # tt1 (TMDB 278), tt2 (129), tt4 (9) : films de l'index
        d.execute("INSERT INTO tmdb.meta VALUES ('tt5', 55, 'en', ',US,', NULL)")
        d.execute("INSERT INTO h.extra VALUES ('tmdb:700', 'movie', 'Hors index', 2020, NULL, 0, 7, 50)")
        recs = {278: [9, 129, 700], 129: [700, 9]}
        with mock.patch.object(foryou, 'recommendations', lambda kind, numbers: {n: recs[n] for n in numbers if n in recs}):
            self.assertEqual(foryou.candidates(d, 'movie', ['tt1', 'kitsu:3', 'tt2', 'tt5']), 2)  # 129 et 278 sont des titres de départ
            f = {**parse({'seeds': ['tt1,tt2'], 'sort': ['foryou']}), 'foryou': True}
            self.assertEqual(f['seeds'], ['tt1', 'tt2'])
            self.assertEqual(ids(search(d, f)), ['tt4', 'tmdb:700'])  # tt2 est un titre de départ : écarté
        self.assertRaises(ValueError, parse, {'sort': ['foryou']})

    def test_cache_then_tmdb(self):
        calls = []

        def get(key, path, **p):
            calls.append(path)
            return {'results': [{'id': 1}, {'id': 2}]}
        import os, tempfile
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(tmdb, 'TMDB_DB', os.path.join(folder, 't.db')), \
                mock.patch.object(tmdb, 'get', get), mock.patch.object(foryou, 'setting', lambda *a: 'k'):
            self.assertEqual(foryou.recommendations('movie', [10, 11]), {10: [1, 2], 11: [1, 2]})
            self.assertEqual(foryou.recommendations('movie', [10]), {10: [1, 2]})
            self.assertEqual(len(calls), 2)
            foryou.recommendations('movie', [10], now=time.time() + foryou.KEPT + 5)
            self.assertEqual(len(calls), 3)


class Rechecked(unittest.TestCase):
    def test_new_titles_first_then_old_checks(self):
        d = sqlite3.connect(':memory:')
        extras.create(d)
        now = 10_000_000
        d.executemany('INSERT INTO checked VALUES (?)', [('tt1',), ('tt2',), ('tt3',)])
        d.executemany('INSERT INTO checked_at VALUES (?,?)', [('tt2', now - 5), ('tt3', now - playable.OLD - 5)])
        titles = [(f'tt{i}', 'movie') for i in (1, 2, 3, 4)]
        self.assertEqual([t[0] for t in playable.remaining(d, titles, now)], ['tt4', 'tt1', 'tt3'])
        playable.store(d, 'tt1', {('fr', 1)}, now)
        playable.store(d, 'tt1', {('en', 0)}, now)  # le lien français a quitté le cache
        self.assertEqual(d.execute('SELECT * FROM playable').fetchall(), [('tt1', 'en', 0)])


class Preview(unittest.TestCase):
    def setUp(self):
        preview._cache.clear()

    def test_french_summary_trailer_and_scores(self):
        d = db()
        d.execute("INSERT INTO h.ratings VALUES ('tt1', 'tomatoes', 8.9)")
        d.execute("INSERT INTO h.offers VALUES ('tt1', 'Netflix', 'movie')")
        body = {'title': 'Les Évadés', 'release_date': '1994-09-10', 'overview': 'Résumé', 'runtime': 142, 'credits': {'cast': [{'name': f'A{i}'} for i in range(9)],
                'crew': [{'job': 'Director', 'name': 'Réal'}, {'job': 'Writer', 'name': 'X'}]},
                'videos': {'results': [{'site': 'YouTube', 'type': 'Trailer', 'iso_639_1': 'en', 'key': 'ENGLISH1'},
                                       {'site': 'YouTube', 'type': 'Trailer', 'iso_639_1': 'fr', 'key': 'FRANCAIS'}]}}
        with mock.patch.object(tmdb, 'get', return_value=body) as get, mock.patch.object(preview, 'setting', lambda *a: 'k'), \
                mock.patch.object(trailer, 'playable', lambda key: True):
            out = preview.preview(d, 'tt1', 'movie')
            preview.preview(d, 'tt1', 'movie')
        self.assertEqual(get.call_count, 1)
        self.assertEqual((out['description'], out['trailer'], out['directors'], len(out['cast'])), ('Résumé', 'FRANCAIS', ['Réal'], 4))
        self.assertEqual((out['names'], out['year']), (['Drame culte', 'Les Évadés'], 1994))
        self.assertEqual((out['ratings'], out['places']), ({'tomatoes': 8.9}, ['Netflix']))
        d.execute("INSERT INTO h.merged VALUES ('tt99', 'tt1')")
        self.assertEqual(preview.preview(d, 'tt1', 'movie')['twin'], 'tt99')

    def test_trailer_french_dubbed_then_subtitled_then_english(self):
        v = lambda key, lang, name='Bande-annonce', kind='Trailer', site='YouTube': {
            'key': key, 'iso_639_1': lang, 'name': name, 'type': kind, 'site': site}
        en, vost, vf = v('english01', 'en', 'Official Trailer'), v('vostfr001', 'fr', 'Bande-annonce VOST'), v('dubbed001', 'fr', 'Bande-annonce VF')
        teaser, clip = v('teaser001', 'fr', 'Teaser VF', 'Teaser'), v('extrait01', 'fr', 'Extrait', 'Clip')
        with mock.patch.object(trailer, 'playable', lambda key: key != 'mort00001'):
            self.assertEqual(trailer.choose([en, clip, vost, vf]), ('dubbed001', 'fr'))
            self.assertEqual(trailer.choose([en, vost]), ('vostfr001', 'fr'))
            self.assertEqual(trailer.choose([en, teaser]), ('teaser001', 'fr'))
            self.assertEqual(trailer.choose([en, clip]), ('english01', 'en'))
            self.assertEqual(trailer.choose([v('mort00001', 'fr', 'VF'), en]), ('english01', 'en'))  # retirée de YouTube
            self.assertEqual(trailer.choose([en, v('sanslang1', None)], 'fr'), ('sanslang1', 'fr'))
            self.assertEqual(trailer.choose([v('x"><script', 'fr'), clip]), (None, None))

    def test_one_trailer_per_language_stremio_language_first(self):
        v = lambda key, lang, name='Trailer': {'key': key, 'iso_639_1': lang, 'name': name, 'type': 'Trailer', 'site': 'YouTube'}
        videos = [v('english01', 'en'), v('vostfr001', 'fr', 'Bande-annonce VOSTFR'), v('allemand1', 'de')]
        with mock.patch.object(trailer, 'playable', lambda key: True):
            self.assertEqual([(t['key'], t['label']) for t in trailer.choose_all(videos, 'en', ('en', 'en', 'fr'))],
                             [('english01', 'EN'), ('vostfr001', 'VOSTFR')])
            self.assertEqual([t['lang'] for t in trailer.choose_all(videos, 'en', ('de', 'en', 'fr'))], ['de', 'en', 'fr'])

    def test_preview_follows_stremio_language(self):
        body = {'overview': 'Summary', 'videos': {'results': [{'site': 'YouTube', 'type': 'Trailer', 'iso_639_1': 'en', 'key': 'ENGLISH1'},
                                                             {'site': 'YouTube', 'type': 'Trailer', 'iso_639_1': 'fr', 'key': 'FRANCAIS'}]}}
        with mock.patch.object(tmdb, 'get', return_value=body) as get, mock.patch.object(preview, 'setting', lambda *a: 'k'),                 mock.patch.object(trailer, 'playable', lambda key: True):
            out = preview.preview(db(), 'tt1', 'movie', 'en')
        self.assertEqual(get.call_args.kwargs['language'], 'en')
        self.assertEqual((out['trailer'], [t['label'] for t in out['trailers']]), ('ENGLISH1', ['EN', 'FR']))
        self.assertRaises(ValueError, preview.preview, db(), 'tt1', 'movie', 'english')

    def test_tmdb_down_or_bad_id(self):
        with mock.patch.object(tmdb, 'get', side_effect=OSError), mock.patch.object(preview, 'setting', lambda *a: 'k'):
            self.assertEqual(preview.preview(db(), 'tt1', 'movie'), {'ratings': {}, 'places': [], 'twin': None, 'names': ['Drame culte', 'Les Évadés']})
        for bad in ('tt1/../x', '', 'kitsu:1'):
            self.assertRaises(ValueError, preview.preview, db(), bad, 'movie')



class OtherPC(unittest.TestCase):
    """PC installé par l'installeur : pas d'addon de liens ni de clé MDBList, les données du paquet restent intactes."""
    def test_playable_without_sources_touches_nothing(self):
        with mock.patch.object(playable.addon_langues, 'sources', return_value=[]),              mock.patch.object(playable.extras, 'open_db', side_effect=AssertionError('base ouverte')):
            playable.main()

    def test_mdblist_without_key_touches_nothing(self):
        with mock.patch.object(mdblist, 'setting', return_value=None),              mock.patch.object(mdblist.extras, 'open_db', side_effect=AssertionError('base ouverte')):
            mdblist.main()


if __name__ == '__main__':
    unittest.main()
