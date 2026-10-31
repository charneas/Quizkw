"""Reconnaissance d'une même chanson entre les playlists d'une partie.

Retour utilisateur (2026-10-31) : "les gens qui ont la même chanson dans une
partie doivent être bien taggés". Une même chanson arrive sous des formes très
différentes selon la source : Deezer donne un titre et un artiste propres,
YouTube un titre de vidéo libre et le nom d'une chaîne qui n'est pas forcément
l'artiste. `group_songs` regroupe donc les morceaux d'une partie en chansons,
du signal le plus sûr au plus tolérant :

1. même `youtube_video_id` ou même ISRC (toujours fusionnés) ;
2. même titre normalisé et artistes compatibles ;
3. mêmes mots dans "artiste + titre", quel que soit l'ordre ("Daft Punk Get
   Lucky", "Get Lucky by Daft Punk") ;
4. titre identique, artiste invérifiable (chaîne YouTube) et durée quasi égale ;
5. titre presque identique (faute de frappe) chez un même artiste.

Un titre identique ne suffit jamais à lui seul : "Hello" d'Adele et celui de
Lionel Richie restent deux chansons. Un live, une version acoustique, un
remaster ou un radio edit sont la même chanson ; un remix, une reprise, un
instrumental, un karaoké, un nightcore ou une version accélérée/ralentie n'en
sont pas (décision produit, cf. spec-blindtest-song-matching-owners.md).

Module pur, sans DB ni réseau. Distinct de `cache.normalize_key` (clés déjà
stockées, à ne pas changer) et de `text_cleanup` (texte affiché) : tout ce qui
est calculé ici sert uniquement à comparer, jamais à afficher."""
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
from itertools import combinations
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

_MAX_DURATION_GAP_SECONDS = 2
_MIN_DURATION_MATCH_TITLE_CHARS = 8
_MIN_FUZZY_TITLE_CHARS = 10
_FUZZY_TITLE_RATIO = 0.93
_FUZZY_PREFIX_CHARS = 3
_FUZZY_ARTIST_RATIO = 0.88
_MIN_FUZZY_ARTIST_CHARS = 5
_MIN_SUBSET_ARTIST_CHARS = 4
_MIN_CREDIT_CHARS = 3
_MIN_TITLE_ONLY_BAG_WORDS = 3
_FIRST_NON_LATIN_CHAR = "ɐ"

_CHAR_REPLACEMENTS = str.maketrans({
    "œ": "oe", "æ": "ae", "ø": "o", "ł": "l", "đ": "d", "ð": "d", "þ": "th",
    "×": " x ", "&": " and ", "+": " and ", "_": " ",
})
_APOSTROPHES_RE = re.compile(r"['’‘`´]")
_DROPPED_G_RE = re.compile(r"(?<=\win)['’‘`´](?=\s|$)")
_INNER_BANG_RE = re.compile(r"(?<=\w)!(?=\w)")
_INNER_DOLLAR_RE = re.compile(r"(?<=\w)\$|\$(?=\w)")
_ACRONYM_RE = re.compile(r"\b(?:\w\.){2,}")
_WORD_RE = re.compile(r"\w+")

_AND_WORDS = {"and", "et", "n"}
_NUMBERED_WORDS = {"part", "volume", "chapter"}
_WORD_ALIASES = {"pt": "part", "pts": "part", "vol": "volume", "ch": "chapter"}
_NUMBER_ALIASES = {
    "i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8", "ix": "9", "x": "10",
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8",
    "nine": "9", "ten": "10",
}
# Mots de liaison ignorés quand on compare les mots sans tenir compte de leur
# ordre ("Get Lucky by Daft Punk").
_BAG_STOPWORDS = {"by", "de", "par", "from"}

_BRACKET_RE = re.compile(r"[(\[{（【]([^()\[\]{}（）【】]*)[)\]}）】]")
_SEGMENT_SEP_RE = re.compile(r"\s+[-–—|:~]+\s+|\s*//\s*")
_FEAT_RE = re.compile(r"\b(?:feat|ft|featuring|prod)\b.*$", re.IGNORECASE)
_LEADING_CREDIT_RE = re.compile(r"^\s*(?:feat|ft|featuring|with|avec|prod)\b", re.IGNORECASE)
_PART_GROUP_RE = re.compile(r"^\s*(?:part|pt|pts|vol|volume|chapter)\b\.?\s*\S+\s*$", re.IGNORECASE)

# Version qui change réellement ce qu'on entend : jamais fusionnée avec
# l'original. Testé avant `_SAME_SONG_RE` : "Acoustic Cover" est une reprise.
_DISTINCT_VERSION_RE = re.compile(
    r"\b(remix|rmx|cover|instrumental|karaoke|nightcore|sped\s*up|speed\s*up|slowed|mashup|bootleg|"
    r"reprise\s+de|tribute)\b",
    re.IGNORECASE,
)
# Mention sans effet sur l'identité de la chanson : version du même morceau ou
# habillage de la vidéo. Testée sur TOUS les mots de la mention, jamais sur un
# seul : "Radio Edit" en est une, "Radio Ga Ga" ou "Stereo Hearts" sont de vrais
# titres, à conserver après "Queen - ".
_VERSION_WORDS = {
    "official", "officiel", "officielle", "music", "video", "clip", "audio", "lyric", "lyrics", "parole", "paroles",
    "visualizer", "visualiser", "hd", "hq", "uhd", "4k", "live", "unplugged", "acoustic", "acoustique", "session",
    "sessions", "remaster", "remastered", "remasterise", "remasterisee", "radio", "edit", "version", "mono", "stereo",
    "explicit", "clean", "deluxe", "bonus", "track", "extended", "original", "album", "single", "ost", "soundtrack",
}
# Seuls ces mots font une mention à eux seuls : "Rammstein - Radio" est un titre.
_LONE_VERSION_WORDS = {
    "live", "unplugged", "acoustic", "acoustique", "remaster", "remastered", "mono", "stereo", "explicit", "clean",
    "deluxe", "lyrics", "paroles", "audio", "hd", "hq", "4k",
}
_RESOLUTION_RE = re.compile(r"\d{3,4}p")
_LIVE_PLACE_RE = re.compile(r"^\s*live\s+(?:at|from|a|au|à|@)", re.IGNORECASE)
# Entre parenthèses, le contexte est clair : formes plus libres, qu'on ne peut
# pas appliquer après un tiret ("Beatles - From Me to You").
_BRACKET_ONLY_MENTION_RE = re.compile(
    r"^\s*(?:live|from|recorded|en\s+concert|bande\s+originale|b\.?o\.?)"
    r"|(?:remaster|remastered|unplugged|version|edit|session|sessions|live|soundtrack|ost)\s*$",
    re.IGNORECASE,
)
# En fin de titre et sans parenthèses, uniquement des expressions complètes :
# un mot isolé comme "music" ou "video" peut appartenir au titre ("Thank You
# for the Music").
_TRAILING_JUNK_RE = re.compile(
    r"(?:\s+(?:official(?:\s+(?:music|lyrics?|hd))?\s+(?:video|audio|visuali[sz]er)|music\s+video|lyrics?\s+video|"
    r"video\s+clip|clip\s+(?:officiel|video)|with\s+lyrics|lyrics|paroles|hd|hq|4k|\d{3,4}p))+\s*$",
    re.IGNORECASE,
)

_ARTIST_SPLIT_RE = re.compile(
    r"\s*[,;/]\s*|\s+(?:and|x|with|avec|vs|versus|feat|ft|featuring)\s+", re.IGNORECASE
)
_CHANNEL_WORDS = {"official", "officiel", "vevo", "topic", "channel", "tv"}
_CHANNEL_SUFFIXES = ("official", "officiel", "music", "tv", "channel", "band")


@dataclass(frozen=True)
class SongTrack:
    """Ce dont `group_songs` a besoin d'un `Track`. `structured` vaut `True`
    si le titre et l'artiste viennent de champs fiables (Deezer) et `False`
    pour une vidéo YouTube, dont l'artiste est le nom d'une chaîne."""
    id: int
    title: str
    artist: str
    isrc: Optional[str] = None
    youtube_video_id: Optional[str] = None
    duration_seconds: Optional[int] = None
    structured: bool = True


@dataclass(frozen=True)
class _Artist:
    whole: str
    tokens: Tuple[str, ...]
    credits: frozenset
    credit_tokens: Tuple[Tuple[str, ...], ...]


@dataclass(frozen=True)
class _Reading:
    """Une interprétation possible d'un morceau en (titre, artiste)."""
    full: Tuple[str, ...]
    base: Tuple[str, ...]
    variants: frozenset
    artist: _Artist


def _strip_latin_accents(text: str) -> Iterable[str]:
    """Retire les accents des lettres latines uniquement : ailleurs, la marque
    change le mot (か/が en japonais)."""
    previous = ""
    for ch in text:
        if not unicodedata.combining(ch) or previous >= _FIRST_NON_LATIN_CHAR:
            yield ch
            previous = ch


def _fold(text: str) -> str:
    text = _DROPPED_G_RE.sub("g", text)
    text = _APOSTROPHES_RE.sub("", text)
    text = _INNER_BANG_RE.sub("i", text)
    text = _INNER_DOLLAR_RE.sub("s", text)
    text = text.casefold().translate(_CHAR_REPLACEMENTS)
    text = _ACRONYM_RE.sub(lambda m: m.group().replace(".", ""), text)
    return unicodedata.normalize("NFC", "".join(_strip_latin_accents(unicodedata.normalize("NFKD", text))))


def _tokens(text: str) -> Tuple[str, ...]:
    tokens: List[str] = []
    for word in _WORD_RE.findall(_fold(text)):
        if word in _AND_WORDS:
            word = "and"
        word = _WORD_ALIASES.get(word, word)
        if tokens and tokens[-1] in _NUMBERED_WORDS:
            word = _NUMBER_ALIASES.get(word, word)
        tokens.append(word)
    return tuple(tokens)


def _compact(tokens: Sequence[str]) -> str:
    return "".join(tokens)


def _version_key(text: str) -> str:
    """Clé d'une version distincte : le texte entier, pour que le remix de
    Skrillex et celui de Tiësto restent deux chansons."""
    return _compact(_tokens(text))


def _is_same_song_mention(text: str, in_brackets: bool = False) -> bool:
    """`True` si `text` décrit une version ou l'habillage de la vidéo : "Live at
    Wembley", "Official Video", "2015 Remaster" oui, "Are Made of This" non."""
    words = _tokens(text)
    if not words:
        return False
    if _LIVE_PLACE_RE.match(text) or (in_brackets and _BRACKET_ONLY_MENTION_RE.search(text)):
        return True
    named = [w for w in words if not (w.isdigit() or _RESOLUTION_RE.fullmatch(w))]
    if not named:
        return True
    if len(named) == 1:
        return named[0] in _LONE_VERSION_WORDS
    return all(w in _VERSION_WORDS for w in named)


def _analyze_title(raw: str) -> Tuple[List[str], List[str], Set[str]]:
    """Découpe un titre brut en segments utiles ("Artiste", "Titre"), sous-titres
    entre parenthèses et versions distinctes."""
    subtitles: List[str] = []
    variants: Set[str] = set()

    def _classify_bracket(match: "re.Match[str]") -> str:
        content = match.group(1)
        if _PART_GROUP_RE.match(content):
            return f" {content} "
        if _DISTINCT_VERSION_RE.search(content):
            variants.add(_version_key(content))
        elif content.strip() and not _LEADING_CREDIT_RE.match(content) and not _is_same_song_mention(content, True):
            subtitles.append(content)
        return " "

    text = _BRACKET_RE.sub(_classify_bracket, raw)
    segments: List[str] = []
    for position, segment in enumerate(_SEGMENT_SEP_RE.split(text)):
        segment = _FEAT_RE.sub("", segment).strip()
        if not segment:
            continue
        cleaned = _TRAILING_JUNK_RE.sub("", segment).strip()
        if position > 0 and _DISTINCT_VERSION_RE.search(cleaned):
            variants.add(_version_key(cleaned))
        elif position > 0 and _is_same_song_mention(cleaned):
            continue
        elif cleaned:
            segments.append(cleaned)
    return segments, subtitles, variants


@lru_cache(maxsize=4096)
def _analyze_artist(raw: str) -> _Artist:
    folded = _fold(raw or "")
    tokens = tuple(t for t in _tokens(raw or "") if t not in _CHANNEL_WORDS)
    if len(tokens) > 1 and tokens[0] == "the":
        tokens = tokens[1:]
    whole = _compact(t for t in tokens if t != "and")

    credit_tokens: List[Tuple[str, ...]] = [tuple(t for t in tokens if t != "and")] if whole else []
    for part in _ARTIST_SPLIT_RE.split(folded):
        part_tokens = tuple(t for t in _tokens(part) if t not in _CHANNEL_WORDS)
        if len(part_tokens) > 1 and part_tokens[0] == "the":
            part_tokens = part_tokens[1:]
        if len(_compact(part_tokens)) >= _MIN_CREDIT_CHARS:
            credit_tokens.append(part_tokens)
    unique = tuple(dict.fromkeys(credit_tokens))
    return _Artist(whole, tokens, frozenset(_compact(c) for c in unique), unique)


def _reading(title: str, subtitles: Sequence[str], variants: Set[str], artist: _Artist) -> Optional[_Reading]:
    base = _tokens(title)
    if not base:
        return None
    full = base
    for subtitle in subtitles:
        full += _tokens(subtitle)
    return _Reading(full, base, frozenset(variants), artist)


def _readings(track: SongTrack) -> List[_Reading]:
    """Toutes les interprétations plausibles de `track`. Un champ Deezer est
    pris tel quel ; une vidéo YouTube peut aussi cacher "Artiste - Titre" ou
    "Titre - Artiste" dans son titre, sans qu'on sache lequel."""
    if not (track.title or "").strip():
        return []
    segments, subtitles, variants = _analyze_title(track.title)
    if not segments:
        return []
    artist = _analyze_artist(track.artist)
    if track.structured:
        # Le reste d'un titre Deezer ("Song - From Movie") est un sous-titre.
        reading = _reading(segments[0], [*segments[1:], *subtitles], variants, artist)
        return [reading] if reading else []

    candidates: List[Tuple[str, _Artist]] = [(" ".join(segments), artist)]
    if len(segments) >= 2:
        # Jamais un segment seul avec l'artiste du champ : le nom de la chaîne
        # est commun à toute une playlist, et "Daft Punk" passerait pour le
        # titre de tous les "Daft Punk - ...".
        first, second = segments[0], segments[1]
        candidates += [(second, _analyze_artist(first)), (first, _analyze_artist(second))]
    readings = (_reading(title, subtitles, variants, who) for title, who in candidates)
    return [r for r in readings if r is not None]


def _is_token_run(short: Sequence[str], long: Sequence[str]) -> bool:
    size = len(short)
    return any(tuple(long[i:i + size]) == tuple(short) for i in range(len(long) - size + 1))


def _is_channel_of(artist: str, channel: str) -> bool:
    """"brunomarsofficial" est la chaîne de "brunomars"."""
    return (
        len(artist) >= _MIN_SUBSET_ARTIST_CHARS
        and channel.startswith(artist)
        and channel[len(artist):] in _CHANNEL_SUFFIXES
    )


@lru_cache(maxsize=65536)
def _artists_match(a: _Artist, b: _Artist) -> bool:
    if not a.whole or not b.whole:
        return False
    if a.credits & b.credits:
        return True
    short, long = (a, b) if len(a.tokens) <= len(b.tokens) else (b, a)
    if len(short.whole) >= _MIN_SUBSET_ARTIST_CHARS and _is_token_run(short.tokens, long.tokens):
        return True
    if _is_channel_of(a.whole, b.whole) or _is_channel_of(b.whole, a.whole):
        return True
    if min(len(a.whole), len(b.whole)) < _MIN_FUZZY_ARTIST_CHARS:
        return False
    return _is_close(a.whole, b.whole, _FUZZY_ARTIST_RATIO)


def _is_close(a: str, b: str, threshold: float) -> bool:
    matcher = SequenceMatcher(None, a, b, autojunk=False)
    return (
        matcher.real_quick_ratio() >= threshold
        and matcher.quick_ratio() >= threshold
        and matcher.ratio() >= threshold
    )


def _numbers(tokens: Sequence[str]) -> Tuple[str, ...]:
    return tuple(t for t in tokens if t.isdigit())


class _UnionFind:
    def __init__(self, size: int) -> None:
        self._parent = list(range(size))

    def find(self, item: int) -> int:
        while self._parent[item] != item:
            self._parent[item] = self._parent[self._parent[item]]
            item = self._parent[item]
        return item

    def union(self, a: int, b: int) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            self._parent[max(root_a, root_b)] = min(root_a, root_b)


def _merge_all(groups: Iterable[List[int]], sets: _UnionFind) -> None:
    for members in groups:
        for other in members[1:]:
            sets.union(members[0], other)


def _durations_agree(a: SongTrack, b: SongTrack) -> bool:
    if a.structured and b.structured:
        return False
    if a.duration_seconds is None or b.duration_seconds is None:
        return False
    return abs(a.duration_seconds - b.duration_seconds) <= _MAX_DURATION_GAP_SECONDS


def _subtitles_conflict(a: _Reading, b: _Reading) -> bool:
    """Un sous-titre peut manquer d'un côté, pas différer : "Intro (Paris)" et
    "Intro (Tokyo)" sont deux morceaux."""
    return a.full != a.base and b.full != b.base and a.full != b.full


def _merge_by_title(tracks: Sequence[SongTrack], readings: Sequence[List[_Reading]], sets: _UnionFind) -> None:
    """Signaux 2 et 4 : bloc par titre exact, pour ne comparer les artistes
    qu'entre morceaux qui ont une chance d'être la même chanson."""
    blocks: Dict[Tuple[str, frozenset], List[Tuple[int, _Reading]]] = {}
    for index, track_readings in enumerate(readings):
        for reading in track_readings:
            for title in {_compact(reading.full), _compact(reading.base)}:
                blocks.setdefault((title, reading.variants), []).append((index, reading))

    for (title, _variants), members in blocks.items():
        for (i, reading_a), (j, reading_b) in combinations(members, 2):
            if sets.find(i) == sets.find(j) or _subtitles_conflict(reading_a, reading_b):
                continue
            if _artists_match(reading_a.artist, reading_b.artist) or (
                len(title) >= _MIN_DURATION_MATCH_TITLE_CHARS
                and len(reading_a.base) >= 2
                and _durations_agree(tracks[i], tracks[j])
            ):
                sets.union(i, j)


def _merge_by_word_bag(tracks: Sequence[SongTrack], readings: Sequence[List[_Reading]], sets: _UnionFind) -> None:
    """Signal 3 : "Daft Punk Get Lucky", "Get Lucky by Daft Punk" et le couple
    ("Get Lucky", "Daft Punk") contiennent les mêmes mots."""
    bags: Dict[Tuple[Tuple[str, ...], frozenset], List[Tuple[int, _Reading, bool]]] = {}

    def _add(words: Iterable[str], index: int, reading: _Reading, has_artist: bool) -> None:
        bag = tuple(sorted(w for w in words if w not in _BAG_STOPWORDS))
        bags.setdefault((bag, reading.variants), []).append((index, reading, has_artist))

    for index, track_readings in enumerate(readings):
        for reading in track_readings:
            for credit in reading.artist.credit_tokens:
                _add(reading.full + credit, index, reading, True)
                _add(reading.base + credit, index, reading, True)
        whole_title = track_readings[0] if track_readings else None
        if whole_title and not tracks[index].structured and len(whole_title.full) >= _MIN_TITLE_ONLY_BAG_WORDS:
            _add(whole_title.full, index, whole_title, False)

    for members in bags.values():
        for (i, reading_a, artist_a), (j, reading_b, artist_b) in combinations(members, 2):
            if sets.find(i) == sets.find(j) or _subtitles_conflict(reading_a, reading_b):
                continue
            # Deux titres de vidéo sans artiste connu : identiques, ils peuvent
            # être une reprise ("Let It Be") et seule une durée égale départage ;
            # mêmes mots dans un autre ordre, c'est "Artiste Titre"/"Titre Artiste".
            if artist_a or artist_b or reading_a.full != reading_b.full or _durations_agree(tracks[i], tracks[j]):
                sets.union(i, j)


def _merge_fuzzy_titles(readings: Sequence[List[_Reading]], sets: _UnionFind) -> None:
    """Signal 5 : "Dont Stop Believin" / "Don't Stop Believing" chez un même
    artiste. Bloc par artiste crédité : jamais de comparaison floue entre tous
    les morceaux de la partie. Les nombres doivent être identiques, sinon
    "Song 1" et "Song 2" passeraient pour une faute de frappe."""
    blocks: Dict[Tuple[str, frozenset], Dict[str, Tuple[Tuple[str, ...], List[int]]]] = {}
    for index, track_readings in enumerate(readings):
        for reading in track_readings:
            title = _compact(reading.full)
            if len(title) < _MIN_FUZZY_TITLE_CHARS:
                continue
            for credit in reading.artist.credits:
                titles = blocks.setdefault((credit, title[:_FUZZY_PREFIX_CHARS], reading.variants), {})
                titles.setdefault(title, (reading.full, []))[1].append(index)

    for titles in blocks.values():
        for (title_a, (tokens_a, members_a)), (title_b, (tokens_b, members_b)) in combinations(titles.items(), 2):
            if _numbers(tokens_a) == _numbers(tokens_b) and _is_close(title_a, title_b, _FUZZY_TITLE_RATIO):
                sets.union(members_a[0], members_b[0])


def group_songs(tracks: Iterable[SongTrack]) -> Dict[int, int]:
    """Renvoie `{track_id: song_id}` : deux morceaux de même `song_id` sont la
    même chanson. `song_id` est le plus petit `track_id` du groupe."""
    items = list(tracks)
    sets = _UnionFind(len(items))

    by_id: Dict[Tuple[str, str], List[int]] = {}
    for index, track in enumerate(items):
        if track.youtube_video_id:
            by_id.setdefault(("video", track.youtube_video_id), []).append(index)
        if track.isrc and track.isrc.strip():
            by_id.setdefault(("isrc", track.isrc.strip().upper()), []).append(index)
    _merge_all(by_id.values(), sets)

    readings = [_readings(track) for track in items]
    _merge_by_title(items, readings, sets)
    _merge_by_word_bag(items, readings, sets)
    _merge_fuzzy_titles(readings, sets)

    smallest: Dict[int, int] = {}
    for index, track in enumerate(items):
        root = sets.find(index)
        smallest[root] = min(smallest.get(root, track.id), track.id)
    return {track.id: smallest[sets.find(index)] for index, track in enumerate(items)}
