"""Addon Stremio « Filtres » : catalogues Films et Séries avec des menus cumulables dans Découvrir.

Stremio affiche un menu (choix unique) par « extra » qui a des options ; ils se cumulent dans la même requête.
Les libellés sont en français ; on les traduit ici en filtres du moteur (search.parse).
"""
import datetime
from . import search

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
VOTES = {'1 000+': '1000', '10 000+': '10000', '50 000+': '50000', '100 000+': '100000', '500 000+': '500000'}
DUREES = {'Moins de 90 min': ('', '89'), '90 à 120 min': ('90', '120'), '120 à 150 min': ('120', '150'),
          'Plus de 150 min': ('151', '')}
TRIS = {'Meilleure note': 'rating', 'Popularité': 'votes', 'Plus récents': 'year', 'Plus anciens': 'year_asc'}
# Tris par d'autres notes : proposés seulement si la base a ces notes (MDBList, TMDB).
TRIS_NOTES = {'Moyenne des notes': ('average', None), 'Rotten Tomatoes': ('tomatoes', 'tomatoes'),
              'Metacritic': ('metacritic', 'metacritic'), 'Letterboxd': ('letterboxd', 'letterboxd'),
              'Trakt': ('trakt', 'trakt'), 'Note TMDB': ('tmdb', 'tmdb')}
PAGE = 100
MAX_PLACES = 30  # les plateformes les plus fournies : un menu plus long est illisible à la télécommande


def decades():
    now = datetime.date.today().year // 10 * 10
    return {f'Années {d}': (str(d), str(d + 9)) for d in range(now, 1940, -10)} | {'Avant 1950': ('', '1949')}


def manifest(options):
    """options : search.options(db), pour ne proposer que les langues et pays présents dans les données."""
    langs = [LANGS_FR[c] for c in options['languages'] if c in LANGS_FR]
    countries = [COUNTRIES_FR[c] for c in options['countries'] if c in COUNTRIES_FR]
    places = options.get('places', [])[:MAX_PLACES]
    scores = set(options.get('scores', []))
    tris = list(TRIS) + [name for name, (_, source) in TRIS_NOTES.items() if source is None and scores or source in scores]
    genres = list(GENRES_FR)
    extra = [{'name': 'genre', 'options': genres}, {'name': 'Note', 'options': list(NOTES)},
             {'name': 'Décennie', 'options': list(decades())}, {'name': 'Genre 2', 'options': genres},
             {'name': 'Exclure', 'options': genres}, {'name': 'Votes', 'options': list(VOTES)},
             {'name': 'Durée', 'options': list(DUREES)}, {'name': 'Tri', 'options': tris}]
    if places:
        extra.append({'name': 'Plateforme', 'options': places})
    if langs:
        extra.append({'name': 'Langue', 'options': langs})
    if countries:
        extra += [{'name': 'Pays', 'options': countries}, {'name': 'Sans le pays', 'options': countries}]
    extra.append({'name': 'skip'})
    return {
        'id': 'local.stremio-custom.filtres', 'version': '1.1.0', 'name': 'Filtres',
        'description': 'Films et séries filtrés par note IMDb, votes, décennie, genres, plateforme, langue, pays '
                       '(ou sans un pays), durée ; tri par note pondérée, autres notes, popularité ou date.',
        'resources': ['catalog'], 'types': ['movie', 'series'], 'idPrefixes': ['tt'],
        'catalogs': [{'type': t, 'id': 'filtres', 'name': 'Filtres', 'extra': extra} for t in ('movie', 'series')],
        'behaviorHints': {'configurable': False},
    }


def to_query(typ, extra):
    """Extras Stremio (dict libellé -> valeur) -> paramètres du moteur. Valeur inconnue : ValueError."""
    inv = {v: k for k, v in LANGS_FR.items()}, {v: k for k, v in COUNTRIES_FR.items()}
    # « known » : sans les titres confidentiels (moins de 100 votes, sur aucune plateforme), comme le panneau par défaut.
    q = {'type': [typ], 'limit': [str(PAGE)], 'skip': [extra.get('skip', '0')], 'known': ['1']}
    pick = lambda table, key: table[extra[key]] if key in extra else None
    if 'Note' in extra:
        q['rating_min'] = [pick(NOTES, 'Note')]
    if 'Votes' in extra:
        q['votes_min'] = [pick(VOTES, 'Votes')]
    if 'Décennie' in extra:
        q['year_min'], q['year_max'] = [[v] for v in decades()[extra['Décennie']]]
    if 'Durée' in extra:
        q['runtime_min'], q['runtime_max'] = [[v] for v in DUREES[extra['Durée']]]
    if 'Tri' in extra:
        q['sort'] = [TRIS[extra['Tri']] if extra['Tri'] in TRIS else TRIS_NOTES[extra['Tri']][0]]
    if 'Plateforme' in extra:
        q['place'] = [extra['Plateforme']]
    wanted = [GENRES_FR[extra[k]] for k in ('genre', 'Genre 2') if k in extra]
    if wanted:
        q['genres_all'] = [','.join(wanted)]
    if 'Exclure' in extra:
        q['genres_none'] = [GENRES_FR[extra['Exclure']]]
    if 'Langue' in extra:
        q['language'] = [inv[0][extra['Langue']]]
    if 'Pays' in extra:
        q['country'] = [inv[1][extra['Pays']]]
    if 'Sans le pays' in extra:
        q['country_not'] = [inv[1][extra['Sans le pays']]]
    return q


def catalog(db, typ, extra):
    try:
        f = search.parse(to_query(typ, extra))
    except KeyError as e:
        raise ValueError(f'option inconnue : {e}') from e
    return search.search(db, f)
