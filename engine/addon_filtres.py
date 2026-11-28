"""Addon Stremio « Filtres » : catalogues Films et Séries avec des menus cumulables dans Découvrir.

Stremio affiche un menu (choix unique) par « extra » qui a des options ; ils se cumulent dans la même requête.
Une variante par langue (filtres, filtres-en…, voir addon_texts) : menus, options et titres dans cette langue.
Les libellés reçus sont traduits ici en filtres du moteur (search.parse).
"""
import datetime, functools
from . import search
from .addon_texts import NAMES, TEXTS

GENRES_FR = {
    'Action': 'Action', 'Aventure': 'Adventure', 'Animation': 'Animation', 'Biographie': 'Biography',
    'Comédie': 'Comedy', 'Comédie musicale': 'Musical', 'Documentaire': 'Documentary', 'Drame': 'Drama',
    'Famille': 'Family', 'Fantastique': 'Fantasy', 'Film noir': 'Film-Noir', 'Guerre': 'War',
    'Histoire': 'History', 'Horreur': 'Horror', 'Musique': 'Music', 'Mystère': 'Mystery', 'Policier': 'Crime',
    'Romance': 'Romance', 'Science-fiction': 'Sci-Fi', 'Sport': 'Sport', 'Thriller': 'Thriller', 'Western': 'Western',
}
LANGS_FR = {
    'en': 'Anglais', 'fr': 'Français', 'es': 'Espagnol', 'it': 'Italien', 'de': 'Allemand', 'ja': 'Japonais',
    'ko': 'Coréen', 'zh': 'Chinois', 'cn': 'Cantonais', 'hi': 'Hindi', 'ta': 'Tamoul', 'te': 'Télougou',
    'ml': 'Malayalam', 'tr': 'Turc', 'ru': 'Russe', 'pt': 'Portugais', 'sv': 'Suédois', 'da': 'Danois',
    'no': 'Norvégien', 'fi': 'Finnois', 'nl': 'Néerlandais', 'pl': 'Polonais', 'fa': 'Persan', 'ar': 'Arabe',
    'th': 'Thaï', 'he': 'Hébreu', 'el': 'Grec', 'cs': 'Tchèque', 'hu': 'Hongrois', 'id': 'Indonésien',
}
COUNTRIES_FR = {
    'US': 'États-Unis', 'GB': 'Royaume-Uni', 'FR': 'France', 'IN': 'Inde', 'JP': 'Japon', 'CA': 'Canada',
    'DE': 'Allemagne', 'KR': 'Corée du Sud', 'IT': 'Italie', 'ES': 'Espagne', 'AU': 'Australie', 'TR': 'Turquie',
    'CN': 'Chine', 'HK': 'Hong Kong', 'BE': 'Belgique', 'SE': 'Suède', 'DK': 'Danemark', 'NO': 'Norvège',
    'MX': 'Mexique', 'BR': 'Brésil', 'AR': 'Argentine', 'IE': 'Irlande', 'NZ': 'Nouvelle-Zélande',
    'CH': 'Suisse', 'NL': 'Pays-Bas', 'PL': 'Pologne', 'RU': 'Russie', 'IR': 'Iran', 'TW': 'Taïwan',
    'TH': 'Thaïlande', 'FI': 'Finlande', 'AT': 'Autriche', 'IL': 'Israël', 'ZA': 'Afrique du Sud',
}
NOTES = {f'{n}+': n for n in ('9', '8.5', '8', '7.5', '7', '6.5', '6', '5')}
VOTE_VALUES = ('1000', '10000', '50000', '100000', '500000')
RUNTIMES = (('', '89'), ('90', '120'), ('120', '150'), ('151', ''))
# Tris par d'autres notes : proposés seulement si la base a ces notes (MDBList, TMDB). Libellé traduit ou nom du site.
NOTE_SORTS = (('average', None), ('tomatoes', 'tomatoes'), ('metacritic', 'metacritic'), ('letterboxd', 'letterboxd'),
              ('trakt', 'trakt'), ('tmdb', 'tmdb'))
SITES = {'tomatoes': 'Rotten Tomatoes', 'metacritic': 'Metacritic', 'letterboxd': 'Letterboxd', 'trakt': 'Trakt'}
PAGE = 100
MAX_PLACES = 30  # les plateformes les plus fournies : un menu plus long est illisible à la télécommande


@functools.lru_cache(maxsize=None)
def tables(lang):
    """Libellés de chaque menu dans cette langue : {libellé: valeur du moteur}."""
    T = TEXTS[lang]
    if lang == 'fr':
        genres, languages, countries = GENRES_FR, LANGS_FR, COUNTRIES_FR
    else:
        names = NAMES[lang]
        genres = dict(sorted((names['genres'][g], g) for g in GENRES_FR.values()))
        languages, countries = names['languages'], names['countries']
    return {
        'genres': genres,
        'languages': {name: code for code, name in languages.items()}, 'language_order': list(languages.values()),
        'countries': {name: code for code, name in countries.items()}, 'country_order': list(countries.values()),
        'language_names': languages, 'country_names': countries,
        'votes': {f'{int(v):,}'.replace(',', T['thousands']) + '+': v for v in VOTE_VALUES},
        'runtimes': dict(zip(T['runtimes'], RUNTIMES)),
        'sorts': {T['sorts'][k]: k for k in ('rating', 'votes', 'year', 'year_asc')},
        'note_sorts': {T['sorts'].get(k) or SITES[k]: (k, source) for k, source in NOTE_SORTS},
    }


def decades(lang='fr'):
    T = TEXTS[lang]
    now = datetime.date.today().year // 10 * 10
    return {T['decade'].format(d): (str(d), str(d + 9)) for d in range(now, 1940, -10)} | {T['before']: ('', '1949')}


def manifest(options, lang='fr'):
    """options : search.options(db), pour ne proposer que les langues et pays présents dans les données."""
    T, t, M = TEXTS[lang], tables(lang), TEXTS[lang]['menus']
    langs = [t['language_names'][c] for c in options['languages'] if c in t['language_names']]
    countries = [t['country_names'][c] for c in options['countries'] if c in t['country_names']]
    places = options.get('places', [])[:MAX_PLACES]
    scores = set(options.get('scores', []))
    sorts = list(t['sorts']) + [name for name, (_, source) in t['note_sorts'].items() if source is None and scores or source in scores]
    genres = list(t['genres'])
    extra = [{'name': 'genre', 'options': genres}, {'name': M['note'], 'options': list(NOTES)},
             {'name': M['decade'], 'options': list(decades(lang))}, {'name': M['genre2'], 'options': genres},
             {'name': M['exclude'], 'options': genres}, {'name': M['votes'], 'options': list(t['votes'])},
             {'name': M['runtime'], 'options': list(t['runtimes'])}, {'name': M['sort'], 'options': sorts}]
    if places:
        extra.append({'name': M['place'], 'options': places})
    if langs:
        extra.append({'name': M['language'], 'options': langs})
    if countries:
        extra += [{'name': M['country'], 'options': countries}, {'name': M['country_not'], 'options': countries}]
    extra.append({'name': 'skip'})
    return {
        # Le français garde l'identifiant d'origine : l'addon déjà installé reste le même.
        'id': 'local.stremio-custom.filtres' + ('' if lang == 'fr' else f'.{lang}'), 'version': '1.2.0', 'name': T['name'],
        'description': T['description'],
        'resources': ['catalog'], 'types': ['movie', 'series'], 'idPrefixes': ['tt'],
        'catalogs': [{'type': ty, 'id': 'filtres', 'name': T['name'], 'extra': extra} for ty in ('movie', 'series')],
        'behaviorHints': {'configurable': False},
    }


def to_query(typ, extra, lang='fr'):
    """Extras Stremio (dict libellé -> valeur) -> paramètres du moteur. Valeur inconnue : KeyError (ValueError dans catalog)."""
    t, M = tables(lang), TEXTS[lang]['menus']
    # « known » : sans les titres confidentiels (moins de 100 votes, sur aucune plateforme), comme le panneau par défaut.
    q = {'type': [typ], 'limit': [str(PAGE)], 'skip': [extra.get('skip', '0')], 'known': ['1'], 'lang': [lang]}
    if M['note'] in extra:
        q['rating_min'] = [NOTES[extra[M['note']]]]
    if M['votes'] in extra:
        q['votes_min'] = [t['votes'][extra[M['votes']]]]
    if M['decade'] in extra:
        q['year_min'], q['year_max'] = [[v] for v in decades(lang)[extra[M['decade']]]]
    if M['runtime'] in extra:
        q['runtime_min'], q['runtime_max'] = [[v] for v in t['runtimes'][extra[M['runtime']]]]
    if M['sort'] in extra:
        label = extra[M['sort']]
        q['sort'] = [t['sorts'][label] if label in t['sorts'] else t['note_sorts'][label][0]]
    if M['place'] in extra:
        q['place'] = [extra[M['place']]]
    wanted = [t['genres'][extra[k]] for k in ('genre', M['genre2']) if k in extra]
    if wanted:
        q['genres_all'] = [','.join(wanted)]
    if M['exclude'] in extra:
        q['genres_none'] = [t['genres'][extra[M['exclude']]]]
    if M['language'] in extra:
        q['language'] = [t['languages'][extra[M['language']]]]
    if M['country'] in extra:
        q['country'] = [t['countries'][extra[M['country']]]]
    if M['country_not'] in extra:
        q['country_not'] = [t['countries'][extra[M['country_not']]]]
    return q


def catalog(db, typ, extra, lang='fr'):
    try:
        f = search.parse(to_query(typ, extra, lang))
    except KeyError as e:
        raise ValueError(f'option inconnue : {e}') from e
    return search.search(db, f)
