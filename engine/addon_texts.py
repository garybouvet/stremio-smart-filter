"""Textes de l'addon « Filtres » dans chaque langue proposée (une variante d'addon par langue : filtres, filtres-en…).

Genres, pays et langues hors français : addon_names.json, fabriqué par deploy/noms-addon.js.
Le français garde exactement les libellés d'origine : l'addon déjà installé sur le compte continue de marcher.
"""
import json, os

LANGS = ('fr', 'en', 'es', 'pt', 'de', 'it')

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'addon_names.json'), encoding='utf-8') as _f:
    NAMES = json.load(_f)

TEXTS = {
    'fr': {
        'name': 'Filtres',
        'description': 'Films et séries filtrés par note IMDb, votes, décennie, genres, plateforme, langue, pays '
                       '(ou sans un pays), durée ; tri par note pondérée, autres notes, popularité ou date.',
        'menus': {'note': 'Note', 'decade': 'Décennie', 'genre2': 'Genre 2', 'exclude': 'Exclure', 'votes': 'Votes',
                  'runtime': 'Durée', 'sort': 'Tri', 'place': 'Plateforme', 'language': 'Langue', 'country': 'Pays',
                  'country_not': 'Sans le pays'},
        'decade': 'Années {}', 'before': 'Avant 1950', 'thousands': ' ',
        'runtimes': ('Moins de 90 min', '90 à 120 min', '120 à 150 min', 'Plus de 150 min'),
        'sorts': {'rating': 'Meilleure note', 'votes': 'Popularité', 'year': 'Plus récents', 'year_asc': 'Plus anciens',
                  'average': 'Moyenne des notes', 'tmdb': 'Note TMDB'},
    },
    'en': {
        'name': 'Filters',
        'description': 'Movies and series filtered by IMDb rating, votes, decade, genres, platform, language, country '
                       '(or excluding one), runtime; sorted by weighted rating, other scores, popularity or date.',
        'menus': {'note': 'Rating', 'decade': 'Decade', 'genre2': 'Genre 2', 'exclude': 'Exclude', 'votes': 'Votes',
                  'runtime': 'Runtime', 'sort': 'Sort', 'place': 'Platform', 'language': 'Language', 'country': 'Country',
                  'country_not': 'Not from'},
        'decade': '{}s', 'before': 'Before 1950', 'thousands': ',',
        'runtimes': ('Under 90 min', '90 to 120 min', '120 to 150 min', 'Over 150 min'),
        'sorts': {'rating': 'Best rated', 'votes': 'Most popular', 'year': 'Newest', 'year_asc': 'Oldest',
                  'average': 'Average score', 'tmdb': 'TMDB score'},
    },
    'es': {
        'name': 'Filtros',
        'description': 'Películas y series filtradas por nota IMDb, votos, década, géneros, plataforma, idioma, país '
                       '(o sin un país), duración; orden por nota ponderada, otras notas, popularidad o fecha.',
        'menus': {'note': 'Nota', 'decade': 'Década', 'genre2': 'Género 2', 'exclude': 'Excluir', 'votes': 'Votos',
                  'runtime': 'Duración', 'sort': 'Orden', 'place': 'Plataforma', 'language': 'Idioma', 'country': 'País',
                  'country_not': 'Sin el país'},
        'decade': 'Años {}', 'before': 'Antes de 1950', 'thousands': '.',
        'runtimes': ('Menos de 90 min', 'De 90 a 120 min', 'De 120 a 150 min', 'Más de 150 min'),
        'sorts': {'rating': 'Mejor nota', 'votes': 'Más populares', 'year': 'Más recientes', 'year_asc': 'Más antiguos',
                  'average': 'Nota media', 'tmdb': 'Nota TMDB'},
    },
    'pt': {
        'name': 'Filtros',
        'description': 'Filmes e séries filtrados por nota IMDb, votos, década, gêneros, plataforma, idioma, país '
                       '(ou sem um país), duração; ordem por nota ponderada, outras notas, popularidade ou data.',
        'menus': {'note': 'Nota', 'decade': 'Década', 'genre2': 'Gênero 2', 'exclude': 'Excluir', 'votes': 'Votos',
                  'runtime': 'Duração', 'sort': 'Ordem', 'place': 'Plataforma', 'language': 'Idioma', 'country': 'País',
                  'country_not': 'Sem o país'},
        'decade': 'Anos {}', 'before': 'Antes de 1950', 'thousands': '.',
        'runtimes': ('Menos de 90 min', 'De 90 a 120 min', 'De 120 a 150 min', 'Mais de 150 min'),
        'sorts': {'rating': 'Melhor nota', 'votes': 'Mais populares', 'year': 'Mais recentes', 'year_asc': 'Mais antigos',
                  'average': 'Nota média', 'tmdb': 'Nota TMDB'},
    },
    'de': {
        'name': 'Filter',
        'description': 'Filme und Serien gefiltert nach IMDb-Bewertung, Stimmen, Jahrzehnt, Genres, Plattform, Sprache, Land '
                       '(oder ohne ein Land), Laufzeit; sortiert nach gewichteter Bewertung, anderen Bewertungen, Beliebtheit oder Datum.',
        'menus': {'note': 'Bewertung', 'decade': 'Jahrzehnt', 'genre2': 'Genre 2', 'exclude': 'Ausschließen', 'votes': 'Stimmen',
                  'runtime': 'Laufzeit', 'sort': 'Sortierung', 'place': 'Plattform', 'language': 'Sprache', 'country': 'Land',
                  'country_not': 'Ohne Land'},
        'decade': '{}er', 'before': 'Vor 1950', 'thousands': '.',
        'runtimes': ('Unter 90 Min.', '90 bis 120 Min.', '120 bis 150 Min.', 'Über 150 Min.'),
        'sorts': {'rating': 'Beste Bewertung', 'votes': 'Am beliebtesten', 'year': 'Neueste', 'year_asc': 'Älteste',
                  'average': 'Durchschnittsbewertung', 'tmdb': 'TMDB-Bewertung'},
    },
    'it': {
        'name': 'Filtri',
        'description': 'Film e serie filtrati per voto IMDb, voti, decennio, generi, piattaforma, lingua, paese '
                       '(o senza un paese), durata; ordine per voto ponderato, altri voti, popolarità o data.',
        'menus': {'note': 'Voto', 'decade': 'Decennio', 'genre2': 'Genere 2', 'exclude': 'Escludi', 'votes': 'Voti',
                  'runtime': 'Durata', 'sort': 'Ordine', 'place': 'Piattaforma', 'language': 'Lingua', 'country': 'Paese',
                  'country_not': 'Senza il paese'},
        'decade': 'Anni {}', 'before': 'Prima del 1950', 'thousands': '.',
        'runtimes': ('Meno di 90 min', 'Da 90 a 120 min', 'Da 120 a 150 min', 'Più di 150 min'),
        'sorts': {'rating': 'Miglior voto', 'votes': 'Più popolari', 'year': 'Più recenti', 'year_asc': 'Meno recenti',
                  'average': 'Voto medio', 'tmdb': 'Voto TMDB'},
    },
}
