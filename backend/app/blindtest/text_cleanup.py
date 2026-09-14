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

# Retour utilisateur (2026-09-14) : "c'est mal découpé" — titres de la
# chaîne "Eurovision Song Contest" du style "Artiste - Titre (LIVE) |
# France 🇫🇷 | Grand Final | Eurovision 2021" : tout ce qui suit le premier
# " | " est alors du contexte de diffusion (pays, manche, édition...), jamais
# une partie du titre de la chanson elle-même.
#
# Retour utilisateur (2026-09-15) : "c'est vraiment pour l'Eurovision que ça
# s'applique, le reste fait attention" — restreint volontairement à un
# marqueur non ambigu (le mot "Eurovision" lui-même, présent dans TOUT titre
# ou nom de chaîne Eurovision Song Contest), PAS à des mots-clés génériques
# ("grand final", "semi-final"...) ni à un drapeau seul, qui peuvent très bien
# apparaître dans un titre sans rapport (un titre de sport, un clip patriote,
# un tout autre concours). Un faux positif ici réécrirait l'artiste et
# tronquerait le titre à tort — mieux vaut sous-nettoyer que mal nettoyer.
#
# ATTENTION (constaté sur données réelles en réconciliation, 2026-09-15) :
# un "|" n'est PAS toujours un séparateur de contexte de diffusion — certains
# titres l'utilisent pour structurer l'inverse, ex. "DORA 2026 | LELEK -
# ANDROMEDA | POBJEDNIČKI NASTUP" où le vrai titre/artiste est justement
# APRÈS le premier "|". Tronquer inconditionnellement au premier "|" y
# détruirait le morceau réel — d'où le garde-fou "Eurovision" ci-dessus.
_PIPE_SUFFIX_RE = re.compile(r"\s*\|.*$")

_EUROVISION_RE = re.compile(r"eurovision", re.IGNORECASE)

# Séparateur "Artiste - Titre" : hyphen normal, mais aussi tiret demi-cadratin
# "–" (U+2013) — constaté sur données réelles (ex. "Sissal – Hallucination"),
# typographiquement équivalent pour un lecteur humain, jamais ambigu comme
# séparateur (contrairement à un mot-clé générique) donc sans risque à
# accepter en plus du hyphen partout où ce module détecte ce motif.
_ARTIST_TITLE_SEP_RE = re.compile(r"\s[-–]\s")


def _split_artist_title(value: str) -> tuple[str, str, str]:
    """Équivalent de `str.partition(" - ")` mais acceptant aussi le tiret
    demi-cadratin comme séparateur — renvoie `(avant, séparateur, après)`,
    `séparateur` vide si aucun des deux motifs n'a été trouvé."""
    match = _ARTIST_TITLE_SEP_RE.search(value)
    if not match:
        return value, "", ""
    return value[: match.start()], match.group(), value[match.end() :]


def _has_broadcast_context_marker(title: str, artist: str) -> bool:
    return bool(_EUROVISION_RE.search(title or "") or _EUROVISION_RE.search(artist or ""))

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

    Retour utilisateur (2026-09-15) : sur un titre/artiste Eurovision Song
    Contest (mot "Eurovision" présent, cf. `_has_broadcast_context_marker` —
    volontairement restreint à ce seul marqueur non ambigu, pas à des
    mots-clés génériques qui pourraient apparaître ailleurs), le champ
    `artist` fourni par la source EST le nom de la chaîne/de l'émission
    ("Eurovision Song Contest"), jamais le vrai artiste — et cette chaîne
    "donne beaucoup trop de contexte" pour un jeu où il faut deviner qui a
    importé le morceau, pas reconnaître l'émission. Dans ce cas précis,
    l'artiste réel (et le titre débarrassé de son préfixe) sont extraits du
    titre lui-même ("{Artiste} - {Titre}", déjà tronqué du contexte de
    diffusion ci-dessus) plutôt que conservés depuis le champ `artist`
    d'origine."""
    is_broadcast_title = _has_broadcast_context_marker(title, artist)
    clean_title = _clean_title_field(title, truncate_pipe=is_broadcast_title)

    if is_broadcast_title:
        prefix, sep, rest = _split_artist_title(clean_title)
        if sep and prefix.strip() and rest.strip():
            return _clean_title_field(rest), _clean_artist_field(prefix)

    clean_artist = _clean_artist_field(artist)
    clean_title = _strip_redundant_artist_prefix(clean_title, clean_artist)
    return clean_title, clean_artist
