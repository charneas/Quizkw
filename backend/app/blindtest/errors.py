"""Erreurs typées de l'extraction de playlist — traduites en codes HTTP par
`main_blindtest.py`. Séparées de `import_pipeline.py` pour que les modules
providers puissent les importer sans dépendre de l'orchestration.
"""


class UnrecognizedUrlError(Exception):
    """L'URL ne correspond à aucun provider connu, ou pointe vers autre chose
    qu'une playlist (ex. un lien de morceau)."""


class PrivatePlaylistError(Exception):
    """Le provider a répondu 403/404 : playlist privée, supprimée, ou
    inexistante."""


class ProviderUnavailableError(Exception):
    """Le provider est injoignable ou répond de façon inexploitable (réseau,
    5xx, 429, quota épuisé, corps non-JSON) : panne côté provider, pas un
    problème avec la playlist de l'utilisateur."""

    def __init__(self, provider: str, reason: str):
        self.provider = provider
        self.reason = reason
        super().__init__(f"{provider} indisponible : {reason}")


class ProviderConfigError(Exception):
    """Credentials applicatifs manquants/invalides pour ce provider."""

    def __init__(self, provider: str, missing: str):
        self.provider = provider
        self.missing = missing
        super().__init__(f"Configuration manquante pour {provider}: {missing}")
