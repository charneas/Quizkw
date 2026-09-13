"""Orchestration de l'extraction de playlist (Story 1.1) : détecte le
provider depuis l'URL et délègue l'extraction, sans jamais persister — la
persistance est la responsabilité du router (`main_blindtest.py`), qui décide
du commit une fois `extract_tracks` revenu sans erreur (garantit "pas de
partial write" — AD de la spec).
"""
from typing import List

from app.blindtest.errors import UnrecognizedUrlError
from app.blindtest.extraction_types import ExtractedTrack
from app.blindtest.providers import deezer, youtube

_PROVIDERS = (
    ("youtube", youtube),
    ("deezer", deezer),
)


def detect_provider(url: str) -> str:
    for name, module in _PROVIDERS:
        if module.matches(url):
            return name
    raise UnrecognizedUrlError("URL de playlist non reconnue")


def extract_tracks(url: str) -> tuple[str, List[ExtractedTrack]]:
    """Retourne (provider, tracks). Lève UnrecognizedUrlError,
    PrivatePlaylistError ou ProviderConfigError — jamais d'exception brute de
    provider (httpx, jwt, ...) ne doit fuiter jusqu'ici sans être mappée."""
    provider = detect_provider(url)
    module = dict(_PROVIDERS)[provider]
    tracks = module.fetch_tracks(url)
    return provider, tracks
