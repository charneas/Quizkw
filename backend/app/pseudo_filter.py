"""Filtrage de pseudo pour la file publique (spec-rooms-publiques, story 2).

Liste statique de mots interdits, codée en dur (assumption confirmée en
SPEC.md — pas d'interface d'administration). Correspondance insensible à la
casse, sur sous-chaîne : un pseudo est rejeté dès qu'il contient un mot
interdit n'importe où (ex. "connard123"), pas seulement en correspondance
exacte de mot entier — plus simple à couvrir par test et plus strict côté
modération, ce qui est le comportement voulu pour ce cas d'usage (rejeter,
pas juste avertir).

Scope strictement limité à `POST /games/public/join` (voir Intent de la
story) : ne touche pas `create_team`/`join_team` du flow privé.
"""

# Liste volontairement courte et illustrative : insultes courantes et
# contenu clairement illégal/haineux. Non exhaustive par nature (liste
# statique, assumption confirmée) — extensible ici si besoin plus tard.
FORBIDDEN_WORDS = {
    "connard",
    "connasse",
    "pute",
    "putain",
    "salope",
    "enculé",
    "enculee",
    "encule",
    "niquer",
    "merde",
    "batard",
    "bâtard",
    "negro",
    "nègre",
    "negre",
    "nazi",
    "hitler",
    "pedophile",
    "pédophile",
    "terroriste",
    "fuck",
    "bitch",
    "whore",
    "nigger",
    "nigga",
    "rapist",
    "violer",
    "violeur",
}


def contains_forbidden_word(name: str) -> bool:
    """True si `name` contient un mot interdit (sous-chaîne, insensible à la casse)."""
    normalized = name.strip().lower()
    return any(word in normalized for word in FORBIDDEN_WORDS)
