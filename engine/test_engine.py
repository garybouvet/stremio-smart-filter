"""uv run python -m unittest engine.test_engine"""
import contextlib, io, os, sqlite3, tempfile, unittest, urllib.error
from unittest import mock
from . import catalogs, extras, harvest, mdblist, playable, tmdb, tmdb_all, tmdb_links
from .imdb_index import genre_mask
from .search import lookup, options as search_options, parse, search, to_meta

ROWS = [('tt1', 'movie', 'Drame culte', 1994, 142, genre_mask(['Drama']), 9.3, 3000000),
        ('tt2', 'movie', 'Animé', 2001, 125, genre_mask(['Animation', 'Drama']), 8.6, 900000),
        ('tt3', 'movie', 'Navet', 2010, 90, genre_mask(['Comedy']), 3.1, 20000),
        ('tt4', 'movie', 'Pépite confidentielle', 2015, 100, genre_mask(['Drama']), 8.8, 40),
        ('tt5', 'series', 'Série', 2008, 47, genre_mask(['Drama', 'Crime']), 9.5, 2000000)]

META = [('tt1', 278, 'en', ',US,', 'Les Évadés'), ('tt2', 129, 'ja', ',JP,', None), ('tt4', 9, 'fr', ',FR,BE,', None)]


def db():
    d = sqlite3.connect(':memory:')
    d.execute('CREATE TABLE titles (id TEXT PRIMARY KEY, type TEXT, name TEXT, year INT,'
              ' runtime INT, genres INT, rating REAL, votes INT)')
    d.executemany('INSERT INTO titles VALUES (?,?,?,?,?,?,?,?)', ROWS)
    d.execute("ATTACH ':memory:' AS tmdb")
    d.execute('CREATE TABLE tmdb.meta (id TEXT PRIMARY KEY, tmdb_id INT, lang TEXT, countries TEXT, name_fr TEXT)')
    d.executemany('INSERT INTO tmdb.meta VALUES (?,?,?,?,?)', META)
    d.execute("ATTACH ':memory:' AS h")
    extras.create(d, 'h')
    return d


def ids(metas):
    return [m['id'] for m in metas]


class Search(unittest.TestCase):
    def test_cumulative_filters(self):
        q = {'rating_min': ['8'], 'votes_min': ['1000'], 'genres_all': ['Drama'], 'genres_none': ['Animation']}
        self.assertEqual(ids(search(db(), parse(q))), ['tt1'])

    def test_sort_and_type(self):
        self.assertEqual(ids(search(db(), parse({'sort': ['year']}))), ['tt4', 'tt3', 'tt2', 'tt1'])
        self.assertEqual(ids(search(db(), parse({'type': ['series']}))), ['tt5'])

    def test_oldest_first_leaves_unknown_years_last(self):
        d = db()
        d.execute("INSERT INTO titles VALUES ('tt9', 'movie', 'Sans date', NULL, NULL, 0, NULL, NULL)")
        self.assertEqual(ids(search(d, parse({'sort': ['year_asc']}))), ['tt1', 'tt2', 'tt3', 'tt4', 'tt9'])

    def test_best_rating_weighs_votes(self):
        # 8,8 sur 40 votes passe derrière 8,6 sur 900 000 votes.
        self.assertEqual(ids(search(db(), parse({'genres_all': ['Drama']}))), ['tt1', 'tt2', 'tt4'])

    def test_genres_any_and_ranges(self):
        q = {'genres_any': ['Comedy,Animation'], 'year_max': ['2005'], 'runtime_min': ['120']}
        self.assertEqual(ids(search(db(), parse(q))), ['tt2'])

    def test_language_country_and_french_title(self):
        self.assertEqual(ids(search(db(), parse({'language': ['fr']}))), ['tt4'])
        self.assertEqual(ids(search(db(), parse({'country': ['BE']}))), ['tt4'])
        self.assertEqual(search(db(), parse({'country': ['US']}))[0]['name'], 'Les Évadés')
        self.assertEqual(search(db(), parse({}))[1]['name'], 'Animé')

    def test_exclude_country(self):
        # tt3 n'a pas de données TMDB : on ne sait pas d'où il vient, il reste affiché.
        self.assertEqual(sorted(ids(search(db(), parse({'country_not': ['US']})))), ['tt2', 'tt3', 'tt4'])
        self.assertEqual(sorted(ids(search(db(), parse({'country_not': ['BE']})))), ['tt1', 'tt2', 'tt3'])
        self.assertRaises(ValueError, parse, {'country_not': ["IN' OR 1=1"]})

    def test_options(self):
        from .search import options
        self.assertEqual(options(db())['languages'], [])  # moins de 20 titres par langue

    def test_rejects_bad_input(self):
        for q in ({'language': ["fr' OR 1=1"]}, {'country': ['fra']}, {'sort': ['x; DROP TABLE titles']}, {'genres_all': ['Nope']}, {'rating_min': ['abc']},
                  {'type': ['tv']}):
            self.assertRaises(ValueError, parse, q)

    def test_lookup(self):
        rows = [(i, 'movie', None, None, None, 0, r, None) for i, r in (('tt1', None), ('tt3', 9.9), ('tt9', None), ('tt8', 7.0))]
        # L'index prime sur l'addon (tt3 reste un navet) ; hors index, on juge sur ce que dit l'addon.
        self.assertEqual(set(lookup(db(), rows, parse({'rating_min': ['5']}))), {'tt1', 'tt8'})


class Harvested(unittest.TestCase):
    def base(self):
        d = db()
        d.execute("INSERT INTO h.extra VALUES ('tmdb:7', 'movie', 'Sans IMDb', 2020, NULL, ?, 8.0, 500)", (genre_mask(['Drama']),))
        d.executemany('INSERT INTO h.presence VALUES (?,?)', [('tt1', 'Netflix'), ('tmdb:7', 'Netflix'), ('tt2', 'Canal+')])
        d.executemany('INSERT INTO h.offers VALUES (?,?,?)', [('tt1', 'Netflix', 'movie'), ('tmdb:7', 'Netflix', 'movie')])
        d.executemany('INSERT INTO h.ratings VALUES (?,?,?)', [('tt1', 'tmdb', 8.7), ('tt2', 'tmdb', 6.0)])
        d.executemany('INSERT INTO h.playable VALUES (?,?,?)', [('tt1', 'fr', 1), ('tt2', 'fr', 0)])
        d.execute("INSERT INTO h.posters VALUES ('tt1', 'note.jpg')")
        return d

    def test_titles_outside_imdb_are_searchable(self):
        out = search(self.base(), parse({'rating_min': ['7.5'], 'votes_min': ['100']}))
        self.assertIn('tmdb:7', ids(out))
        self.assertEqual(out[0]['poster'], 'note.jpg')

    def test_place_score_and_link(self):
        got = lambda q: set(ids(search(self.base(), parse(q))))
        self.assertEqual(got({'place': ['Netflix']}), {'tt1', 'tmdb:7'})
        self.assertEqual(got({'score_tmdb_min': ['8']}), {'tt1'})
        self.assertEqual(got({'link': ['fr']}), {'tt1', 'tt2'})
        self.assertEqual(got({'link': ['fr_cached']}), {'tt1'})
        self.assertRaises(ValueError, parse, {'link': ['x; drop']})
        self.assertEqual(set(ids(search(self.base(), {**parse({}), 'harvested': True}))), {'tt1', 'tt2', 'tmdb:7'})

    def test_options_list_what_was_harvested(self):
        d = self.base()
        d.executemany('INSERT INTO h.offers VALUES (?,?,?)', [(f'x{i}', 'Arte', 'movie') for i in range(20)])
        o = search_options(d)
        self.assertEqual((o['places'], o['scores'], o['links']), (['Arte'], ['tmdb'], ['fr']))

    def test_place_names_merge_duplicates(self):
        self.assertEqual({extras.place_name(n) for n in ('Netflix', 'Netflix Standard with Ads')}, {'Netflix'})
        self.assertEqual(extras.place_name('INA  madelen Amazon Channel '), 'INA madelen')

    def test_playable_waits_then_retries_a_refused_batch(self):
        answers = iter([playable.Refused, playable.Refused, ('tt1', {('fr', 1)})])

        def check(title):
            a = next(answers)
            if a is playable.Refused:
                raise a
            return a
        with tempfile.TemporaryDirectory() as tmp:
            index = os.path.join(tmp, 'index.db')
            d = sqlite3.connect(index)
            d.execute('CREATE TABLE titles (id TEXT, type TEXT, votes INT)')
            d.execute("INSERT INTO titles VALUES ('tt1', 'movie', 5000)")
            d.commit()
            d.close()
            with mock.patch.object(playable, 'DB_PATH', index), mock.patch.object(extras, 'EXTRAS_DB', os.path.join(tmp, 'x.db')),                     mock.patch.object(playable, 'check', check), mock.patch.object(playable.time, 'sleep') as sleep,                     contextlib.redirect_stdout(io.StringIO()):
                playable.main()
            self.assertEqual([c.args[0] for c in sleep.call_args_list], [playable.WAIT, playable.WAIT * 2])
            db = sqlite3.connect(os.path.join(tmp, 'x.db'))
            self.assertEqual(db.execute('SELECT * FROM checked').fetchall(), [('tt1',)])
            db.close()

    def test_playable_reads_links_and_keeps_failures_for_later(self):
        vf = {'name': 'Torrentio\n[RD+] 1080p', 'title': 'Film.2020.TRUEFRENCH.1080p', 'url': 'http://x/1'}
        vo = {'name': 'Torrentio\n1080p', 'title': 'Film.2020.1080p\n🇬🇧', 'url': 'http://x/2'}
        self.assertEqual(playable.offers([vf, vo]), {('fr', 1), ('en', 0)})
        with mock.patch.object(playable.addon_langues, 'sources', lambda: ['u']), mock.patch.object(playable, 'PAUSE', 0):
            with mock.patch.object(playable, 'ask', lambda *a: None):
                self.assertIsNone(playable.check(('tt1', 'movie')))
            with mock.patch.object(playable, 'ask', lambda u, t, v: [] if v == 'tt5:1:1' else None):
                self.assertEqual(playable.check(('tt5', 'series')), ('tt5', set()))

    def test_mdblist_scores_on_ten_whatever_the_source_scale(self):
        items = [{'ids': {'imdb': 'tt1'}, 'ratings': [{'source': 'letterboxd', 'value': 4.6, 'score': 92}, {'source': 'tomatoes', 'value': 89, 'score': 89},
                                                      {'source': 'imdb', 'value': 9.3, 'score': 93}, {'source': 'trakt', 'value': None, 'score': None}]},
                 {'ids': {'imdb': None}, 'ratings': [{'source': 'tomatoes', 'score': 50}]}]
        self.assertEqual(mdblist.rows_of(items), [('tt1', 'letterboxd', 9.2), ('tt1', 'tomatoes', 8.9)])

    def test_tmdb_survives_network_cuts(self):
        calls = []

        class Resp(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): pass

        def flaky(req, timeout):
            calls.append(1)
            if len(calls) < 3:
                raise urllib.error.URLError(ConnectionResetError(10054))
            return Resp(b'{"ok": 1}')

        with mock.patch.object(tmdb.urllib.request, 'urlopen', flaky), mock.patch.object(tmdb.time, 'sleep'):
            self.assertEqual(tmdb.get('k', '/x'), {'ok': 1})
        with mock.patch.object(tmdb.urllib.request, 'urlopen', mock.Mock(side_effect=OSError('coupé'))), mock.patch.object(tmdb.time, 'sleep'):
            self.assertIsNone(tmdb.try_fetch('k', 'tt1'))  # abandonné après les réessais, sans faire tomber la tâche

    def test_remember_keeps_every_addon_seen(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(extras, 'ADDONS', os.path.join(d, 'a.json')):
            extras.remember(u for u in ['b', 'a'])
            extras.remember(iter(['c']))
            self.assertEqual(extras.addons(), ['a', 'b', 'c'])

    def test_harvest_jobs_skip_what_cannot_be_walked(self):
        m = {'catalogs': [{'type': 'movie', 'id': 'top', 'name': 'Disney Plus', 'extra': [{'name': 'genre', 'options': ['A', 'B']}]},
                          {'type': 'movie', 'id': 'new', 'name': 'New', 'extra': [{'name': 'genre', 'isRequired': True, 'options': ['A']}]},
                          {'type': 'movie', 'id': 's', 'extra': [{'name': 'search', 'isRequired': True}]},
                          {'type': 'channel', 'id': 'c'}]}
        self.assertEqual(list(harvest.jobs(m)), [('movie', 'top', 'Disney+', []), ('movie', 'top', 'Disney+', [('genre', 'A')]),
                                                 ('movie', 'top', 'Disney+', [('genre', 'B')]), ('movie', 'new', 'New', [('genre', 'A')])])

    def test_harvest_walk_stops_when_addon_ignores_skip(self):
        saved = []
        with mock.patch.object(catalogs, 'fetch_page', lambda *a: [{'id': 'tt1'}]), mock.patch.object(harvest, 'PAUSE', 0):
            self.assertEqual(harvest.walk('http://x', ('movie', 'top', 'L', []), lambda *a: saved.append(a)), 1)
        self.assertEqual(len(saved), 1)


class Catalog(unittest.TestCase):
    def test_pages_until_enough_and_keeps_order(self):
        pages = {0: [{'id': 'tt3'}, {'id': 'tt1', 'name': 'Titre FR'}], 2: [{'id': 'tt4'}, {'id': 'tt2'}], 4: []}
        with mock.patch.object(catalogs, 'fetch_page', lambda b, t, c, s, e: pages[s]):
            # Les pages sont lues en entier : on s'arrête après celle qui atteint le nombre voulu.
            out, nxt = catalogs.filtered(db(), 'http://x', 'top', parse({'rating_min': ['8']}), want=1)
            self.assertEqual((ids(out), nxt), (['tt1'], 2))
            out, nxt = catalogs.filtered(db(), 'http://x', 'top', parse({'rating_min': ['8']}), want=2)
            self.assertEqual((ids(out), nxt), (['tt1', 'tt4', 'tt2'], 4))
            self.assertEqual(out[0]['name'], 'Titre FR')
            out, nxt = catalogs.filtered(db(), 'http://x', 'top', parse({'rating_min': ['8']}), want=50)
            self.assertEqual((ids(out), nxt), (['tt1', 'tt4', 'tt2'], None))

    def test_failed_page_is_not_retried_at_once(self):
        calls = []

        def down(req, timeout):
            calls.append(req.full_url)
            raise OSError('504')

        with mock.patch.object(catalogs.urllib.request, 'urlopen', down):
            catalogs._cache.clear()
            catalogs._down.clear()
            for _ in range(2):
                self.assertRaises(OSError, catalogs.fetch_page, 'https://a.b', 'movie', 'top', 0)
        self.assertEqual(len(calls), 1)

    def test_addon_failing_midway_keeps_found_titles(self):
        def fetch(base, typ, cid, skip, extra):
            if skip:
                raise OSError('504')
            return [{'id': 'tt1'}]

        with mock.patch.object(catalogs, 'fetch_page', fetch):
            self.assertEqual(ids(catalogs.filtered(db(), 'http://x', 'top', parse({}), want=5)[0]), ['tt1'])
            self.assertRaises(OSError, catalogs.filtered, db(), 'http://x', 'top', parse({}), start=1)

    def test_every_kind_of_id(self):
        metas = [{'id': 'tmdb:155', 'imdb_id': 'tt1', 'name': 'Par TMDB', 'poster': 'p.jpg'},
                 {'id': 'tmdb-dice:7'}, {'id': 'tmdb:no-content', 'name': 'Error'}, {'id': 'dlrealdebrid123'},
                 {'id': 'tt3'}, {'id': 'tt3'}]
        with mock.patch.object(catalogs.tmdb, 'imdb_of', lambda typ, n: {'7': 'tt2'}[n]):
            out = catalogs.kept(db(), metas, parse({}))
        self.assertEqual(ids(out), ['tt1', 'tt2', 'tt3'])
        self.assertEqual((out[0]['poster'], out[0]['imdbRating']), ('p.jpg', '9.3'))

    def test_title_outside_index_uses_addon_data(self):
        new = {'id': 'tt99', 'name': 'Inédit', 'releaseInfo': '2026', 'imdbRating': '8.0', 'runtime': '2h10min',
               'genres': ['Drame', 'Science-Fiction']}
        self.assertEqual(catalogs.row_of(new, 'movie')[3:7], (2026, 130, genre_mask(['Drama', 'Sci-Fi']), 8.0))
        keep = lambda q: ids(catalogs.kept(db(), [new], parse(q)))
        self.assertEqual(keep({'rating_min': ['7'], 'genres_all': ['Sci-Fi'], 'year_min': ['2020']}), ['tt99'])
        self.assertEqual(keep({'rating_min': ['9']}), [])
        self.assertEqual(keep({'votes_min': ['1000']}), [])  # l'addon ne donne pas les votes : critère non vérifiable
        self.assertEqual(catalogs.row_of({'id': 'tt1', 'imdbRating': ''}, 'movie')[3:7], (None, None, 0, None))

    def test_language_filter_completes_missing_titles(self):
        with mock.patch.object(catalogs.tmdb, 'complete') as complete:
            catalogs.kept(db(), [{'id': 'tt3'}], parse({'rating_min': ['1']}))
            complete.assert_not_called()
            catalogs.kept(db(), [{'id': 'tt3'}], parse({'language': ['fr']}))
            self.assertEqual(complete.call_args[0][1], ['tt3'])

    def test_everywhere_merges_sorts_and_survives_a_failure(self):
        pages = {('a', 0): [{'id': 'tt3'}, {'id': 'tt1'}], ('a', 2): [],
                 ('b', 0): [{'id': 'tmdb:1', 'imdb_id': 'tt1'}, {'id': 'tt2'}], ('b', 2): []}

        def fetch(base, typ, cid, skip, extra):
            if cid == 'panne':
                raise OSError('source en panne')
            return pages[cid, skip]

        sources = [('http://x', 'a', []), ('http://x', 'panne', []), ('http://x', 'b', [])]
        with mock.patch.object(catalogs, 'fetch_page', fetch):
            out, nxt = catalogs.everywhere(db(), sources, parse({'limit': ['2']}))
            self.assertEqual((ids(out), nxt), (['tt1', 'tt2'], 2))
            out, nxt = catalogs.everywhere(db(), sources, parse({'limit': ['2'], 'skip': ['2']}))
            self.assertEqual((ids(out), nxt), (['tt3'], None))

    def test_sources_of(self):
        raw = '{"https://a.b/cfg/manifest.json": [["top", "genre=Action&skip=50"], ["new", ""]], "http://bad": [["x", ""]]}'
        self.assertEqual(catalogs.sources_of(raw), [('https://a.b/cfg', 'top', [('genre', 'Action')]), ('https://a.b/cfg', 'new', [])])
        many = '{"https://a.b/manifest.json": [["a", ""]' + ',["b", ""]' * 60 + ']}'
        for bad in ('[]', '{}', 'x', '{"https://a.b/manifest.json": 3}', many):
            self.assertRaises(ValueError, catalogs.sources_of, bad)

    def test_page_url_with_extra(self):
        seen = []

        class Resp:
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def read(self): return b'{"metas": []}'

        with mock.patch.object(catalogs.urllib.request, 'urlopen', lambda req, timeout: seen.append(req.full_url) or Resp()):
            catalogs._cache.clear()
            catalogs.fetch_page('https://a.b/cfg', 'movie', 'top', 0)
            catalogs.fetch_page('https://a.b/cfg', 'movie', 'top', 50, [('genre', 'Sci-Fi & Fantasy')])
        self.assertEqual(seen, ['https://a.b/cfg/catalog/movie/top.json',
                                'https://a.b/cfg/catalog/movie/top/genre=Sci-Fi%20%26%20Fantasy&skip=50.json'])

    def test_addon_url_validation(self):
        self.assertEqual(catalogs.addon_base('https://a.b/cfg/manifest.json'), 'https://a.b/cfg')
        for bad in ('file:///c:/x/manifest.json', 'https://a.b/other', ''):
            self.assertRaises(ValueError, catalogs.addon_base, bad)


class Tmdb(unittest.TestCase):
    def test_fetch_movie_series_and_missing(self):
        from . import tmdb
        answers = {
            '/find/tt1': {'movie_results': [{'id': 278, 'original_language': 'en', 'title': 'Les Évadés'}]},
            '/movie/278': {'origin_country': ['US']},
            '/find/tt5': {'tv_results': [{'id': 1396, 'original_language': 'en', 'name': 'Breaking Bad', 'origin_country': ['US']}]},
            '/find/tt9': {'movie_results': [], 'tv_results': []},
        }
        with mock.patch.object(tmdb, 'get', lambda key, path, **p: answers[path]):
            self.assertEqual(tmdb.fetch('k', 'tt1'), ('tt1', 278, 'en', ',US,', 'Les Évadés'))
            self.assertEqual(tmdb.fetch('k', 'tt5'), ('tt5', 1396, 'en', ',US,', 'Breaking Bad'))
            self.assertEqual(tmdb.fetch('k', 'tt9'), ('tt9', None, None, None, None))

    def test_series_ignores_a_false_movie_hit(self):
        both = {'movie_results': [{'id': 1, 'title': 'Faux'}], 'tv_results': [{'id': 2, 'name': 'Vraie', 'origin_country': []}]}
        with mock.patch.object(tmdb, 'get', lambda key, path, **p: both if path.startswith('/find') else {}):
            self.assertEqual(tmdb.fetch('k', 'tt1', series=True)[1], 2)
            self.assertEqual(tmdb.fetch('k', 'tt1')[1], 1)

    def test_links_series_to_imdb_and_keeps_the_rest(self):
        db, meta = sqlite3.connect(':memory:'), sqlite3.connect(':memory:')
        extras.create(db)
        meta.execute('CREATE TABLE meta (id TEXT PRIMARY KEY, tmdb_id INT, lang TEXT, countries TEXT, name_fr TEXT)')
        for n in (1, 2, 3, 4):
            db.execute('INSERT INTO extra VALUES (?,?,?,?,?,?,?,?)', (f'tmdb:tv:{n}', 'series', 'S', 2020, None, 0, 7, n))
            db.execute('INSERT INTO ratings VALUES (?,?,?)', (f'tmdb:tv:{n}', 'tmdb', 7))
            meta.execute('INSERT INTO meta VALUES (?,?,?,?,?)', (f'tmdb:tv:{n}', n, 'fr', None, 'S'))
        db.execute("INSERT INTO presence VALUES ('tmdb:tv:1', 'Netflix')")
        meta.execute("INSERT INTO meta VALUES ('tt2', NULL, NULL, NULL, NULL)")

        def get(key, path, **p):
            if path == '/tv/4/external_ids':
                raise OSError
            return {'/tv/1/external_ids': {'imdb_id': 'tt1'}, '/tv/2/external_ids': {'imdb_id': 'tt2'}}.get(path, {'imdb_id': None})
        with mock.patch.object(tmdb, 'get', get), contextlib.redirect_stdout(io.StringIO()):
            tmdb_links.link('k', db, meta, {'tt2'})
        one = lambda d, sql: sorted(r[0] for r in d.execute(sql))
        self.assertEqual(one(db, 'SELECT id FROM extra'), ['tmdb:tv:3', 'tmdb:tv:4', 'tt1'])  # tt2 : déjà dans l'index
        self.assertEqual(one(db, 'SELECT id FROM ratings'), ['tmdb:tv:3', 'tmdb:tv:4', 'tt1', 'tt2'])
        self.assertEqual(one(db, 'SELECT id FROM presence'), ['tt1'])
        self.assertEqual(one(db, 'SELECT id FROM unlinked'), ['tmdb:tv:3'])  # 4 n'a pas répondu : à reprendre
        self.assertEqual(meta.execute("SELECT tmdb_id FROM meta WHERE id = 'tt2'").fetchone(), (2,))

    def test_movie_and_series_with_same_number_stay_apart(self):
        db, meta = sqlite3.connect(':memory:'), sqlite3.connect(':memory:')
        extras.create(db)
        meta.execute('CREATE TABLE meta (id TEXT PRIMARY KEY, tmdb_id INT, lang TEXT, countries TEXT, name_fr TEXT)')
        tmdb_all.storer(db, meta, {}, 'movie', {})([{'id': 7, 'title': 'Film', 'vote_count': 3, 'vote_average': 6}])
        tmdb_all.storer(db, meta, {}, 'tv', {})([{'id': 7, 'name': 'Série', 'vote_count': 3, 'vote_average': 8}])
        self.assertEqual(db.execute('SELECT id, name FROM extra ORDER BY id').fetchall(), [('tmdb:7', 'Film'), ('tmdb:tv:7', 'Série')])
        self.assertEqual(db.execute('SELECT value FROM ratings ORDER BY id').fetchall(), [(6,), (8,)])
        self.assertEqual(to_meta(('tmdb:tv:7', 'series', 'Série', 2020, None, 0, 8, 3, None, None))['id'], 'tmdb:7')


@contextlib.contextmanager
def running_engine():
    """Moteur réel sur un port libre, avec un index de test (ROWS) et une base TMDB vide. Donne get(chemin)."""
    import json, os, tempfile, threading, urllib.request
    from http.server import ThreadingHTTPServer
    from . import search, server, tmdb
    with tempfile.TemporaryDirectory() as tmp:
        index = os.path.join(tmp, 'index.db')
        d = sqlite3.connect(index)
        d.execute('CREATE TABLE titles (id TEXT PRIMARY KEY, type TEXT, name TEXT, year INT,'
                  ' runtime INT, genres INT, rating REAL, votes INT)')
        d.executemany('INSERT INTO titles VALUES (?,?,?,?,?,?,?,?)', ROWS)
        d.commit()
        d.close()
        front = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        threading.Thread(target=front.serve_forever, daemon=True).start()
        try:
            with mock.patch.object(search, 'DB_PATH', index), \
                    mock.patch.object(tmdb, 'TMDB_DB', os.path.join(tmp, 'tmdb.db')), \
                    mock.patch.object(extras, 'EXTRAS_DB', os.path.join(tmp, 'extras.db')), \
                    mock.patch.object(extras, 'ADDONS', os.path.join(tmp, 'addons.json')), mock.patch('sys.stderr'):
                def get(p, headers={'X-Stremio-Custom': '1'}):
                    return json.load(urllib.request.urlopen(
                        urllib.request.Request(f'http://127.0.0.1:{front.server_address[1]}{p}', headers=headers)))
                get.port = front.server_address[1]
                yield get
        finally:
            front.shutdown()
            front.server_close()


class Api(unittest.TestCase):
    def test_works_before_tmdb_enrichment(self):
        with running_engine() as get:
            self.assertEqual(get('/api/options')['languages'], [])
            self.assertEqual([m['id'] for m in get('/api/search?type=series')['metas']], ['tt5'])


class Relay(unittest.TestCase):
    def test_forwards_method_body_and_range(self):
        import threading, urllib.request
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from . import proxy, server

        class Fake(BaseHTTPRequestHandler):
            def answer(self):
                n = int(self.headers.get('Content-Length') or 0)
                data = f'{self.command} {self.path} {self.headers.get("Range")} {self.rfile.read(n).decode()}'.encode()
                self.send_response(206)
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(data)
            do_GET = do_POST = answer
            def log_message(self, *a): pass

        backend = ThreadingHTTPServer(('127.0.0.1', 0), Fake)
        front = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        for s in (backend, front):
            threading.Thread(target=s.serve_forever, daemon=True).start()
        try:
            with mock.patch.object(proxy, 'TARGET', backend.server_address), mock.patch('sys.stderr'):
                url = f'http://127.0.0.1:{front.server_address[1]}/ss/abc/0?x=1'
                r = urllib.request.urlopen(urllib.request.Request(url, headers={'Range': 'bytes=5-'}))
                self.assertEqual((r.status, r.read()), (206, b'GET /abc/0?x=1 bytes=5- '))
                self.assertIsNone(r.headers.get('Access-Control-Allow-Origin'))
                r = urllib.request.urlopen(urllib.request.Request(url, data=b'{"a":1}', method='POST'))
                self.assertEqual(r.read(), b'POST /abc/0?x=1 None {"a":1}')
        finally:
            backend.shutdown()
            front.shutdown()


if __name__ == '__main__':
    unittest.main()
