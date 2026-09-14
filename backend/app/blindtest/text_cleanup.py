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


def _clean_one(value: str) -> str:
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
    # Suffixe technique retiré une seule fois : un titre en aurait rarement
    # deux empilés, et boucler ouvrirait la porte à un titre légitime
    # terminant par une parenthèse vidée par erreur en cascade.
    value = _JUNK_SUFFIX_RE.sub("", value)
    value = _WS_RE.sub(" ", value).strip()
    return value


def clean_title_artist(title: str, artist: str) -> tuple[str, str]:
    """Nettoyage non destructif du couple (title, artist) affiché : entités
    HTML, forme unicode, espaces superflus, suffixes techniques YouTube en
    fin de titre. Ne touche jamais à la casse/aux accents volontaires — cf.
    docstring du module."""
    return _clean_one(title), _clean_one(artist)
