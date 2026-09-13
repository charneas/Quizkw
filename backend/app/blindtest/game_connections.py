"""Gestionnaire de connexions WebSocket en mémoire — Story 2.1.

Aucune persistance : la présence d'un joueur dans une partie est
entièrement dérivée des sockets actuellement ouverts (pas de `Player` DB
table, cf. Design Notes de spec-2-1-lobby-connexion-partie.md). Singleton
au niveau module — acceptable car ce process est la seule instance serveur
(AD, voir epic-2-context.md § Technical Decisions).
"""
from typing import Dict, Optional

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

    async def broadcast_game_state(self, game_code: str, extra: Optional[dict] = None) -> None:
        """Envoie `game_state` à tous les sockets actuellement connectés
        pour cette partie. `extra` (Story 2.4 : `phase`/`host_pseudo`) est
        fusionné dans le payload aux côtés de `players` — implémenté en
        termes de `broadcast` pour ne pas dupliquer la boucle d'envoi."""
        game = self._games.get(game_code, {})
        # `players` est calculé ici et doit toujours gagner si jamais un
        # futur appelant passe une clé `players` dans `extra` (revue de
        # code) — d'où la fusion avec `extra` en premier.
        payload = {**(extra or {}), "players": list(game.keys())}
        await self.broadcast(game_code, "game_state", payload)

    async def broadcast(self, game_code: str, msg_type: str, payload: dict) -> None:
        """Envoie un message arbitraire à tous les sockets actuellement
        connectés pour cette partie. Itère sur une copie de la liste des
        sockets : un envoi qui échoue (socket déjà mort côté client) ne doit
        pas empêcher les autres destinataires de recevoir le message."""
        game = self._games.get(game_code, {})
        for socket in list(game.values()):
            try:
                await socket.send_json(_envelope(msg_type, payload))
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


class GuessStore:
    """`{game_id: {pseudo: [target_player_ids]}}` — stockage en mémoire
    uniquement des devinettes du round en cours (Story 2.5). Même
    convention que `ConnectionManager` : aucune persistance, l'état vit et
    meurt avec le process serveur (pas de `Round`/`Score` DB table, cf.
    Boundaries de spec-2-5-devinette-selection-multiple.md — le scoring
    lui-même est Story 2.6).

    Clé sur `game_id` (entier, PK `Game`) plutôt que sur le code de partie :
    les appelants (`_handle_guess_submitted`/`_handle_start_game`) ont déjà
    l'objet `Game` en main, pas de round-trip supplémentaire pour
    normaliser un code."""

    def __init__(self) -> None:
        self._guesses: Dict[int, Dict[str, list[str]]] = {}

    def submit(self, game_id: int, pseudo: str, target_player_ids: list[str]) -> None:
        """Enregistre la sélection courante de `pseudo` pour ce round,
        écrasant toute sélection précédente du même joueur (AC3 — dernière
        soumission gagne, pas d'accumulation)."""
        self._guesses.setdefault(game_id, {})[pseudo] = target_player_ids

    def reset_round(self, game_id: int) -> None:
        """Vide les devinettes d'un nouveau round tiré (appelé à la fin
        d'un `_handle_start_game` réussi) — Story 2.6/2.7 ne doivent jamais
        scorer contre des devinettes d'un round précédent."""
        self._guesses.pop(game_id, None)

    def get_guess(self, game_id: int, pseudo: str) -> Optional[list[str]]:
        """Lit la devinette stockée de `pseudo` pour le round en cours de
        `game_id`, ou `None` si ce joueur n'a rien soumis (Story 2.6 —
        premier accesseur en lecture, `submit`/`reset_round` suffisaient
        jusqu'ici)."""
        return self._guesses.get(game_id, {}).get(pseudo)

    def known_pseudos(self, game_id: int) -> set[str]:
        """Pseudos ayant une devinette stockée pour le round en cours de
        `game_id` — utilisé par la clôture anticipée (Story 2.6) pour
        détecter que tous les joueurs présents non-propriétaires ont
        répondu."""
        return set(self._guesses.get(game_id, {}).keys())


guess_store = GuessStore()


class ScoreStore:
    """`{game_id: {pseudo: int}}` — score cumulatif en mémoire uniquement
    (Story 2.6), même convention que `GuessStore`/`ConnectionManager` :
    aucune persistance, l'état vit et meurt avec le process serveur (pas de
    `Score` DB table, cf. Boundaries de spec-2-6-reveal-score-cumule.md).
    Contrairement à `GuessStore`, jamais réinitialisé entre rounds — le
    score doit s'accumuler depuis le début de la partie."""

    def __init__(self) -> None:
        self._scores: Dict[int, Dict[str, int]] = {}

    def add(self, game_id: int, pseudo: str, delta: int) -> None:
        """Crée paresseusement l'entrée de `pseudo` à 0 puis ajoute `delta`
        (peut être négatif, pas de plancher à zéro). Appelé aussi avec
        `delta=0` uniquement pour garantir la présence d'un joueur dans le
        snapshot (ex. le propriétaire sur son propre round)."""
        game_scores = self._scores.setdefault(game_id, {})
        game_scores[pseudo] = game_scores.get(pseudo, 0) + delta

    def snapshot(self, game_id: int) -> dict:
        """Copie du score cumulatif de tous les joueurs scorés jusqu'ici
        pour cette partie — payload `reveal.scores`."""
        return dict(self._scores.get(game_id, {}))


score_store = ScoreStore()
