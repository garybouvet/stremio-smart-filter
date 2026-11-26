"""Modes « Ce catalogue » et « Toutes les sources » : lit les catalogues des addons et ne garde que ce qui passe les filtres."""
import concurrent.futures as cf, ipaddress, json, re, socket, sys, time, urllib.parse, urllib.request
from . import tmdb
from .addon_filtres import GENRES_FR
from .imdb_index import GENRES, genre_mask
from .search import lookup
from .settings import setting

TTL = 3600
MAX_PAGES = 20
SOURCE_PAGES = 5  # par catalogue en mode « Toutes les sources » : ce que l'addon met en avant, pas tout son fonds
MAX_SOURCES = 60  # chaque catalogue coûte des requêtes sortantes : borne fixée par le serveur, pas par le navigateur
WORKERS = 16
TMDB_ID = re.compile(r'^tmdb(?:-dice)?:(\d+)$')
RUNTIME = re.compile(r'(?:(\d+)\s*h)?\s*(?:(\d+)\s*min)?')
# Les addons nomment les genres chacun à sa façon : « Drame », « Science Fiction »…
GENRE_NAMES = {g.lower(): g for g in GENRES} | {k.lower(): v for k, v in GENRES_FR.items()} | {'science fiction': 'Sci-Fi'}
TIMEOUT = 10
BUDGET = 8  # secondes pour commencer de nouvelles pages : une source lente n'attarde pas les autres, le cache complète ensuite
RETRY = 300  # une page en panne n'est pas redemandée avant ce délai : chaque essai bloquerait le résultat jusqu'à TIMEOUT
_cache = {}  # url -> (horodatage, metas)
_down = {}  # url -> horodatage de la dernière panne


def addon_base(transport_url):
    u = urllib.parse.urlsplit(transport_url or '')
    if u.scheme not in ('http', 'https') or not u.path.endswith('/manifest.json'):
        raise ValueError('adresse d\'addon invalide')
    if setting('PUBLIC') == '1' and not public_host(u.hostname):
        raise ValueError('adresse d\'addon interne refusée')
    return transport_url[:-len('/manifest.json')]


def public_host(host):
    """Sur le serveur, l'adresse vient du navigateur : refuser le réseau interne (SSRF : métadonnées Oracle, Docker…).
    shortcut: vérifié à la résolution, pas après redirection ni re-résolution DNS ; l'accès reste réservé au jeton."""
    try:
        addrs = {i[4][0] for i in socket.getaddrinfo(host, None)}
    except (OSError, UnicodeError):
        return False
    return bool(addrs) and all(ipaddress.ip_address(a.split('%')[0]).is_global for a in addrs)


def fetch_page(base, typ, cid, skip, extra=()):
    extra = list(extra) + ([('skip', skip)] if skip else [])
    url = (f'{base}/catalog/{typ}/{urllib.parse.quote(cid)}'
           + (f'/{urllib.parse.urlencode(extra, quote_via=urllib.parse.quote)}' if extra else '') + '.json')
    hit = _cache.get(url)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    if time.time() - _down.get(url, 0) < RETRY:
        raise OSError('source en panne')
    req = urllib.request.Request(url, headers={'User-Agent': 'stremio-custom'})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            metas = json.load(r).get('metas') or []
    except OSError:
        _down[url] = time.time()
        raise
    if len(_cache) > 5000:  # shortcut: cache vidé d'un bloc, passer à un LRU si la mémoire gêne
        _cache.clear()
        _down.clear()
    _cache[url] = (time.time(), metas)
    return metas


def imdb_id(m, typ):
    """Identifiant IMDb d'un titre d'addon : TMDB le donne dans `imdb_id`, TMDB Dice oblige à demander à TMDB."""
    for v in (m.get('id'), m.get('imdb_id')):
        if isinstance(v, str) and v.startswith('tt'):
            return v
    hit = TMDB_ID.match(str(m.get('id')))
    return tmdb.imdb_of(typ, hit[1]) if hit else None


def identified(metas, typ):
    """Titres avec un identifiant IMDb, sans doublon ; les autres (fichiers Real-Debrid, messages d'erreur) sont écartés."""
    with cf.ThreadPoolExecutor(WORKERS) as ex:
        ids = list(ex.map(lambda m: imdb_id(m, typ), metas))
    seen = {}
    for tt, m in zip(ids, metas):
        if tt:
            seen.setdefault(tt, {**m, 'id': tt})
    return list(seen.values())


def row_of(m, typ):
    """Ce que l'addon sait d'un titre, pour ceux que l'index IMDb n'a pas (spéciaux TV, sorties récentes). Colonnes de titles."""
    year = re.match(r'\d{4}', str(m.get('year') or m.get('releaseInfo') or ''))
    run = RUNTIME.fullmatch(str(m.get('runtime') or '').strip())
    try:
        rating = float(m.get('imdbRating'))
    except (TypeError, ValueError):
        rating = None
    return (m['id'], typ, m.get('name'), int(year[0]) if year else None,
            (int(run[1] or 0) * 60 + int(run[2] or 0) or None) if run else None,
            genre_mask(GENRE_NAMES.get(str(g).lower()) for g in m.get('genres') or m.get('genre') or []), rating, None)


def kept(db, metas, f, ranked=False):
    """Titres d'addons qui passent les filtres, avec les affiches et textes de l'addon. ranked : triés selon f."""
    metas = identified(metas, f['type'])
    by_id = {m['id']: m for m in metas}
    if any(f.get(k) for k in ('language', 'language_not', 'country', 'country_not', 'unknown_country')):
        tmdb.complete(db, list(by_id))
    hits = lookup(db, [row_of(m, f['type']) for m in metas], f, ranked)
    return [{**hits[i], **{k: v for k, v in by_id[i].items() if v not in (None, '', [])},
             'imdbRating': hits[i]['imdbRating'], 'votes': hits[i]['votes']} for i in (hits if ranked else by_id) if i in hits]


def filtered(db, base, cid, f, start=0, want=50, extra=()):
    """Renvoie (metas retenues, position suivante ou None si le catalogue est épuisé).

    extra : filtres propres à l'addon (ex. [('genre', 'Action')]), transmis tels quels."""
    out, skip = [], start
    # shortcut: pages lues l'une après l'autre (~0,3 s chacune), paralléliser si c'est trop lent
    for _ in range(MAX_PAGES):
        try:
            metas = fetch_page(base, f['type'], cid, skip, extra)
        except OSError:  # addon en panne en cours de route : on garde ce qui est déjà trouvé
            if out:
                return out, None
            raise
        if not metas:
            return out, None
        out += kept(db, metas, f)
        skip += len(metas)
        if len(out) >= want:
            break
    return out, skip


def sources_of(raw):
    """Paramètre `sources` du navigateur, {adresse d'addon: [[catalogue, extra], ...]} -> [(base, catalogue, extra)]."""
    out = []
    try:
        for url, cats in json.loads(raw).items():
            try:
                base = addon_base(url)
            except ValueError:  # addon local ou interne : les autres restent utilisables
                continue
            out += [(base, str(cid), [(k, v) for k, v in urllib.parse.parse_qsl(str(extra)) if k != 'skip']) for cid, extra in cats]
    except (AttributeError, TypeError) as e:
        raise ValueError('sources invalides') from e
    if not out or len(out) > MAX_SOURCES:
        raise ValueError('nombre de sources invalide')
    return out


def everywhere(db, sources, f):
    """Toutes les sources réunies, sans doublon, filtrées et triées. Renvoie (metas, position suivante ou None)."""
    deadline = time.time() + BUDGET

    def read(source):
        base, cid, extra = source
        metas, skip = [], 0
        try:
            for _ in range(SOURCE_PAGES):
                page = fetch_page(base, f['type'], cid, skip, extra) if time.time() < deadline else None
                if not page:
                    break
                metas += page
                skip += len(page)
        except Exception as e:  # une source en panne ne prive pas des autres ; jamais son adresse dans le journal (clés)
            sys.stderr.write(f'source {cid} indisponible : {type(e).__name__}\n')
        return metas

    with cf.ThreadPoolExecutor(WORKERS) as ex:
        metas = [m for page in ex.map(read, sources) for m in page]
    out = kept(db, metas, f, ranked=True)
    return out, f['skip'] + len(out) if len(out) == f['limit'] else None
