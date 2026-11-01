"""Règles du blind test classique (spec-blindtest-classique.md) : barème et
reconnaissance de la réponse tapée. Module pur, sans DB ni réseau.

Deux éléments à trouver sur une chanson, le titre et l'artiste principal, dans
un seul champ et sans limite d'essais. `build_reference` extrait ce qui est
attendu d'un titre de vidéo souvent bruité ; `match_answer` y confronte le texte
du joueur ; `points` transforme les temps de découverte en score.

La normalisation réutilise celle de `song_identity` (accents, casse,
ponctuation) : le jeu et le recoupement des chansons comparent le même texte."""
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Collection, Optional, Sequence, Set, Tuple, Union

from app.blindtest.song_identity import _FEAT_RE, _analyze_artist, _analyze_title, _artists_match, _compact, _tokens
from app.blindtest.text_cleanup import _QUOTED_PREFIX_RE, clean_title_artist

TITLE = "title"
ARTIST = "artist"

ROUND_SECONDS = 30
TITLE_POINTS = 100
ARTIST_POINTS = 60
# Valeur restante d'un élément trouvé à la dernière seconde : une découverte
# tardive rapporte toujours quelque chose.
END_OF_ROUND_RATIO = 0.2
BOTH_FOUND_BONUS = 0.25

SIMILARITY_THRESHOLD = 0.85
# Une référence courte n'a pas de marge pour une faute : "Sea" n'est pas "Sia".
MAX_EXACT_MATCH_CHARS = 4
# Un joueur peut coller ou séparer un mot ("bey once"), jamais en oublier
# plusieurs ; la similarité écarte ensuite un simple début de titre.
_WINDOW_SLACKS = (0, -1, 1)

# "Artiste - Titre" : tiret simple, demi-cadratin ou cadratin.
_DASH_SEPARATOR_RE = re.compile(r"\s[-–—]\s")
# Après un tiret, annonce une version de la chanson, pas une chanson. "Live" n'y
# suffit pas seul : "Oasis - Live Forever" est un titre.
_VERSION_SEGMENT_RE = re.compile(
    r"^\s*(?:from|live\s+(?:in|at|on|from|a|à|au)|remaster(?:ed)?|\d{4}\s+remaster(?:ed)?|radio\s+edit)\b",
    re.IGNORECASE,
)

Elapsed = Union[float, Tuple[float, float]]


@dataclass(frozen=True)
class Reference:
    """Réponse attendue d'une chanson. `title` et `artist` sont les textes
    affichés au reveal ; `titles` et `artists` les formes acceptées, normalisées
    en mots."""
    title: str
    artist: str
    titles: Tuple[Tuple[str, ...], ...]
    artists: Tuple[Tuple[str, ...], ...]


def _decayed(base: int, elapsed: float) -> float:
    progress = min(max(elapsed, 0), ROUND_SECONDS) / ROUND_SECONDS
    return base * (1 - (1 - END_OF_ROUND_RATIO) * progress)


def points(found_title: bool, found_artist: bool, elapsed: Elapsed) -> int:
    """Score d'un joueur sur une chanson. `elapsed` donne le moment de chaque
    découverte, `(titre, artiste)`, ou un seul nombre si elles coïncident.

    Sert aussi au score en direct : la valeur ne fait que croître quand le
    second élément arrive, un joueur ne peut donc jamais perdre de points."""
    title_elapsed, artist_elapsed = elapsed if isinstance(elapsed, tuple) else (elapsed, elapsed)
    total = 0.0
    if found_title:
        total += _decayed(TITLE_POINTS, title_elapsed)
    if found_artist:
        total += _decayed(ARTIST_POINTS, artist_elapsed)
    if found_title and found_artist:
        total *= 1 + BOTH_FOUND_BONUS
    return int(round(total))


def _split_title_and_artist(title: str, artist: str, structured: bool) -> Tuple[str, str, Sequence[str]]:
    """Sépare chanson et artiste. `clean_title_artist` ne retire "Artiste - "
    que si ce préfixe est le nom de la chaîne, ce qui laisse l'artiste d'une
    chaîne de compilation dans le titre : ici, un tiret tranche toujours, sauf
    pour des champs déjà fiables (`structured`), où "Song - From Movie" est un
    titre."""
    clean_title, channel = clean_title_artist(title, artist)
    segments, subtitles, _ = _analyze_title(clean_title)
    if not segments:
        return clean_title, channel, []

    if structured:
        return segments[0], channel, subtitles
    has_separator = _DASH_SEPARATOR_RE.search(clean_title) is not None
    if len(segments) < 2 or not has_separator:
        return " ".join(segments), channel, subtitles

    first, second = segments[0], segments[1]
    quoted = _QUOTED_PREFIX_RE.match(first)
    if quoted:
        return quoted.group(1), second, subtitles
    channel_artist = _analyze_artist(channel)
    channel_is_first = _artists_match(channel_artist, _analyze_artist(first))
    if _VERSION_SEGMENT_RE.match(second) and not channel_is_first:
        return first, channel, subtitles
    if _artists_match(channel_artist, _analyze_artist(second)) and not channel_is_first:
        return first, second, subtitles
    return second, first, subtitles


def build_reference(title: str, artist: str, structured: bool = False) -> Reference:
    """`structured` : `title` et `artist` viennent de champs fiables (Deezer,
    preset relu), pas d'un titre de vidéo et d'un nom de chaîne."""
    song, performer, subtitles = _split_title_and_artist(title, artist, structured)
    song = song.strip().strip('"“”').strip()
    main_artist = _FEAT_RE.sub("", performer).strip()

    base = _tokens(song)
    titles = [base] if base else []
    if base and subtitles:
        titles.append(base + tuple(word for subtitle in subtitles for word in _tokens(subtitle)))

    # Le nom complet d'abord, puis chaque co-artiste seul.
    artists = _analyze_artist(main_artist).credit_tokens
    return Reference(song, main_artist, tuple(titles), artists)


def _is_similar(candidate: str, target: str) -> bool:
    if len(target) <= MAX_EXACT_MATCH_CHARS:
        return candidate == target
    return SequenceMatcher(None, candidate, target, autojunk=False).ratio() >= SIMILARITY_THRESHOLD


def _find_window(
    tokens: Sequence[str], used: Set[int], forms: Sequence[Tuple[str, ...]]
) -> Optional[Set[int]]:
    """Indices des mots de `tokens` qui forment l'une des `forms`, sans
    réutiliser un mot déjà attribué à l'autre élément."""
    for form in forms:
        target = _compact(form)
        for slack in _WINDOW_SLACKS:
            size = len(form) + slack
            if size < 1:
                continue
            for start in range(len(tokens) - size + 1):
                window = set(range(start, start + size))
                if not window & used and _is_similar(_compact(tokens[start:start + size]), target):
                    return window
    return None


def _scan(tokens: Sequence[str], reference: Reference, order: Sequence[str], skip: Collection[str]) -> Set[str]:
    forms = {TITLE: reference.titles, ARTIST: reference.artists}
    used: Set[int] = set()
    found: Set[str] = set()
    # Les mots d'un élément déjà trouvé restent à lui, sauf sur une chanson
    # éponyme : là, seul un second passage du même mot peut donner l'artiste.
    if not set(reference.titles) & set(reference.artists):
        for element in skip:
            used |= _find_window(tokens, used, forms[element]) or set()
    for element in order:
        if element in skip:
            continue
        window = _find_window(tokens, used, forms[element])
        if window is not None:
            used |= window
            found.add(element)
    return found


def match_answer(text: str, reference: Reference, skip: Collection[str] = ()) -> Set[str]:
    """Éléments (`TITLE`, `ARTIST`) reconnus dans `text`. Chaque mot de la
    réponse ne compte que pour un élément : "killer queen" donne le titre de
    Queen sans donner l'artiste, y compris si le joueur le retape après coup.
    Les deux ordres sont essayés pour trouver le plus d'éléments possible ; `skip`
    écarte ceux déjà trouvés, ce qui permet de marquer l'artiste d'une chanson
    éponyme avec le même mot."""
    tokens = _tokens(text or "")
    title_first = _scan(tokens, reference, (TITLE, ARTIST), skip)
    artist_first = _scan(tokens, reference, (ARTIST, TITLE), skip)
    return title_first if len(title_first) >= len(artist_first) else artist_first
