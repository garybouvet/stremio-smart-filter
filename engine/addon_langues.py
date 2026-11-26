"""Addon Stremio « Langues » : regroupe les liens de tes addons de flux (LANGUES_SOURCES dans .env),
les classe par langue (sûr, possible, reste) et écrit un badge dans le nom de chaque lien.

Les pistes réelles des meilleurs liens en cache sont vérifiées en arrière-plan (tracks.py) :
le badge « ✓ » apparaît à la réouverture du film.
"""
import concurrent.futures as cf, json, os, threading, time, urllib.parse, urllib.request
from . import stream_languages as sl, tracks
from .settings import setting

_pool = cf.ThreadPoolExecutor(8)

# Le menu des liens de Stremio a une ligne par addon, et masque ceux qui ne renvoient rien :
# un addon par langue donne un vrai menu des langues disponibles pour chaque film.
AUDIO = {'fr': 'français', 'en': 'anglais', 'es': 'espagnol', 'it': 'italien', 'de': 'allemand', 'ja': 'japonais', 'ko': 'coréen'}
SUBS = {'fr': 'français', 'en': 'anglais'}
VARIANTS = {f'audio-{c}': ('audio', c, f'Audio {n}') for c, n in AUDIO.items()} | \
           {f'subs-{c}': ('subs', c, f'Sous-titres {n}') for c, n in SUBS.items()}
SHARED_SECONDS = 120
_recent = {}
_recent_lock = threading.Lock()


def sources():
    return [u for u in setting('LANGUES_SOURCES', '').split() if u.endswith('/manifest.json')]


def manifest():
    return {
        'id': 'local.stremio-custom.langues', 'version': '1.0.0', 'name': 'Langues',
        'description': f"Liens de tes addons classés par langue ({setting('LANGUES_LANG', 'fr').upper()} d'abord), "
                       'avec badge VF / VOSTFR / MULTi / ✓ pistes vérifiées.',
        'resources': ['stream'], 'types': ['movie', 'series'], 'idPrefixes': ['tt'], 'catalogs': [],
        'behaviorHints': {'configurable': False},
    }


def fetch(manifest_url, typ, vid):
    base = manifest_url[:-len('/manifest.json')]
    req = urllib.request.Request(f'{base}/stream/{typ}/{urllib.parse.quote(vid, safe=":")}.json', headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r).get('streams') or []
    except (OSError, ValueError):
        return []  # source en panne : les autres répondent quand même


def gather(typ, vid):
    return [s for batch in _pool.map(lambda u: fetch(u, typ, vid), sources()) for s in batch]


def shared(typ, vid):
    """gather une seule fois par film : Stremio appelle tous les addons de langue en même temps."""
    key, now = (typ, vid), time.monotonic()
    with _recent_lock:
        hit = _recent.get(key)
        mine = not hit or now - hit[0] > SHARED_SECONDS
        if mine:
            if len(_recent) > 200:  # shortcut: purge brutale, remplacer par un LRU si beaucoup d'utilisateurs
                _recent.clear()
            hit = _recent[key] = (now, cf.Future())
    if mine:
        try:
            hit[1].set_result(gather(typ, vid))
        except Exception as e:
            with _recent_lock:
                _recent.pop(key, None)
            hit[1].set_exception(e)
    return hit[1].result()


def rank(stream, d, lang):
    a, s = sl.audio_match(d, lang), sl.subs_match(d, lang)
    if a == 'sure':
        return 0 if d.verified else 1
    if a == 'maybe':
        return 2
    if s == 'sure':
        return 3  # VOSTFR : utile, mais après tout ce qui a l'audio voulu
    return 4 if s == 'maybe' else 5


def streams(typ, vid):
    lang = setting('LANGUES_LANG', 'fr')
    strict = setting('LANGUES_MODE', 'trier') == 'filtrer'
    found = gather(typ, vid)
    checked = tracks.known([s['url'] for s in found if sl.is_cached_debrid(s)])
    scored = []
    for i, s in enumerate(found):
        d = sl.from_tracks(checked[s['url']]) if s.get('url') in checked else sl.detect(s)
        # Dans une même langue, les liens en cache (lecture immédiate) avant ceux à télécharger (⏳).
        scored.append((rank(s, d, lang), not sl.is_cached_debrid(s), i, s, d))
    scored.sort(key=lambda x: x[:3])
    # Vérifie en arrière-plan les meilleurs candidats en cache, pas encore vérifiés.
    # LANGUES_VERIFY=0 sur un serveur : Real-Debrid verrait une 2e adresse IP sur le compte.
    per_title = int(setting('LANGUES_VERIFY', '8'))
    tracks.verify_later([s['url'] for r, _, _, s, d in scored if r <= 2 and not d.verified and sl.is_cached_debrid(s)][:per_title])
    out = []
    for r, _, _, s, d in scored:
        if strict and r == 5:
            continue
        b = sl.badge(d, lang)
        out.append({**s, 'name': f"{b}\n{s.get('name', '')}" if b else s.get('name', '')})
    return out


def language_manifest(code):
    name = VARIANTS[code][2]
    return {
        'id': f'local.stremio-custom.{code}', 'version': '1.0.0', 'name': name,
        'description': f'Liens de tes addons : {name.lower()}. « ? » = langue probable, pas certaine.',
        'resources': ['stream'], 'types': ['movie', 'series'], 'idPrefixes': ['tt'], 'catalogs': [],
        'behaviorHints': {'configurable': False},
    }


def offered(m, d, lang):
    # MULTi sans drapeau : français ou anglais en pratique ; sinon le coréen serait « disponible » partout.
    return m is not None and not (m == 'maybe' and lang not in d.flags and lang not in ('fr', 'en'))


def language_streams(code, typ, vid):
    """Liens de cette langue : vérifiés, sûrs, puis probables (« ? ») ; en cache d'abord à chaque niveau."""
    kind, lang, _ = VARIANTS[code]
    match = sl.audio_match if kind == 'audio' else sl.subs_match
    found = shared(typ, vid)
    checked = tracks.known([s['url'] for s in found if sl.is_cached_debrid(s)])
    kept = []
    for i, s in enumerate(found):
        d = sl.from_tracks(checked[s['url']]) if s.get('url') in checked else sl.detect(s)
        m = match(d, lang)
        if not offered(m, d, lang):
            continue
        kept.append(((m == 'maybe', not d.verified, not sl.is_cached_debrid(s), i), s, d, m))
    out = []
    for _, s, d, m in sorted(kept, key=lambda k: k[0]):
        b = sl.badge(d, lang) or ''
        if m == 'maybe' and kind == 'subs':
            b = f'ST {lang.upper()} ?'
        elif m == 'maybe' and '?' not in b:
            b = f'{b} ?'.strip()
        out.append({**s, 'name': f"{b}\n{s.get('name', '')}" if b else s.get('name', '')})
    return out
