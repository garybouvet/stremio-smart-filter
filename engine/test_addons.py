"""uv run python -m unittest engine.test_addons"""
import concurrent.futures as cf, json, os, subprocess, threading, time, unittest, urllib.error, urllib.request
from unittest import mock
from . import addon_filtres, addon_langues, stream_languages as sl, tracks
from .test_engine import running_engine

# Titres réels renvoyés par Torrentio et MediaFusion (2026-10-30), comme dans stremio-web/tests/streamLanguages.spec.js.
T = lambda title, name='[RD+] Torrentio\n1080p', url='https://x/resolve/realdebrid/K/' + 'a' * 40 + '/null/0/f.mkv': \
    {'name': name, 'title': title, 'url': url}
FR_EN = T('Les evades 1994 - 1080p FR EN x264 ac3 mHDgz..mkv\n👤 66 💾 3.53 GB ⚙️ Torrent9\n🇬🇧 / 🇫🇷')
SUBS = T('The.Shawshank.Redemption.1994.bluray.sdr.1080p.av1.5.1.opus.subs…\n🇬🇧 / 🇯🇵 / 🇫🇷 / 🇩🇪')
MULTI = T('The.Shawshank.Redemption.1994.1080p.Bluray.MULTi.DTS-HD.Master.H264\nMulti Audio / 🇬🇧 / 🇫🇷')
VOSTFR = T('Dune.Part.Two.2024.VOSTFR.1080p.WEB.H264\n🇫🇷')
MULTI_SUBS = T('[moon] Dune: Part Two 2024 1080p WEBRip x264 AC3 MultiSubs\nMulti Subs / 🇬🇧 / 🇫🇷')
EN = T('The.Shawshank.Redemption.1994.1080p.BluRay.x264-AMIABLE\n🇬🇧', name='[RD download] Torrentio\n1080p')
MF_FR = {'name': 'MediaFusion | Midnight 🧲 RD ⚡️ 1080p', 'description': '📺 BluRay REMUX\n🌐 French\n🔗 Zilean', 'url': 'https://m/x'}


class Detector(unittest.TestCase):
    def test_same_rules_as_interface(self):
        self.assertEqual([sl.audio_match(sl.detect(s), 'fr') for s in (FR_EN, SUBS, MULTI, VOSTFR, MULTI_SUBS, EN, MF_FR)],
                         ['sure', None, 'sure', None, None, None, 'sure'])
        self.assertEqual([sl.subs_match(sl.detect(s), 'fr') for s in (SUBS, VOSTFR, MULTI_SUBS)], ['maybe', 'sure', 'maybe'])
        self.assertEqual([sl.badge(sl.detect(s)) for s in (FR_EN, SUBS, MULTI, VOSTFR, EN)], ['VF', 'ST FR ?', 'VF', 'VOSTFR', None])

    def test_torrentio_flags_alone_first_is_audio_others_subtitles(self):
        # Pistes réelles lues le 2026-11-05 : audio anglais seul, sous-titres français.
        d = sl.detect(T('Backrooms 2026 BluRay 1080p DDP 5 1 x264-hallowed\n👤 96 💾 8.25 GB ⚙️ ThePirateBay\n🇬🇧 / 🇪🇸 / 🇫🇷'))
        self.assertEqual([sl.audio_match(d, l) for l in ('fr', 'es', 'en')], [None, None, 'maybe'])
        self.assertEqual((sl.subs_match(d, 'fr'), sl.badge(d)), ('maybe', 'ST FR ?'))

    def test_multi_audio_flags_are_audio(self):
        self.assertEqual(sl.audio_match(sl.detect(T('Film.2024.MULTi.1080p\nMulti Audio / 🇬🇧 / 🇪🇸')), 'fr'), None)
        self.assertEqual(sl.audio_match(sl.detect(T('Film.2024.MULTi.1080p')), 'fr'), 'maybe')

    def test_release_codes_are_audio_but_not_title_words(self):
        self.assertEqual(sl.audio_match(sl.detect(T('Parasite.2019.MULTi.KOR.Bluray.1080p')), 'ko'), 'sure')
        self.assertEqual(sl.audio_match(sl.detect(T('Dune (2024 Eng 7.1-Fre 5.1-Spa 5.1)')), 'es'), 'sure')
        self.assertEqual(sl.audio_match(sl.detect(T('The.Italian.Job.2003.1080p.BluRay')), 'it'), None)

    def test_subtitle_list_is_not_audio(self):
        d = sl.detect(T('The Shawshank Redemption 1994 BRRip Sub Eng-Arabic-French-Swedish\n🇬🇧 / 🇫🇷'))
        self.assertEqual((sl.audio_match(d, 'fr'), sl.subs_match(d, 'fr')), (None, 'sure'))
        self.assertEqual(sl.audio_match(sl.detect(T('Movie 2020 1080p French Eng Subs')), 'fr'), 'sure')

    def test_real_tracks_win(self):
        d = sl.from_tracks([{'track': 'audio', 'language': 'eng'}, {'track': 'audio', 'language': 'fre'},
                            {'track': 'subtitle', 'language': 'fre'}])
        self.assertEqual((sl.audio_match(d, 'fr'), sl.badge(d)), ('sure', '✓ FR EN · ST FR'))
        d = sl.from_tracks([{'track': 'audio', 'language': 'und'}])
        self.assertEqual((sl.audio_match(d, 'fr'), sl.subs_match(d, 'fr'), sl.badge(d)), (None, None, '✓ ?'))

    def test_cached_debrid(self):
        self.assertEqual([sl.is_cached_debrid(s) for s in (FR_EN, EN, MF_FR)], [True, False, True])


class Filtres(unittest.TestCase):
    def test_menus_to_engine_filters(self):
        q = addon_filtres.to_query('movie', {'genre': 'Drame', 'Genre 2': 'Policier', 'Exclure': 'Animation',
                                             'Note': '8+', 'Décennie': 'Années 1990', 'Durée': '120 à 150 min',
                                             'Tri': 'Popularité', 'skip': '100'})
        self.assertEqual((q['genres_all'], q['genres_none'], q['rating_min'], q['year_min'], q['year_max']),
                         (['Drama,Crime'], ['Animation'], ['8'], ['1990'], ['1999']))
        self.assertEqual((q['runtime_min'], q['runtime_max'], q['sort'], q['skip']), (['120'], ['150'], ['votes'], ['100']))

    def test_platform_country_out_and_other_scores(self):
        q = addon_filtres.to_query('movie', {'Plateforme': 'Netflix', 'Sans le pays': 'Inde', 'Tri': 'Rotten Tomatoes'})
        self.assertEqual((q['place'], q['country_not'], q['sort'], q['known']), (['Netflix'], ['IN'], ['tomatoes'], ['1']))
        menus = {e['name']: e.get('options') for e in addon_filtres.manifest(
            {'languages': [], 'countries': ['IN'], 'places': ['Netflix'], 'scores': ['tomatoes']})['catalogs'][0]['extra']}
        self.assertEqual((menus['Plateforme'], menus['Sans le pays']), (['Netflix'], ['Inde']))
        self.assertIn('Rotten Tomatoes', menus['Tri'])
        self.assertNotIn('Letterboxd', menus['Tri'])  # pas de notes Letterboxd dans ces données

    def test_other_languages(self):
        from .addon_texts import LANGS, NAMES
        for lang in LANGS[1:]:  # chaque variante a tous ses noms (deploy/noms-addon.js à relancer sinon)
            self.assertEqual(set(NAMES[lang]['genres']), set(addon_filtres.GENRES_FR.values()), lang)
            self.assertEqual(set(NAMES[lang]['countries']), set(addon_filtres.COUNTRIES_FR), lang)
            self.assertEqual(set(NAMES[lang]['languages']), set(addon_filtres.LANGS_FR), lang)
        q = addon_filtres.to_query('movie', {'genre': 'Comedy', 'Rating': '8+', 'Not from': 'India', 'Votes': '10,000+',
                                             'Decade': '1990s', 'Sort': 'Rotten Tomatoes'}, 'en')
        self.assertEqual((q['genres_all'], q['rating_min'], q['country_not'], q['votes_min'], q['year_min'], q['sort'], q['lang']),
                         (['Comedy'], ['8'], ['IN'], ['10000'], ['1990'], ['tomatoes'], ['en']))
        m = addon_filtres.manifest({'languages': ['ko'], 'countries': ['DE'], 'places': [], 'scores': []}, 'de')
        menus = {e['name']: e.get('options') for e in m['catalogs'][0]['extra']}
        self.assertEqual((m['id'], m['name'], menus['Land'], menus['Sprache']), ('local.stremio-custom.filtres.de', 'Filter', ['Deutschland'], ['Koreanisch']))
        self.assertIn('Komödie', menus['genre'])

    def test_unknown_option_is_rejected(self):
        self.assertRaises(ValueError, addon_filtres.catalog, None, 'movie', {'Note': '11+'})

    def test_served_with_token_and_cors(self):
        with mock.patch.dict(os.environ, {'ADDON_TOKEN': 'secret'}), running_engine() as get:
            m = get('/addon/secret/filtres/manifest.json', {})
            self.assertEqual([c['type'] for c in m['catalogs']], ['movie', 'series'])
            self.assertNotIn('Langue', [e['name'] for e in m['catalogs'][0]['extra']])  # pas de données TMDB ici
            metas = get('/addon/secret/filtres/catalog/movie/filtres/genre=Drame&Note=8%2B.json', {})['metas']
            self.assertEqual([x['id'] for x in metas], ['tt1', 'tt2'])  # tt4 : 40 votes, sur aucune plateforme, masqué
            with self.assertRaises(urllib.error.HTTPError) as e:
                get('/addon/mauvais/filtres/manifest.json', {})
            self.assertEqual(e.exception.code, 404)

    def test_cors_and_preflight(self):
        # Stremio tourne sur web.stremio.com : il doit pouvoir appeler le moteur local.
        with mock.patch.dict(os.environ, {'ADDON_TOKEN': 'secret'}), running_engine() as get:
            url = f'http://127.0.0.1:{get.port}/addon/secret/filtres/manifest.json'
            pre = urllib.request.urlopen(urllib.request.Request(url, method='OPTIONS'))
            self.assertEqual((pre.status, pre.headers['Access-Control-Allow-Private-Network']), (204, 'true'))
            self.assertEqual(urllib.request.urlopen(url).headers['Access-Control-Allow-Origin'], '*')


class Langues(unittest.TestCase):
    def test_order_badges_and_background_check(self):
        found = {'a/manifest.json': [EN, SUBS, MULTI], 'b/manifest.json': [VOSTFR, FR_EN, MF_FR]}
        checked = {MF_FR['url']: [{'track': 'audio', 'language': 'fre'}]}
        env = {'LANGUES_SOURCES': 'a/manifest.json b/manifest.json', 'LANGUES_LANG': 'fr', 'LANGUES_MODE': 'trier'}
        with mock.patch.dict(os.environ, env), \
                mock.patch.object(addon_langues, 'fetch', lambda u, t, v: found[u]), \
                mock.patch.object(tracks, 'known', lambda urls: {u: checked[u] for u in urls if u in checked}), \
                mock.patch.object(tracks, 'verify_later') as later:
            out = addon_langues.streams('movie', 'tt0111161')
        self.assertEqual([s['name'].split('\n')[0] for s in out], ['✓ FR', 'VF', 'VF', 'VOSTFR', 'ST FR ?', '[RD download] Torrentio'])
        later.assert_called_once_with([MULTI['url'], FR_EN['url']])

    def test_cached_links_first_within_a_language(self):
        later = T('Intouchables.2011.FRENCH.1080p', name='[RD download] Torrentio\n1080p')
        now = T('Intouchables.2011.FRENCH.720p')
        with mock.patch.dict(os.environ, {'LANGUES_SOURCES': 'a/manifest.json', 'LANGUES_MODE': 'trier'}), \
                mock.patch.object(addon_langues, 'fetch', lambda u, t, v: [later, now]), \
                mock.patch.object(tracks, 'known', lambda urls: {}), mock.patch.object(tracks, 'verify_later'):
            self.assertEqual([s['title'] for s in addon_langues.streams('movie', 'tt1')], [now['title'], later['title']])

    def test_strict_mode_drops_the_rest(self):
        with mock.patch.dict(os.environ, {'LANGUES_SOURCES': 'a/manifest.json', 'LANGUES_MODE': 'filtrer'}), \
                mock.patch.object(addon_langues, 'fetch', lambda u, t, v: [EN, FR_EN]), \
                mock.patch.object(tracks, 'known', lambda urls: {}), mock.patch.object(tracks, 'verify_later'):
            self.assertEqual([s['title'] for s in addon_langues.streams('movie', 'tt1')], [FR_EN['title']])


class LanguageMenu(unittest.TestCase):
    def setUp(self):
        addon_langues._recent.clear()

    def links(self, code, found):
        addon_langues._recent.clear()
        with mock.patch.object(addon_langues, 'gather', lambda t, v: found), mock.patch.object(tracks, 'known', lambda urls: {}):
            return addon_langues.language_streams(code, 'movie', 'tt1')

    def test_each_language_is_its_own_addon(self):
        m = addon_langues.language_manifest('subs-fr')
        self.assertEqual((m['name'], m['id']), ('Sous-titres français', 'local.stremio-custom.subs-fr'))
        self.assertEqual(len({addon_langues.language_manifest(c)['id'] for c in addon_langues.VARIANTS}), 9)

    def test_only_the_language_sure_before_probable(self):
        vague = T('Film.2024.MULTi.1080p')
        out = self.links('audio-fr', [vague, EN, FR_EN])
        self.assertEqual([s['title'] for s in out], [FR_EN['title'], vague['title']])
        self.assertTrue(out[0]['name'].startswith('VF\n'))
        self.assertTrue(out[1]['name'].startswith('MULTi ?\n'))

    def test_no_link_hides_the_language(self):
        self.assertEqual(self.links('audio-it', [EN]), [])

    def test_multi_alone_does_not_make_every_language_available(self):
        self.assertEqual(self.links('audio-ko', [T('Film.2024.MULTi.1080p')]), [])
        flagged = T('Film.2024.MULTi.1080p\n🇰🇷')
        self.assertEqual([s['title'] for s in self.links('audio-ko', [flagged])], [flagged['title']])

    def test_vostfr_is_french_subtitles_not_french_audio(self):
        self.assertEqual(self.links('audio-fr', [VOSTFR]), [])
        self.assertTrue(self.links('subs-fr', [VOSTFR])[0]['name'].startswith('VOSTFR\n'))
        self.assertTrue(self.links('subs-fr', [T('Film 2026 1080p\n🇬🇧 / 🇫🇷')])[0]['name'].startswith('ST FR ?\n'))

    def test_sources_are_called_once_for_all_languages(self):
        calls, gate = [], threading.Barrier(len(addon_langues.VARIANTS))

        def slow(typ, vid):
            calls.append(vid)
            time.sleep(0.05)
            return [FR_EN]

        def one(code):
            gate.wait()
            return addon_langues.language_streams(code, 'movie', 'tt1')

        with mock.patch.object(addon_langues, 'gather', slow), mock.patch.object(tracks, 'known', lambda urls: {}), \
                cf.ThreadPoolExecutor(len(addon_langues.VARIANTS)) as pool:
            results = dict(zip(addon_langues.VARIANTS, pool.map(one, addon_langues.VARIANTS)))
        self.assertEqual(len(calls), 1)
        self.assertEqual({c for c, r in results.items() if r}, {'audio-fr', 'audio-en'})

    def test_a_failed_fetch_is_not_kept(self):
        with mock.patch.object(addon_langues, 'gather', side_effect=OSError):
            with self.assertRaises(OSError):
                addon_langues.shared('movie', 'tt1')
        self.assertEqual(addon_langues._recent, {})


class Public(unittest.TestCase):
    def test_only_addons_and_health_on_a_server(self):
        from . import server
        with mock.patch.dict(os.environ, {'ADDON_TOKEN': 'secret'}), mock.patch.object(server, 'PUBLIC', True),                 running_engine() as get:
            self.assertEqual(get('/health', {}), {'ok': True})
            self.assertEqual(get('/addon/secret/filtres/manifest.json', {})['name'], 'Filtres')
            for path in ('/api/options', '/ss/settings', '/', '/index.html'):
                with self.assertRaises(urllib.error.HTTPError) as e:
                    get(path)
                self.assertEqual(e.exception.code, 404, path)

    def test_interface_behind_its_own_token(self):
        from . import server
        with mock.patch.dict(os.environ, {'WEB_TOKEN': 'web'}), mock.patch.object(server, 'PUBLIC', True), \
                running_engine() as get:
            self.assertIn('genres', get('/app/web/api/options'))
            for path in ('/app/autre/api/options', '/app/web/ss/settings', '/api/options'):
                with self.assertRaises(urllib.error.HTTPError) as e:
                    get(path)
                self.assertEqual(e.exception.code, 404, path)

    def test_no_internal_addresses_on_a_server(self):
        from . import catalogs
        with mock.patch.dict(os.environ, {'PUBLIC': '1'}):
            for url in ('http://127.0.0.1:11470/manifest.json', 'http://169.254.169.254/manifest.json', 'http://engine:11480/manifest.json'):
                with self.assertRaises(ValueError, msg=url):
                    catalogs.addon_base(url)
            self.assertEqual(catalogs.addon_base('https://1.1.1.1/x/manifest.json'), 'https://1.1.1.1/x')

    def test_rate_limit(self):
        from . import ratelimit
        self.assertTrue(all(ratelimit.allow('1.2.3.4', limit=3, now=t) for t in (0, 1, 2)))
        self.assertFalse(ratelimit.allow('1.2.3.4', limit=3, now=3))
        self.assertTrue(ratelimit.allow('5.6.7.8', limit=3, now=3))  # une autre IP n'est pas touchée
        self.assertTrue(ratelimit.allow('1.2.3.4', limit=3, now=61))  # la fenêtre a glissé

    def test_verification_can_be_disabled_on_a_server(self):
        with mock.patch.dict(os.environ, {'LANGUES_SOURCES': 'a/manifest.json', 'LANGUES_VERIFY': '0'}),                 mock.patch.object(addon_langues, 'fetch', lambda u, t, v: [FR_EN, MULTI]),                 mock.patch.object(tracks, 'known', lambda urls: {}), mock.patch.object(tracks, 'verify_later') as later:
            addon_langues.streams('movie', 'tt1')
        later.assert_called_once_with([])


class Tracks(unittest.TestCase):
    def test_key_and_ffprobe_parsing(self):
        self.assertEqual(tracks.key_of(FR_EN['url']), 'a' * 40 + ':f.mkv')
        out = json.dumps({'streams': [{'codec_type': 'video'}, {'codec_type': 'audio', 'tags': {'language': 'fre'}},
                                      {'codec_type': 'subtitle', 'tags': {'language': 'eng', 'title': 'Forced'}}]}).encode()
        with mock.patch.object(subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, out, b'')):
            self.assertEqual(tracks.probe('https://x'), [{'track': 'audio', 'language': 'fre', 'title': None},
                                                          {'track': 'subtitle', 'language': 'eng', 'title': 'Forced'}])


if __name__ == '__main__':
    unittest.main()
