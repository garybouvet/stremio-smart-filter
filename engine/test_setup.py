"""Déballage du paquet de données sur un autre PC (engine.setup_data)."""
import os, tempfile, unittest, zipfile
from . import setup_data


def archive(folder, names):
    path = os.path.join(folder, 'paquet.zip')
    with zipfile.ZipFile(path, 'w') as z:
        for name in names:
            z.writestr(name, 'x')
    return path


class Unpack(unittest.TestCase):
    def test_complete_package_lands_in_data(self):
        with tempfile.TemporaryDirectory() as d:
            data = os.path.join(d, 'data')
            names = setup_data.unpack(archive(d, ['tmdb.db', 'extras.db', 'fini-harvest.txt']), data)
            self.assertEqual(names, ['extras.db', 'fini-harvest.txt', 'tmdb.db'])
            self.assertTrue(os.path.exists(os.path.join(data, 'tmdb.db')))

    def test_incomplete_package_refused(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                setup_data.unpack(archive(d, ['tmdb.db']), os.path.join(d, 'data'))

    def test_path_outside_data_refused(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                setup_data.unpack(archive(d, ['tmdb.db', 'extras.db', '../evil.txt']), os.path.join(d, 'data'))
            self.assertFalse(os.path.exists(os.path.join(d, 'evil.txt')))


if __name__ == '__main__':
    unittest.main()
