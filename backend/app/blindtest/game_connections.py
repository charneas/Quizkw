"""Gestionnaire de connexions WebSocket en mémoire — Story 2.1.

Aucune persistance : la présence d'un joueur dans une partie est
entièrement dérivée des sockets actuellement ouverts (pas de `Player` DB
table, cf. Design Notes de spec-2-1-lobby-connexion-partie.md). Singleton
au niveau module — acceptable car ce process est la seule instance serveur
(AD, voir epic-2-context.md § Technical Decisions).
"""
from typing import Dict

from fastapi import WebSocket


class ConnectionManager:
    """`{game_code: {pseudo: WebSocket}}`. Un code de partie est toujours
    normalisé en majuscules par l'appelant avant d'atteindre ce gestionnaire
    (le join est insensible à la casse, cf. matrice I/O), donc les clés ici
    sont déjà canoniques.
    """

    def __init__(self) -> None:
        self._games: Dict[str, Dict[str, WebSocket]] = {}

    def connect(self, game_code: str, pseudo: str, websocket: WebSocket) -> None:
        self._games.setdefault(game_code, {})[pseudo] = websocket

    def disconnect(self, game_code: str, pseudo: str) -> None:
        game = self._games.get(game_code)
        if not game:
            return
        game.pop(pseudo, None)
        if not game:
            self._games.pop(game_code, None)

    def has_pseudo(self, game_code: str, pseudo: str) -> bool:
        return pseudo in self._games.get(game_code, {})

    def players(self, game_code: str) -> list[str]:
        return list(self._games.get(game_code, {}).keys())

    async def broadcast_game_state(self, game_code: str) -> None:
        """Envoie `game_state` à tous les sockets actuellement connectés
        pour cette partie. Itère sur une copie de la liste des sockets :
        un envoi qui échoue (socket déjà mort côté client) ne doit pas
        empêcher les autres destinataires de recevoir la mise à jour."""
        game = self._games.get(game_code, {})
        payload = {"players": list(game.keys())}
        for socket in list(game.values()):
            try:
                await socket.send_json(_envelope("game_state", payload))
            except Exception:
                # Le nettoyage du socket mort est géré par le handler WS
                # lui-même (boucle de réception qui détecte la déconnexion),
                # pas ici : on ne fait qu'au mieux pour les destinataires
                # encore joignables.
                continue


def _envelope(msg_type: str, payload: dict) -> dict:
    from datetime import datetime, timezone

    return {
        "type": msg_type,
        "payload": payload,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


manager = ConnectionManager()
