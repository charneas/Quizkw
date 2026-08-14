"""
Génération de contenu via Claude (story F.2, AC #2).

Isolé du router pour rester testable par mock du client Anthropic, sans
jamais appeler l'API réelle depuis la suite pytest (voir Dev Notes de la story).
"""
import json
import os

import anthropic
from pydantic import ValidationError

from app.schemas_content_gen import GeneratedContent
from app.schemas import ThemeCategoryEnum

MODEL = "claude-sonnet-5"
QUESTIONS_PER_GENERATION = 10

_SYSTEM_PROMPT = (
    "Tu génères du contenu pour un jeu de quiz. Réponds UNIQUEMENT avec un objet JSON "
    "valide, sans texte avant ou après, sans balises markdown. Le JSON doit avoir "
    "exactement cette forme : "
    '{"theme_name": string, "category": "serious" | "pop_culture" | "whimsical", '
    '"questions": [{"text": string, "correct_answer": string, '
    '"wrong_answers": [string, string, string], "difficulty": "easy" | "medium" | "hard"}]}. '
    f"Génère exactement {QUESTIONS_PER_GENERATION} questions, factuellement exactes d'après "
    "l'extrait fourni, avec exactement 3 mauvaises réponses plausibles mais incorrectes par question."
)


CLIENT_TIMEOUT_SECONDS = 30.0


def _get_client() -> anthropic.Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY non configurée")
    # Défaut SDK = 10 minutes, beaucoup trop long pour un appel synchrone dans
    # une requête HTTP (décision produit : pas de file d'attente). Voir Dev
    # Notes de la story.
    return anthropic.Anthropic(api_key=api_key, timeout=CLIENT_TIMEOUT_SECONDS)


def generate_content(topic: str, wikipedia_extract: str, category: ThemeCategoryEnum | None) -> GeneratedContent:
    """Appelle Claude pour générer un thème + des questions à partir d'un extrait
    Wikipedia. Lève ValueError si l'appel échoue (réseau, timeout, erreur API) ou
    si la réponse n'est pas un JSON valide conforme au contrat attendu (AD-6 :
    jamais de suggestion partiellement remplie, et jamais un 500 non mappé pour
    un échec de fournisseur externe)."""
    client = _get_client()

    category_instruction = (
        f'Utilise obligatoirement la catégorie "{category.value}".'
        if category is not None
        else "Choisis la catégorie la plus appropriée parmi serious, pop_culture, whimsical."
    )

    user_message = (
        f"Sujet : {topic}\n\n"
        f"Extrait Wikipedia :\n{wikipedia_extract}\n\n"
        f"{category_instruction}"
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
    except anthropic.APIError as e:
        # Regroupe timeout/réseau/429/401/5xx : tous des échecs du fournisseur
        # externe, tous mappés en 502 par le router (trouvé en revue de code :
        # non attrapé, ce chemin fuyait en 500 non mappé, contredisant AD-6 et
        # la Dev Note de la story qui promettait explicitement ce mapping).
        raise ValueError(f"Échec de l'appel à l'API Anthropic : {e}") from e

    text_blocks = [block.text for block in response.content if getattr(block, "type", None) == "text"]
    raw_text = "".join(text_blocks).strip()

    # Playtest 2026-08-15 : malgré la consigne "sans balises markdown", le
    # modèle enveloppe parfois sa réponse dans un bloc ```json ... ``` —
    # retiré avant parsing plutôt que de faire échouer toute la génération.
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
        raw_text = raw_text.strip()

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Réponse du LLM non-JSON : {e}") from e

    try:
        return GeneratedContent.model_validate(parsed)
    except ValidationError as e:
        raise ValueError(f"Réponse du LLM ne respecte pas le contrat attendu : {e}") from e
