"""Filtres à plusieurs choix : pays, langues originales, plateformes, à inclure (l'un d'eux) ou à exclure (aucun),
et la bibliothèque de l'utilisateur (titres vus, sa liste), dont l'interface envoie les identifiants."""
import re

MAX_CHOICES = 60
MAX_IDS = 5000
# Langue parlée surtout dans un seul pays : elle donne le pays d'un titre dont l'origine est inconnue.
# Pas l'anglais, l'espagnol, l'arabe, le bengali ou le pendjabi : plusieurs pays.
LANG_COUNTRY = {
    'hi': 'IN', 'ta': 'IN', 'te': 'IN', 'ml': 'IN', 'kn': 'IN', 'mr': 'IN', 'gu': 'IN', 'or': 'IN', 'as': 'IN',
    'ko': 'KR', 'ja': 'JP', 'th': 'TH', 'tr': 'TR', 'vi': 'VN', 'id': 'ID', 'tl': 'PH', 'fa': 'IR', 'he': 'IL',
    'pl': 'PL', 'cs': 'CZ', 'hu': 'HU', 'ro': 'RO', 'el': 'GR', 'uk': 'UA', 'sv': 'SE', 'fi': 'FI', 'da': 'DK',
    'no': 'NO', 'nb': 'NO', 'is': 'IS', 'et': 'EE', 'lv': 'LV', 'lt': 'LT', 'ka': 'GE', 'hy': 'AM', 'km': 'KH',
    'my': 'MM', 'si': 'LK', 'ne': 'NP', 'ur': 'PK',
}
TITLE_ID = re.compile(r'^(tt\d+|tmdb:\d+)$')


def values(q, key, pattern, size):
    """Valeurs d'un paramètre, répété ou séparé par des virgules. Lève ValueError si l'une est invalide."""
    split = pattern is not None or key.endswith('_ids') or key == 'seeds'
    found = [v.strip() for raw in q.get(key, []) for v in (raw.split(',') if split else [raw]) if v.strip()]
    if len(found) > size or any(pattern and not re.fullmatch(pattern, v) for v in found) or any(len(v) > 80 for v in found):
        raise ValueError(f'{key} invalide')
    return list(dict.fromkeys(found))


def parse(q, typ):
    f = {k: values(q, k, r'[A-Z]{2}', MAX_CHOICES) for k in ('country', 'country_not')}
    f |= {k: values(q, k, r'[a-z]{2,3}', MAX_CHOICES) for k in ('language', 'language_not')}
    f |= {k: values(q, k, None, MAX_CHOICES) for k in ('place', 'place_not')}
    f['unknown_country'] = q.get('unknown_country', [''])[0] == 'hide'
    empty = q.get('only_ids') == ['none']  # « Ma liste seulement » avec une liste vide : aucun titre
    for k in ('exclude_ids', 'only_ids'):
        # Une bibliothèque contient aussi des chaînes TV, des vidéos YouTube… : ces identifiants-là sont ignorés.
        ids = [] if k == 'only_ids' and empty else [i for i in values(q, k, None, MAX_IDS) if TITLE_ID.fullmatch(i)]
        # Stremio nomme tmdb:N une série que la base range sous tmdb:tv:N (voir search.to_meta).
        f[k] = [i.replace('tmdb:', 'tmdb:tv:') if typ == 'series' and i.startswith('tmdb:') else i for i in ids]
    if empty:
        f['only_ids'] = ['']
    return f


def marks(items):
    return ','.join('?' * len(items))


def from_countries(codes):
    """Titres de l'un de ces pays : connu par TMDB ou Wikidata, sinon deviné par la langue."""
    langs = [lang for lang, country in LANG_COUNTRY.items() if country in codes]
    sql = ' OR '.join('countries LIKE ?' for _ in codes)
    args = [f'%,{c},%' for c in codes]
    if langs:
        sql += f' OR (countries IS NULL AND lang IN ({marks(langs)}))'
        args += langs
    return f'SELECT id FROM tmdb.meta WHERE {sql}', args


def clauses(f):
    sql, args = [], []

    def add(clause, more):
        sql.append(clause)
        args.extend(more)

    if f.get('country'):
        sub, more = from_countries(f['country'])
        add(f'titles.id IN ({sub})', more)
    if f.get('country_not'):
        sub, more = from_countries(f['country_not'])
        add(f'titles.id NOT IN ({sub})', more)
    if f.get('unknown_country'):
        # Recherche par titre (clé primaire) : la liste des 1,3 million de fiches situées serait trop longue à bâtir.
        add('EXISTS (SELECT 1 FROM tmdb.meta k WHERE k.id = titles.id AND (k.countries IS NOT NULL'
            f' OR k.lang IN ({marks(LANG_COUNTRY)})))', list(LANG_COUNTRY))
    if f.get('language'):
        add(f'titles.id IN (SELECT id FROM tmdb.meta WHERE lang IN ({marks(f["language"])}))', f['language'])
    if f.get('language_not'):
        add(f'titles.id NOT IN (SELECT id FROM tmdb.meta WHERE lang IN ({marks(f["language_not"])}))', f['language_not'])
    if f.get('place'):
        add(f'titles.id IN (SELECT id FROM h.offers WHERE place IN ({marks(f["place"])}))', f['place'])
    if f.get('place_not'):
        add(f'titles.id NOT IN (SELECT id FROM h.offers WHERE place IN ({marks(f["place_not"])}))', f['place_not'])
    if f.get('exclude_ids'):
        add(f'titles.id NOT IN ({marks(f["exclude_ids"])})', f['exclude_ids'])
    if f.get('only_ids'):
        add(f'titles.id IN ({marks(f["only_ids"])})', f['only_ids'])
    return sql, args
