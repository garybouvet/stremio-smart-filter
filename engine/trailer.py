"""Bande-annonce d'un titre, en français quand elle existe : VF, puis VOSTFR, puis l'anglais.

Mesuré le 25/11/2026 chez TMDB : une bande-annonce française pour 46 films connus sur 60, 22 films récents sur 60,
et 18 séries sur 40 (11 sur 40 avec un autre échantillon). Les vidéos par saison n'en ajoutent presque pas.
"""
import re, urllib.error, urllib.request

KINDS = ('Trailer', 'Teaser')
VOST = re.compile(r'\bvo(?:st(?:fr)?)?\b|sous[- ]titr', re.I)
VF = re.compile(r'\bv\.?f\.?\b|\bfran[cç]ais', re.I)
OEMBED = 'https://www.youtube.com/oembed?format=json&url=https://www.youtube.com/watch?v='
TRIES = 3


def rank(video, original):
    lang = video.get('iso_639_1') or (original if original == 'fr' else None)  # sans langue : celle du film s'il est français
    name = video.get('name') or ''
    return (lang != 'fr', bool(lang == 'fr' and VOST.search(name)), video.get('type') != 'Trailer',
            not (lang == 'fr' and VF.search(name)), lang != 'en', not video.get('official'))


def playable(key):
    """Vidéo encore en ligne et lisible hors de YouTube. Sans réponse : on tente quand même."""
    try:
        urllib.request.urlopen(OEMBED + key, timeout=4).close()
    except urllib.error.HTTPError as e:
        return e.code not in (400, 401, 403, 404)
    except OSError:
        return True
    return True


def choose(videos, original=None):
    """(numéro YouTube, langue 'fr' ou autre), ou (None, None)."""
    wanted = [v for v in videos if v.get('site') == 'YouTube' and v.get('type') in KINDS and re.fullmatch(r'[\w-]{6,20}', v.get('key') or '')]
    wanted.sort(key=lambda v: rank(v, original))
    for v in wanted[:TRIES]:
        if playable(v['key']):
            return v['key'], 'fr' if not rank(v, original)[0] else v.get('iso_639_1')
    return None, None
