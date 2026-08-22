"""
Client Wikipedia minimal pour la génération de contenu (story F.2).

Isolé du router pour rester testable par mock au niveau du client, sans avoir
à intercepter des appels HTTP bruts dans les tests (voir Dev Notes de la story).
"""
from urllib.parse import quote

import httpx

WIKIPEDIA_SUMMARY_URL = "https://fr.wikipedia.org/api/rest_v1/page/summary/{topic}"


def get_wikipedia_extract(topic: str, timeout: float = 10.0) -> str:
    """Retourne l'extrait résumé d'un sujet Wikipedia.

    Lève LookupError si le sujet n'existe pas (404 Wikipedia). Lève ValueError
    pour tout autre échec (réseau, timeout, 5xx/429 Wikipedia). L'appelant
    traduit LookupError en 404 et ValueError en 502 (AD-6).
    """
    # Un sujet non encodé (ex. "AC/DC", "a?b") casse le chemin REST ou
    # redirige silencieusement vers un autre endpoint — trouvé en revue de code.
    url = WIKIPEDIA_SUMMARY_URL.format(topic=quote(topic, safe=""))

    try:
        # Wikimedia bloque en 403 les User-Agent génériques sans contact
        # (leur robot policy l'exige explicitement) — trouvé en prod, curl
        # passait avec le même endpoint mais httpx avec un UA non conforme
        # se faisait rejeter.
        response = httpx.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "Quizkw-content-generator/1.0 (https://quizclimb.fr; contact: charneas@gmail.com)"},
        )
        if response.status_code == 404:
            raise LookupError(f"Sujet Wikipedia introuvable : '{topic}'")
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as e:
        raise ValueError(f"Échec de l'appel à l'API Wikipedia : {e}") from e

    extract = data.get("extract")
    if not extract:
        raise LookupError(f"Aucun extrait disponible pour le sujet Wikipedia '{topic}'")
    return extract
