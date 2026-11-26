"""Pistes réelles (audio, sous-titres) d'un lien Real-Debrid en cache, lues par ffprobe sur l'en-tête du fichier.

Résultats gardés dans data/tracks.db. Effet de bord, comme une lecture : le torrent s'ajoute à la liste Real-Debrid.
Les sous-titres en fichiers séparés dans le torrent ne sont pas vus (seules les pistes intégrées le sont).
"""
import concurrent.futures as cf, hashlib, json, os, re, sqlite3, subprocess, threading, time
from .imdb_index import DATA

TRACKS_DB = os.path.join(DATA, 'tracks.db')
FFPROBE = os.environ.get('FFPROBE') or os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'Stremio', 'ffprobe.exe')
_pool = cf.ThreadPoolExecutor(2)
_running = set()
_lock = threading.Lock()


def key_of(url):
    # Hash du torrent + nom du fichier quand l'adresse les contient (stable même si la clé change), sinon empreinte.
    m = re.search(r'([0-9a-fA-F]{40})', url)
    if m:
        return f'{m.group(1).lower()}:{url.rstrip("/").rsplit("/", 1)[-1]}'
    return hashlib.sha256(url.encode()).hexdigest()


def _db():
    db = sqlite3.connect(TRACKS_DB, timeout=10)
    db.execute('CREATE TABLE IF NOT EXISTS tracks (key TEXT PRIMARY KEY, tracks TEXT, at REAL)')
    return db


def known(urls):
    """{url: pistes} pour les liens déjà vérifiés."""
    keys = {key_of(u): u for u in urls}
    if not keys:
        return {}
    db = _db()
    try:
        rows = db.execute(f'SELECT key, tracks FROM tracks WHERE key IN ({",".join("?" * len(keys))})', list(keys)).fetchall()
    finally:
        db.close()
    return {keys[k]: json.loads(t) for k, t in rows}


def probe(url, timeout=25):
    out = subprocess.run([FFPROBE, '-v', 'error', '-print_format', 'json', '-show_streams', url],
                         capture_output=True, timeout=timeout, check=True).stdout
    kinds = {'audio': 'audio', 'subtitle': 'subtitle'}
    return [{'track': kinds[s['codec_type']], 'language': (s.get('tags') or {}).get('language'),
             'title': (s.get('tags') or {}).get('title')}
            for s in json.loads(out).get('streams', []) if s.get('codec_type') in kinds]


def _probe_and_store(url):
    try:
        found = probe(url)
        db = _db()
        try:
            db.execute('INSERT OR REPLACE INTO tracks VALUES (?,?,?)', (key_of(url), json.dumps(found), time.time()))
            db.commit()
        finally:
            db.close()
    except (subprocess.SubprocessError, OSError, ValueError):
        pass  # lien expiré, fichier illisible : il reste non vérifié et sera retenté à la prochaine ouverture
    finally:
        with _lock:
            _running.discard(url)


def verify_later(urls):
    """Lance en arrière-plan la vérification des liens pas encore connus ni en cours."""
    if not os.path.exists(FFPROBE):
        return
    with _lock:
        todo = [u for u in urls if u not in _running]
        _running.update(todo)
    for u in todo:
        _pool.submit(_probe_and_store, u)
