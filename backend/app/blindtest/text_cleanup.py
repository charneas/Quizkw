"""Uniformisation du texte affiché (titre/artiste) des morceaux importés
(retour utilisateur, 2026-09-14 : "réconciliation des chansons et
uniformisation dans la base de données").

Distinct de `cache.normalize_key` (qui produit une clé de recherche agressive
— minuscule, sans accents/ponctuation — jamais affichée à l'utilisateur) :
ce module ne fait que du nettoyage *non destructif* pour l'affichage, jamais
de mise en forme qui altérerait un nom stylisé à dessein (ex. "P!nk",
"deadmau5", "Sigur Rós" gardent leur casse/accents originaux).

Appelé à deux endroits (mêmes règles, jamais dupliquées) :
- `main_blindtest.py` (import) : nettoie chaque `title`/`artist` extrait
  juste avant la création du `Track`, pour que les nouveaux imports ne
  réintroduisent pas le problème.
- `backend/scripts/normalize_blindtest_tracks.py` : rejoue les mêmes règles
  sur les `Track` déjà en base (tâche ponctuelle de réconciliation)."""
import html
import re
import unicodedata
from typing import Optional

# Suffixes techniques fréquents dans les titres YouTube ("(Official Video)",
# "[Official Music Video]", "(Lyrics)", "(HD)"...) qui n'ont pas leur place
# dans le titre affiché pendant une manche de blind test — retirés seulement
# en fin de chaîne (jamais au milieu) pour ne jamais mutiler un titre légitime
# qui contiendrait par ailleurs une parenthèse.
_JUNK_SUFFIX_RE = re.compile(
    r"""[\s]*[\(\[]\s*
        (official\s*(lyrics?\s*|music\s*)?(video|audio)?
        |lyrics?(\s*video)?
        |audio
        |hd|4k
        |visualizer)
        \s*[\)\]]\s*$""",
    re.IGNORECASE | re.VERBOSE,
)

_WS_RE = re.compile(r"\s+")

# Retour utilisateur (2026-09-14) : "c'est mal découpé" — titres de chaînes
# de diffusion (Eurovision Song Contest, Festival da Canção...) du style
# "Artiste - Titre (LIVE) | France 🇫🇷 | Grand Final | Eurovision 2021" :
# tout ce qui suit le premier " | " est alors du contexte de diffusion (pays,
# manche, édition...), jamais une partie du titre de la chanson elle-même.
#
# ATTENTION (constaté sur données réelles en réconciliation, 2026-09-15) :
# un "|" n'est PAS toujours un séparateur de contexte de diffusion — certains
# titres l'utilisent pour structurer l'inverse, ex. "DORA 2026 | LELEK -
# ANDROMEDA | POBJEDNIČKI NASTUP" où le vrai titre/artiste est justement
# APRÈS le premier "|". Tronquer inconditionnellement au premier "|" y
# détruirait le morceau réel.
#
# Retour utilisateur (2026-09-15, suite) : "faut faire attention que
# l'artiste/nom de la chanson sont cohérents" — pas la peine de se limiter au
# mot "Eurovision" : le vrai signal fiable est structurel, pas lexical — la
# portion AVANT le premier "|" contient-elle déjà elle-même un séparateur
# artiste/titre ("NAPA - Deslocado" oui, "DORA 2026" non) ? Si oui, cette
# portion est un "{Artiste} - {Titre}" de confiance et tout le reste est bien
# du contexte de diffusion annexe ; si non (comme "DORA 2026"), on ne touche
# à rien plutôt que de deviner. Générique (Eurovision, Festival da Canção,
# n'importe quel diffuseur suivant cette même convention), jamais dépendant
# d'un mot-clé qui pourrait aussi bien apparaître dans un titre sans rapport.
_PIPE_SUFFIX_RE = re.compile(r"\s*\|.*$")

# Séparateur "Artiste - Titre" : hyphen normal, mais aussi tiret demi-cadratin
# "–" (U+2013) — constaté sur données réelles (ex. "Sissal – Hallucination"),
# typographiquement équivalent pour un lecteur humain, jamais ambigu comme
# séparateur (contrairement à un mot-clé générique) donc sans risque à
# accepter en plus du hyphen partout où ce module détecte ce motif.
_ARTIST_TITLE_SEP_RE = re.compile(r"\s[-–]\s")

# Retour utilisateur (2026-09-15, trouvé en dry-run) : certaines émissions
# (Operación Triunfo) inversent la convention — '"Titre de la chanson" -
# Interprète(s)' au lieu de "Artiste - Titre" — le titre entre guillemets EST
# la chanson, jamais l'artiste. Sans ce garde-fou, '"UNA LLUNA A L’AIGUA" -
# MIKI' finissait artiste='"UNA LLUNA A L'AIGUA"' / titre='MIKI', exactement
# inversé. Guillemets droits ou typographiques, jamais l'apostrophe simple
# (trop ambiguë : une apostrophe de contraction, ex. "L'AIGUA", n'encadre
# rien).
_QUOTED_PREFIX_RE = re.compile(r'^["“](.+)["”]$')

# Retour utilisateur (2026-09-15, trouvé après coup) : troisième convention —
# 'Serge Lama "Je suis malade" | INA Chansons' : PAS de tiret du tout, juste
# un artiste non guillemeté suivi du titre entre guillemets. `.+?` non-glouton
# pour le préfixe (l'artiste s'arrête au premier guillemet rencontré), `.+?`
# non-glouton aussi pour l'intérieur (mais ancré par `$`, donc capture bien
# tout jusqu'au dernier guillemet fermant de la portion). Comme le guillemet
# ouvrant doit être précédé d'au moins un caractère (`.+?` exige ≥1), cette
# convention ne peut jamais matcher en même temps que `_QUOTED_PREFIX_RE`
# (où le guillemet est le tout premier caractère) — les deux sont mutuellement
# exclusives par construction, jamais de conflit d'interprétation.
_UNQUOTED_ARTIST_QUOTED_TITLE_RE = re.compile(r'^(.+?)\s*["“](.+?)["”]\s*$')


def _split_artist_title(value: str) -> tuple[str, str, str]:
    """Équivalent de `str.partition(" - ")` mais acceptant aussi le tiret
    demi-cadratin comme séparateur — renvoie `(avant, séparateur, après)`,
    `séparateur` vide si aucun des deux motifs n'a été trouvé."""
    match = _ARTIST_TITLE_SEP_RE.search(value)
    if not match:
        return value, "", ""
    return value[: match.start()], match.group(), value[match.end() :]


def _extract_pipe_artist_title(title: str) -> Optional[tuple[str, str]]:
    """Si `title` contient un "|" ET que la portion avant le premier "|"
    ressemble à une des conventions "{Artiste} {Titre}" connues, renvoie
    `(artiste, titre)` extraits de cette portion (tout le reste, à partir du
    premier "|", est alors considéré comme du contexte de diffusion annexe —
    pays, manche, chaîne...). Renvoie `None` si aucune convention connue ne
    matche : mieux vaut ne rien deviner que mal découper (cf. "DORA 2026 |
    LELEK - ANDROMEDA | POBJEDNIČKI NASTUP", où le vrai contenu est justement
    APRÈS le premier "|" — aucune des conventions ci-dessous n'y matche,
    à raison).

    Conventions reconnues, dans cet ordre :
    1. "{Artiste} - {Titre}" (tiret ou tiret demi-cadratin) — la plus
       courante (Eurovision Song Contest, Festival da Canção, Riot Games
       Music...).
    2. '"{Titre}" - {Interprète(s)}' — convention inversée constatée sur
       Operación Triunfo : le préfixe entre guillemets est le titre, jamais
       l'artiste.
    3. '{Artiste} "{Titre}"' (sans tiret) — constatée sur des chaînes
       d'archives (INA Chansons) : l'artiste précède directement le titre
       entre guillemets, sans séparateur."""
    if "|" not in title:
        return None
    first_segment = title.split("|", 1)[0]

    sep_match = _ARTIST_TITLE_SEP_RE.search(first_segment)
    if sep_match:
        prefix = first_segment[: sep_match.start()].strip()
        rest = first_segment[sep_match.end() :].strip()
        if prefix and rest:
            quoted = _QUOTED_PREFIX_RE.match(prefix)
            if quoted:
                return rest, quoted.group(1).strip()
            return prefix, rest

    unquoted_match = _UNQUOTED_ARTIST_QUOTED_TITLE_RE.match(first_segment.strip())
    if unquoted_match:
        artist, song_title = unquoted_match.group(1).strip(), unquoted_match.group(2).strip()
        if artist and song_title:
            return artist, song_title

    return None

# Retour utilisateur (2026-09-14) : "Enlève le VEVO ça n'a aucun sens de le
# garder" — suffixe technique de nom de chaîne YouTube ("OliviaRodrigoVEVO",
# "KatyPerryVEVO"...), jamais un nom d'artiste réel. Optionnellement précédé
# d'un tiret/espace/underscore quand le channel title en a un.
_VEVO_SUFFIX_RE = re.compile(r"[\s\-_]*VEVO$", re.IGNORECASE)

# Une fois VEVO retiré, ces channel titles restent collés sans espace
# ("OliviaRodrigo", "DeadOrAlive") : on ne le fait QUE dans ce cas précis
# (jamais sur un artiste "normal" par ailleurs, cf. `_clean_artist_field`) —
# insère un espace avant chaque majuscule qui suit une minuscule/chiffre.
_CAMEL_CASE_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _clean_artist_field(value: str) -> str:
    if not value:
        return value
    value = html.unescape(value)
    value = unicodedata.normalize("NFC", value)
    without_vevo = _VEVO_SUFFIX_RE.sub("", value)
    if without_vevo != value and " " not in without_vevo.strip():
        # Le suffixe VEVO vient d'être retiré ET ce qui reste est un seul
        # bloc collé sans espace -> channel title auto-généré, on tente de
        # le rendre lisible (cf. commentaire de `_CAMEL_CASE_RE`).
        without_vevo = _CAMEL_CASE_RE.sub(" ", without_vevo)
    value = without_vevo
    value = _WS_RE.sub(" ", value).strip()
    return value


def _clean_title_field(value: str, truncate_pipe: bool = False) -> str:
    if not value:
        return value
    # Entités HTML résiduelles (`&amp;`, `&#39;`...) parfois renvoyées telles
    # quelles par certaines réponses d'API — décodées avant tout le reste
    # pour que le nettoyage suivant s'applique au texte réel.
    value = html.unescape(value)
    # Forme unicode canonique (NFC) : deux représentations visuellement
    # identiques d'un même caractère accentué (composé vs décomposé) ne
    # doivent pas être traitées comme des titres différents.
    value = unicodedata.normalize("NFC", value)
    if truncate_pipe:
        value = _PIPE_SUFFIX_RE.sub("", value)
    # Suffixe technique retiré une seule fois : un titre en aurait rarement
    # deux empilés, et boucler ouvrirait la porte à un titre légitime
    # terminant par une parenthèse vidée par erreur en cascade.
    value = _JUNK_SUFFIX_RE.sub("", value)
    value = _WS_RE.sub(" ", value).strip()
    return value


def _strip_redundant_artist_prefix(title: str, artist: str) -> str:
    """Retour utilisateur (2026-09-14) : beaucoup de titres YouTube répètent
    déjà l'artiste en préfixe ("Olivia Rodrigo - begged (SNL 2026)" pour
    l'artiste "OliviaRodrigoVEVO"/"Olivia Rodrigo") — une fois l'artiste
    nettoyé (`_clean_artist_field`), si le titre commence exactement par
    "{artiste} - ", ce préfixe redondant est retiré du titre affiché.
    Comparaison insensible à la casse (l'artiste channel a souvent une casse
    différente du préfixe de titre) ; ne touche à rien si ça ne matche pas
    exactement (jamais de préfixe partiel deviné)."""
    if not title or not artist:
        return title
    prefix, sep, rest = _split_artist_title(title)
    if sep and prefix.strip().casefold() == artist.strip().casefold():
        return rest.strip()
    return title


def clean_title_artist(title: str, artist: str) -> tuple[str, str]:
    """Nettoyage non destructif du couple (title, artist) affiché : entités
    HTML, forme unicode, espaces superflus, suffixes techniques YouTube en
    fin de titre, contexte de diffusion après le premier "|", suffixe "VEVO"
    et préfixe artiste redondant en début de titre. Ne touche jamais à la
    casse/aux accents volontaires (hors les cas ciblés ci-dessus) — cf.
    docstring du module.

    Retour utilisateur (2026-09-15) : sur un titre de chaîne de diffusion
    (Eurovision Song Contest, Festival da Canção...), le champ `artist`
    fourni par la source EST le nom de la chaîne/de l'émission, jamais le
    vrai artiste — et "donne beaucoup trop de contexte" pour un jeu où il
    faut deviner qui a importé le morceau, pas reconnaître l'émission. Dans
    ce cas, l'artiste réel (et le titre débarrassé de son préfixe) sont
    extraits du titre lui-même ("{Artiste} - {Titre}", déjà tronqué du
    contexte de diffusion) plutôt que conservés depuis le champ `artist`
    d'origine — détection structurelle uniquement, générique à tout
    diffuseur suivant l'une des conventions reconnues (cf.
    `_extract_pipe_artist_title`, y compris sa note sur le repli "Eurovision"
    abandonné pour non-idempotence)."""
    pipe_extraction = _extract_pipe_artist_title(title or "")
    clean_title = _clean_title_field(title, truncate_pipe=pipe_extraction is not None)

    if pipe_extraction is not None:
        artist_candidate, title_candidate = pipe_extraction
        return _clean_title_field(title_candidate), _clean_artist_field(artist_candidate)

    clean_artist = _clean_artist_field(artist)
    clean_title = _strip_redundant_artist_prefix(clean_title, clean_artist)
    return clean_title, clean_artist
