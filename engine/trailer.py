"""Bandes-annonces d'un titre, une par langue : celle de l'interface de Stremio d'abord, puis l'anglais et le français.

En français : la VF avant la VOSTFR. Une vidéo sans langue est dans la langue du film.
Mesuré le 25/11/2026 chez TMDB : une bande-annonce française pour 46 films connus sur 60, 22 films récents sur 60,
et 18 séries sur 40 (11 sur 40 avec un autre échantillon). Les vidéos par saison n'en ajoutent presque pas.
"""
import re, urllib.error, urllib.request

KINDS = ('Trailer', 'Teaser')
VOST = re.compile(r'\bvo(?:st(?:fr)?)?\b|sous[- ]titr', re.I)
VF = re.compile(r'\bv\.?f\.?\b|\bfran[cç]ais', re.I)
KEY = re.compile(r'[\w-]{6,20}')
OEMBED = 'https://www.youtube.com/oembed?format=json&url=https://www.youtube.com/watch?v='
TRIES = 3


def language(video, original):
    return video.get('iso_639_1') or original


def label(video, original):
    """Pastille affichée à côté du bouton : FR, VOSTFR, EN…"""
    lang = language(video, original)
    if lang == 'fr' and VOST.search(video.get('name') or ''):
        return 'VOSTFR'
    return (lang or '?').upper()


def rank(video, lang):
    """Entre deux vidéos de la même langue : doublée avant sous-titrée, bande-annonce avant teaser, VF annoncée, officielle."""
    name = video.get('name') or ''
    return (lang == 'fr' and bool(VOST.search(name)), video.get('type') != 'Trailer',
            not (lang == 'fr' and VF.search(name)), not video.get('official'))


def playable(key):
    """Vidéo encore en ligne et lisible hors de YouTube. Sans réponse : on tente quand même."""
    try:
        urllib.request.urlopen(OEMBED + key, timeout=4).close()
    except urllib.error.HTTPError as e:
        return e.code not in (400, 401, 403, 404)
    except OSError:
        return True
    return True


def choose_all(videos, original=None, wanted=('fr', 'en')):
    """[{key, lang, label}] : la meilleure bande-annonce encore en ligne de chaque langue voulue, dans cet ordre."""
    usable = [v for v in videos if v.get('site') == 'YouTube' and v.get('type') in KINDS and KEY.fullmatch(v.get('key') or '')]
    found = []
    for lang in dict.fromkeys(wanted):
        same = sorted((v for v in usable if language(v, original) == lang), key=lambda v: rank(v, lang))
        for v in same[:TRIES]:
            if playable(v['key']):
                found.append({'key': v['key'], 'lang': lang, 'label': label(v, original)})
                break
    return found


def choose(videos, original=None):
    """(numéro YouTube, langue) : en français si elle existe, sinon en anglais ; (None, None) sinon."""
    found = choose_all(videos, original, ('fr', 'en'))
    return (found[0]['key'], found[0]['lang']) if found else (None, None)
