"""Langues d'un lien, devinées depuis son texte (les addons n'ont aucun champ « langue »).

Même règles que l'interface (stremio-web/.../LanguageFilter/streamLanguages.js), mêmes cas de test.
Règles par source, mesurées avec ffprobe sur de vrais fichiers (2026-11-05) :
- MediaFusion, « 🌐 English + French » : langues audio (5 sur 5).
- Torrentio, « Multi Audio / 🇬🇧 / 🇫🇷 » : drapeaux = audio (5 sur 5).
- Torrentio, drapeaux seuls : le premier est l'audio, les suivants des sous-titres (6 sur 6).
sûr = mot explicite ou ligne ci-dessus ; incertain = MULTi sans détail, ou premier drapeau.
"""
import re

FLAGS = {
    'GB': 'en', 'US': 'en', 'FR': 'fr', 'BE': 'fr', 'CA': 'fr', 'ES': 'es', 'MX': 'es', 'IT': 'it', 'DE': 'de',
    'PT': 'pt', 'BR': 'pt', 'JP': 'ja', 'KR': 'ko', 'CN': 'zh', 'TW': 'zh', 'RU': 'ru', 'UA': 'uk', 'PL': 'pl',
    'NL': 'nl', 'IN': 'hi', 'TR': 'tr', 'SA': 'ar', 'SE': 'sv', 'NO': 'no', 'DK': 'da', 'FI': 'fi', 'CZ': 'cs',
    'HU': 'hu', 'GR': 'el', 'IL': 'he', 'TH': 'th', 'VN': 'vi',
}
NAMES = {
    'english': 'en', 'french': 'fr', 'spanish': 'es', 'latino': 'es', 'italian': 'it', 'german': 'de',
    'portuguese': 'pt', 'japanese': 'ja', 'korean': 'ko', 'chinese': 'zh', 'russian': 'ru', 'ukrainian': 'uk',
    'polish': 'pl', 'dutch': 'nl', 'hindi': 'hi', 'turkish': 'tr', 'arabic': 'ar', 'swedish': 'sv',
    'norwegian': 'no', 'danish': 'da', 'finnish': 'fi', 'czech': 'cs', 'hungarian': 'hu', 'greek': 'el',
    'hebrew': 'he', 'thai': 'th', 'vietnamese': 'vi',
}
ISO3 = {
    'fre': 'fr', 'fra': 'fr', 'eng': 'en', 'spa': 'es', 'ita': 'it', 'ger': 'de', 'deu': 'de', 'por': 'pt',
    'jpn': 'ja', 'kor': 'ko', 'chi': 'zh', 'zho': 'zh', 'rus': 'ru', 'ukr': 'uk', 'pol': 'pl', 'dut': 'nl',
    'nld': 'nl', 'hin': 'hi', 'tur': 'tr', 'ara': 'ar', 'swe': 'sv', 'nor': 'no', 'nob': 'no', 'dan': 'da',
    'fin': 'fi', 'cze': 'cs', 'ces': 'cs', 'hun': 'hu', 'gre': 'el', 'ell': 'el', 'heb': 'he', 'tha': 'th',
    'vie': 'vi',
}
# « Sub Eng-Arabic-French » : liste de langues après « Sub » = sous-titres, pas audio.
SUBS_FR = re.compile(r'\b(VOSTFR|VOST|SUBFRENCH|STFR|ST[ ._-]FR|SUB(?:S|TITLES?)?[ ._:-]+(?:[a-z]{2,}[ ._,/-]+){0,6}?(?:FR|FRE|FRENCH)|FRENCH[ ._-]?SUBS?)\b', re.I)
AUDIO_FR = re.compile(r'\b(TRUEFRENCH|FRENCH|VFF|VFQ|VFI|VF2|VF|VOF|FRA|FRE|FR)\b', re.I)
AUDIO_EN = re.compile(r'\b(ENG|ENGLISH|EN|VO)\b', re.I)
SUBS_HINT = re.compile(r'\bsubs?\b|subtitles?|napisy|multi[ ._-]?subs|\bmsubs\b', re.I)
# « Multi Subs » = plusieurs sous-titres, pas plusieurs pistes audio.
MULTI = re.compile(r'\bMULTI(?![ ._-]?SUBS?\b)(?:[ ._-]?AUDIO|[ ._-]?LANG)?\b', re.I)
FLAG = re.compile('([\U0001F1E6-\U0001F1FF])([\U0001F1E6-\U0001F1FF])')
AUDIO_LINE = re.compile(r'^(?:multi|dual)[ ._-]?audio\b.*$', re.I | re.M)
# Codes de sortie (« Eng Fr Spa », « MULTi.KOR ») ; pas les noms entiers : « The Italian Job » n'est pas en italien.
AUDIO_CODES = {'es': re.compile(r'\b(SPA|ESP)\b', re.I), 'it': re.compile(r'\bITA\b', re.I), 'de': re.compile(r'\b(GER|DEU)\b', re.I),
               'ja': re.compile(r'\bJPN\b', re.I), 'ko': re.compile(r'\bKOR\b', re.I)}
CACHED = re.compile(r'\[RD\+\]|⚡')


class Langs:
    def __init__(self, audio=(), subs=(), flags=(), multi=False, subs_hint=False, verified=False):
        self.audio, self.subs, self.flags = set(audio), set(subs), set(flags)
        self.first = next(iter(flags), None) if isinstance(flags, list) else None
        self.multi, self.subs_hint, self.verified = multi, subs_hint, verified


def text_of(stream):
    return f"{stream.get('name') or ''}\n{stream.get('title') or stream.get('description') or ''}"


def flags_in(text):
    regions = (chr(ord(a) - 0x1F1E6 + 65) + chr(ord(b) - 0x1F1E6 + 65) for a, b in FLAG.findall(text))
    return [FLAGS[r] for r in regions if r in FLAGS]


def detect(stream):
    text = text_of(stream)
    d = Langs(flags=flags_in(text), multi=bool(MULTI.search(text)), subs_hint=bool(SUBS_HINT.search(text)))
    if SUBS_FR.search(text):
        d.subs.add('fr')
    without_subs = SUBS_FR.sub(' ', text)  # « VOSTFR » contient « FR »
    if AUDIO_FR.search(without_subs):
        d.audio.add('fr')
    if AUDIO_EN.search(without_subs):
        d.audio.add('en')
    listed = re.search(r'🌐\s*([^\n]+)', text)  # MediaFusion : « 🌐 English + French »
    if listed:
        d.audio |= {NAMES[s.strip().lower()] for s in re.split(r'[+,/|]', listed.group(1)) if s.strip().lower() in NAMES}
    line = AUDIO_LINE.search(text)
    if line:
        d.audio |= set(flags_in(line.group(0)))
    if not d.subs_hint:
        d.audio |= {lang for lang, code in AUDIO_CODES.items() if code.search(without_subs)}
    return d


def track_lang(track):
    code, title = track.get('language'), track.get('title') or ''
    if code in ISO3:
        return ISO3[code]
    if isinstance(code, str) and len(code) == 2:
        return code
    if re.search(r'french|fran[cç]ais|\bvf[fqi2]?\b|truefrench', title, re.I):
        return 'fr'
    if re.search(r'english|anglais', title, re.I):
        return 'en'
    return None


def from_tracks(tracks):
    pick = lambda kind: {l for t in tracks if t.get('track') == kind and (l := track_lang(t))}
    return Langs(audio=pick('audio'), subs=pick('subtitle'), verified=True)


def audio_match(d, lang):
    if lang in d.audio:
        return 'sure'
    if d.verified:
        return None
    # MULTi sans détail : l'anglais est souvent omis des drapeaux.
    if d.multi and (not d.flags or lang == 'en' or lang in d.flags):
        return 'maybe'
    # Sortie qui annonce des sous-titres : ses drapeaux sont ceux des sous-titres, pas de l'audio.
    if lang == d.first and lang not in d.subs and not d.subs_hint:
        return 'maybe'
    return None


def subs_match(d, lang):
    if lang in d.subs:
        return 'sure'
    if d.verified:
        return None
    if lang in d.flags and lang not in d.audio:
        return 'maybe'
    return None


def badge(d, lang='fr'):
    up = lang.upper()
    if d.verified:
        audio = ' '.join(l.upper() for l in sorted(d.audio, key=lambda l: (l != lang, l))) or '?'
        return f'✓ {audio}' + (f' · ST {up}' if lang in d.subs else '')
    if lang in d.subs and lang not in d.audio:
        return 'VOSTFR' if lang == 'fr' else f'ST {up}'
    if lang in d.audio:
        return 'VF' if lang == 'fr' else up
    if d.multi:
        return 'MULTi'
    if lang in d.flags:
        return f'ST {up} ?' if d.subs_hint or lang != d.first else f'{up} ?'
    return None


def is_cached_debrid(stream):
    return bool(CACHED.search(text_of(stream))) and str(stream.get('url', '')).startswith('http')
