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

# Retour utilisateur (2026-09-14) : "c'est mal découpé" — titres de chaînes
# de diffusion/événements (Eurovision, INA, chaînes TV...) du style
# "Artiste - Titre (LIVE) | France 🇫🇷 | Grand Final | Eurovision 2021" :
# tout ce qui suit le premier " | " est du contexte de diffusion (pays,
# manche, édition...), jamais une partie du titre de la chanson elle-même —
# tronqué en un seul point de coupe (le premier), jamais itéré, pour ne
# jamais grignoter un titre légitime au-delà de cette première occurrence.
_PIPE_SUFFIX_RE = re.compile(r"\s*\|.*$")

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


def _clean_title_field(value: str) -> str:
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
    prefix, sep, rest = title.partition(" - ")
    if sep and prefix.strip().casefold() == artist.strip().casefold():
        return rest.strip()
    return title


def clean_title_artist(title: str, artist: str) -> tuple[str, str]:
    """Nettoyage non destructif du couple (title, artist) affiché : entités
    HTML, forme unicode, espaces superflus, suffixes techniques YouTube en
    fin de titre, contexte de diffusion après le premier "|", suffixe "VEVO"
    et préfixe artiste redondant en début de titre. Ne touche jamais à la
    casse/aux accents volontaires (hors les cas ciblés ci-dessus) — cf.
    docstring du module."""
    clean_artist = _clean_artist_field(artist)
    clean_title = _clean_title_field(title)
    clean_title = _strip_redundant_artist_prefix(clean_title, clean_artist)
    return clean_title, clean_artist
