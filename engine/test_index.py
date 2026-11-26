"""uv run python -m unittest engine.test_index : mise à jour de l'index et protection du relais."""
import contextlib, io, os, sqlite3, tempfile, unittest
from . import extras
from .imdb_index import fresh, install, prune_extras
from .proxy import foreign


def base(path, names):
    d = sqlite3.connect(path)
    d.execute('CREATE TABLE titles (id TEXT PRIMARY KEY)')
    d.executemany('INSERT INTO titles VALUES (?)', [(n,) for n in names])
    d.commit()
    return d


class Install(unittest.TestCase):
    def test_index_is_refreshed_while_a_task_keeps_it_open(self):
        with tempfile.TemporaryDirectory() as folder:
            live = os.path.join(folder, 'index.db')
            base(live, ['tt1']).close()
            task = sqlite3.connect(':memory:')  # comme tmdb_all : l'index reste attaché des heures
            task.execute('ATTACH DATABASE ? AS idx', (live,))
            self.assertEqual(task.execute('SELECT id FROM idx.titles').fetchall(), [('tt1',)])
            new = base(os.path.join(folder, 'new.db'), ['tt1', 'tt2'])
            install(new, live)
            new.close()
            self.assertEqual(task.execute('SELECT COUNT(*) FROM idx.titles').fetchone(), (2,))
            task.close()

    def test_weekly(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'index.db')
            self.assertFalse(fresh(path))
            open(path, 'w').close()
            self.assertTrue(fresh(path))
            os.utime(path, (0, 0))
            self.assertFalse(fresh(path))


class Pruned(unittest.TestCase):
    def test_refreshed_index_takes_over_extra_titles(self):
        with tempfile.TemporaryDirectory() as folder:
            index, path = os.path.join(folder, 'index.db'), os.path.join(folder, 'extras.db')
            base(index, ['tt1']).close()
            e = sqlite3.connect(path)
            extras.create(e)
            e.executemany('INSERT INTO extra VALUES (?,?,?,NULL,NULL,0,NULL,NULL)',
                          [('tt1', 'series', 'Déjà indexé'), ('tt2', 'series', 'Hors index'), ('tt3', 'movie', None)])
            e.commit()
            e.close()
            with contextlib.redirect_stdout(io.StringIO()):
                prune_extras(path, index)
            e = sqlite3.connect(path)
            self.assertEqual(e.execute('SELECT id FROM extra').fetchall(), [('tt2',)])
            e.close()


class Worker(unittest.TestCase):
    def test_local_interface_is_never_kept_in_cache(self):
        import threading, urllib.request
        from http.server import ThreadingHTTPServer
        from unittest import mock
        from . import server
        front = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        threading.Thread(target=front.serve_forever, daemon=True).start()
        try:
            with mock.patch('sys.stderr'), mock.patch.object(server, 'PUBLIC', False):
                r = urllib.request.urlopen(f'http://127.0.0.1:{front.server_address[1]}/service-worker.js')
                body = r.read()
            self.assertIn('javascript', r.headers['Content-Type'])
            self.assertEqual(r.headers['Cache-Control'], 'no-cache')
            self.assertIn(b'unregister', body)
            self.assertNotIn(b'precache', body)
        finally:
            front.shutdown()
            front.server_close()


class Relay(unittest.TestCase):
    def test_only_the_interface_and_the_player_pass(self):
        ok = {'Host': '127.0.0.1:11480'}
        for headers in (ok, {**ok, 'Sec-Fetch-Site': 'same-origin'}, {**ok, 'Origin': 'http://127.0.0.1:11480'}):
            self.assertFalse(foreign(headers, 11480), headers)
        for headers in ({**ok, 'Origin': 'https://exemple.com'}, {**ok, 'Sec-Fetch-Site': 'cross-site'}, {**ok, 'Origin': 'null'},
                        {**ok, 'Sec-Fetch-Site': 'same-site'}, {'Host': 'piege.com:11480'}, {}):
            self.assertTrue(foreign(headers, 11480), headers)


if __name__ == '__main__':
    unittest.main()
