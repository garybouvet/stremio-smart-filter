"""Base data/extras.db : ce qui s'ajoute à l'index IMDb, rempli en tâche de fond (harvest, tmdb_all, playable).

extra : titres hors index (mêmes colonnes que titles) ; merged : parmi eux, ceux que l'index a sous un autre numéro ;
presence : catalogues d'addons où se trouve un titre ; offers : plateformes d'abonnement ou gratuites en France ; posters : affiches à préférer ; ratings : notes d'autres sources ; playable : langues des liens trouvés, en cache ou non.
"""
import json, os, re, sqlite3
from .imdb_index import DATA

EXTRAS_DB = os.path.join(DATA, 'extras.db')
ADDONS = os.path.join(DATA, 'addons.json')  # adresses des addons (avec leurs clés) : data/ n'est jamais commité
# Même plateforme, noms différents selon l'addon ou TMDB.
ALIASES = {'Disney Plus': 'Disney+', 'Amazon Prime Video': 'Prime Video', 'Prime  Video': 'Prime Video',
           'Apple TV Plus': 'Apple TV+', 'Apple TV': 'Apple TV+', 'Max': 'HBO Max',
           'Netflix Standard with Ads': 'Netflix', 'Amazon Prime Video with Ads': 'Prime Video',
           'Paramount Plus': 'Paramount+', 'Paramount Plus Premium': 'Paramount+'}
RESOLD = re.compile(r' (?:Amazon|Apple TV) Channel$')  # la même offre, vendue par un autre


def place_name(name):
    name = RESOLD.sub('', ' '.join(name.split()))
    return ALIASES.get(name, name)


def create(db, schema='main'):
    for sql in ('CREATE TABLE IF NOT EXISTS {s}.extra (id TEXT PRIMARY KEY, type TEXT, name TEXT, year INT,'
                ' runtime INT, genres INT, rating REAL, votes INT)',
                'CREATE TABLE IF NOT EXISTS {s}.presence (id TEXT, place TEXT, PRIMARY KEY (id, place)) WITHOUT ROWID',
                'CREATE INDEX IF NOT EXISTS {s}.ix_place ON presence (place)',
                'CREATE TABLE IF NOT EXISTS {s}.offers (id TEXT, place TEXT, kind TEXT, PRIMARY KEY (id, place)) WITHOUT ROWID',
                'CREATE INDEX IF NOT EXISTS {s}.ix_offer ON offers (place)',
                'CREATE TABLE IF NOT EXISTS {s}.merged (old TEXT PRIMARY KEY, new TEXT) WITHOUT ROWID',
                'CREATE TABLE IF NOT EXISTS {s}.posters (id TEXT PRIMARY KEY, poster TEXT) WITHOUT ROWID',
                'CREATE TABLE IF NOT EXISTS {s}.ratings (id TEXT, source TEXT, value REAL, PRIMARY KEY (id, source)) WITHOUT ROWID',
                'CREATE INDEX IF NOT EXISTS {s}.ix_score ON ratings (source, value)',
                'CREATE TABLE IF NOT EXISTS {s}.playable (id TEXT, lang TEXT, cached INT, PRIMARY KEY (id, lang, cached)) WITHOUT ROWID',
                'CREATE INDEX IF NOT EXISTS {s}.ix_link ON playable (lang, cached)',
                'CREATE TABLE IF NOT EXISTS {s}.checked (id TEXT PRIMARY KEY) WITHOUT ROWID',
                'CREATE TABLE IF NOT EXISTS {s}.checked_at (id TEXT PRIMARY KEY, at INT) WITHOUT ROWID',
                'CREATE TABLE IF NOT EXISTS {s}.unlinked (id TEXT PRIMARY KEY) WITHOUT ROWID'):
        db.execute(sql.format(s=schema))


def open_db():
    db = sqlite3.connect(EXTRAS_DB, timeout=60, check_same_thread=False)
    create(db)
    return db


def remember(urls):
    """Adresses vues dans le panneau : l'aspiration suit les addons du compte sans liste à tenir à jour."""
    known, urls = set(addons()), set(urls)
    if not urls <= known:
        with open(ADDONS, 'w', encoding='utf-8') as f:
            json.dump(sorted(known | urls), f)


def addons():
    if not os.path.exists(ADDONS):
        return []
    with open(ADDONS, encoding='utf-8') as f:
        return json.load(f)
