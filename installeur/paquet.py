"""Fabrique le paquet de données à joindre à une Release : tmdb.db et extras.db, sans rien de personnel.

Usage : uv run python installeur/paquet.py [dossier de sortie, défaut tmp/paquet]
Les bases sont copiées par la sauvegarde SQLite : data/ n'est que lu, même si des tâches de fond y écrivent.
Pas les données IMDb (leur licence interdit de les redistribuer) : chaque PC les télécharge et construit son index.
Retirés : le cache « Pour toi » (vient de la bibliothèque), tracks.db, addons.json (adresses avec clés).
"""
import datetime, hashlib, os, sqlite3, sys, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
SHARED = {'tmdb.db': ['reco'], 'extras.db': []}  # base -> tables personnelles à vider
DONE = ('tmdb', 'harvest', 'mdblist')  # la prochaine relecture complète part de la date du paquet


def copy(name, drop, out):
    target = os.path.join(out, name)
    if os.path.exists(target):
        os.remove(target)
    src = sqlite3.connect(f'file:{os.path.join(DATA, name)}?mode=ro', uri=True)
    dst = sqlite3.connect(target)
    src.backup(dst)
    src.close()
    for table in drop:
        dst.execute(f'DROP TABLE IF EXISTS {table}')
    dst.commit()
    dst.execute('VACUUM')
    dst.close()
    return target


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def build(out):
    os.makedirs(out, exist_ok=True)
    day = datetime.date.today().isoformat()
    archive = os.path.join(out, f'donnees-{day}.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_LZMA) as z:
        for name, drop in SHARED.items():
            db = copy(name, drop, out)
            z.write(db, name)
            os.remove(db)
            print(name, 'ajoutée', flush=True)
        for task in DONE:
            z.writestr(f'fini-{task}.txt', day)
    digest = sha256(archive)
    with open(archive + '.sha256', 'w', encoding='ascii') as f:
        f.write(f'{digest}  {os.path.basename(archive)}\n')
    return archive, digest


if __name__ == '__main__':
    path, digest = build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'tmp', 'paquet'))
    print(path, f'{os.path.getsize(path) / 1e6:.0f} Mo', digest)
