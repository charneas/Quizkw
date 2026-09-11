"""File d'attente publique (spec-rooms-publiques, story 1).

Couvre la matrice I/O de la story : 1er/2e/3e/4e joueur, 5e joueur après
assemblage, file périmée (TTL), et non-régression sur le flow Manche 1→2→3.
"""
from datetime import datetime, timedelta, timezone

from app import models
from main_public_queue import PUBLIC_QUEUE_TTL_MINUTES


def _join_public(test_client, name):
    return test_client.post("/games/public/join", json={"name": name})


class TestPublicQueueFirstPlayers:
    def test_first_player_creates_new_public_game(self, test_client):
        response = _join_public(test_client, "Alice")
        assert response.status_code == 200
        data = response.json()
        assert data["game"]["is_public"] is True
        assert data["game"]["players_per_team"] == 1
        assert data["game"]["total_players"] == 4
        assert data["game"]["started"] is False
        assert data["team_id"]
        assert data["team_token"]
        assert data["player_id"]
        assert data["player_token"]
        assert data["code"] == data["game"]["code"]

    def test_second_and_third_player_join_same_game(self, test_client):
        first = _join_public(test_client, "Alice").json()
        second = _join_public(test_client, "Bob").json()
        third = _join_public(test_client, "Carol").json()

        assert second["code"] == first["code"]
        assert third["code"] == first["code"]
        assert second["game"]["started"] is False
        assert third["game"]["started"] is False

    def test_duplicate_pseudo_rejected(self, test_client):
        _join_public(test_client, "Alice")
        response = _join_public(test_client, "alice")  # casse différente
        assert response.status_code == 400


class TestPublicQueuePseudoFilter:
    def test_forbidden_pseudo_rejected(self, test_client):
        response = _join_public(test_client, "connard")
        assert response.status_code == 400

    def test_forbidden_pseudo_rejected_case_insensitive_and_substring(self, test_client):
        response = _join_public(test_client, "SuperConnardDu92")
        assert response.status_code == 400

    def test_normal_pseudo_accepted(self, test_client):
        response = _join_public(test_client, "Alice")
        assert response.status_code == 200

    def test_common_first_names_not_falsely_rejected(self, test_client):
        # Revue de code : "nique"/"viol" en sous-chaîne bloquaient à tort des
        # prénoms courants ("Dominique", "Monique", "Violette", "Violaine").
        for name in ["Dominique", "Monique", "Violette", "Violaine"]:
            response = _join_public(test_client, name)
            assert response.status_code == 200, f"{name} ne devrait pas être rejeté"


class TestPublicQueueAutoStart:
    def test_fourth_player_triggers_auto_start_without_host_token(self, test_client):
        names = ["Alice", "Bob", "Carol", "Dan"]
        responses = [_join_public(test_client, name).json() for name in names]

        code = responses[0]["code"]
        assert all(r["code"] == code for r in responses)
        assert responses[-1]["game"]["started"] is True
        assert responses[-1]["game"]["is_active"] is True
        # Les 3 premiers voient started=False au moment de leur propre requête.
        for r in responses[:3]:
            assert r["game"]["started"] is False

        # Chaque joueur a bien reçu ses propres tokens (équipes-de-1 : pas de
        # partage de token entre inconnus).
        team_tokens = {r["team_token"] for r in responses}
        player_tokens = {r["player_token"] for r in responses}
        assert len(team_tokens) == 4
        assert len(player_tokens) == 4

    def test_fifth_player_after_assembly_creates_new_game(self, test_client):
        names = ["Alice", "Bob", "Carol", "Dan"]
        first_wave = [_join_public(test_client, name).json() for name in names]
        first_code = first_wave[0]["code"]

        fifth = _join_public(test_client, "Eve").json()
        assert fifth["code"] != first_code
        assert fifth["game"]["started"] is False


class TestPublicQueueExpiration:
    def test_stale_queue_is_abandoned_for_a_fresh_one(self, test_client, db_session):
        first = _join_public(test_client, "Alice").json()

        # Simule une file ouverte depuis plus que le TTL, toujours à 1 joueur.
        stale_game = db_session.query(models.GameSession).filter(
            models.GameSession.code == first["code"]
        ).first()
        stale_game.created_at = datetime.now(timezone.utc) - timedelta(
            minutes=PUBLIC_QUEUE_TTL_MINUTES + 1
        )
        db_session.commit()

        second = _join_public(test_client, "Bob").json()
        assert second["code"] != first["code"]


class TestPublicQueueNormalPlay:
    def test_assembled_public_game_progresses_like_a_private_one(self, test_client):
        names = ["Alice", "Bob", "Carol", "Dan"]
        responses = [_join_public(test_client, name).json() for name in names]
        code = responses[0]["code"]

        game = test_client.get(f"/games/{code}").json()
        assert game["current_round"] == "manche_1"
        assert game["started"] is True
        assert game["is_solo_finale"] is False

        # Aucune modification du flow Manche 1→2→3 existant (voir Boundaries) :
        # next-question reste gated par host_token comme pour une partie
        # privée — story hors périmètre pour changer ce point, qui concerne
        # le pilotage de la partie, pas son assemblage.
        response = test_client.post(f"/games/{code}/next-question")
        assert response.status_code == 403
