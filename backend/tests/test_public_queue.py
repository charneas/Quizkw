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


def _leave_public(test_client, code, team_id, team_token):
    headers = {"X-Team-Token": team_token} if team_token is not None else {}
    return test_client.delete(f"/games/public/{code}/teams/{team_id}", headers=headers)


def _seat_rows(db_session, team_id):
    return (
        db_session.query(models.Team).filter(models.Team.id == team_id).count(),
        db_session.query(models.Player).filter(models.Player.team_id == team_id).count(),
        db_session.query(models.Token).filter(models.Token.team_id == team_id).count(),
    )


class TestPublicQueueLeave:
    """spec-public-queue-leave : "Annuler" libère la place dans la file."""

    def test_leave_while_waiting_deletes_seat(self, test_client, db_session):
        alice = _join_public(test_client, "Alice").json()
        _join_public(test_client, "Bob")
        _join_public(test_client, "Carol")
        code = alice["code"]
        assert len(test_client.get(f"/games/{code}").json()["teams"]) == 3

        response = _leave_public(test_client, code, alice["team_id"], alice["team_token"])
        assert response.status_code == 204

        assert _seat_rows(db_session, alice["team_id"]) == (0, 0, 0)
        game = test_client.get(f"/games/{code}").json()
        assert len(game["teams"]) == 2
        assert {t["name"] for t in game["teams"]} == {"Bob", "Carol"}

    def test_seat_reusable_after_leave(self, test_client, db_session):
        alice = _join_public(test_client, "Alice").json()
        _join_public(test_client, "Bob")
        _join_public(test_client, "Carol")
        code = alice["code"]
        assert _leave_public(test_client, code, alice["team_id"], alice["team_token"]).status_code == 204

        dan = _join_public(test_client, "Dan").json()
        assert dan["code"] == code
        assert dan["game"]["started"] is False

        eve = _join_public(test_client, "Eve").json()
        assert eve["code"] == code
        assert eve["game"]["started"] is True
        game = db_session.query(models.GameSession).filter(models.GameSession.code == code).first()
        teams = db_session.query(models.Team).filter(models.Team.game_session_id == game.id).all()
        assert len(teams) == 4
        assert {t.name for t in teams} == {"Bob", "Carol", "Dan", "Eve"}

    def test_leave_after_start_rejected(self, test_client, db_session):
        responses = [_join_public(test_client, n).json() for n in ["Alice", "Bob", "Carol", "Dan"]]
        alice = responses[0]
        assert responses[-1]["game"]["started"] is True

        response = _leave_public(test_client, alice["code"], alice["team_id"], alice["team_token"])
        assert response.status_code == 409
        assert _seat_rows(db_session, alice["team_id"]) == (1, 1, 3)

    def test_leave_with_wrong_token_rejected(self, test_client, db_session):
        alice = _join_public(test_client, "Alice").json()
        bob = _join_public(test_client, "Bob").json()

        response = _leave_public(test_client, alice["code"], alice["team_id"], bob["team_token"])
        assert response.status_code == 403
        assert _seat_rows(db_session, alice["team_id"]) == (1, 1, 3)

    def test_leave_with_missing_token_rejected(self, test_client, db_session):
        alice = _join_public(test_client, "Alice").json()

        response = _leave_public(test_client, alice["code"], alice["team_id"], None)
        assert response.status_code == 403
        assert _seat_rows(db_session, alice["team_id"]) == (1, 1, 3)

    def test_leave_unknown_team_same_403(self, test_client):
        alice = _join_public(test_client, "Alice").json()

        response = _leave_public(test_client, alice["code"], 999999, alice["team_token"])
        assert response.status_code == 403

    def test_leave_with_code_of_another_game_rejected(self, test_client, db_session):
        alice = _join_public(test_client, "Alice").json()
        other = models.GameSession(code="OTHER1", total_players=4, players_per_team=1,
                                   current_round=models.RoundType.MANCHE_1, is_active=True,
                                   started=False, is_public=True)
        db_session.add(other)
        db_session.commit()

        response = _leave_public(test_client, "OTHER1", alice["team_id"], alice["team_token"])
        assert response.status_code == 403
        assert _seat_rows(db_session, alice["team_id"]) == (1, 1, 3)

    def test_leave_private_game_rejected(self, test_client, db_session):
        game = models.GameSession(code="PRIV01", total_players=4, players_per_team=1,
                                  current_round=models.RoundType.MANCHE_1, is_active=True,
                                  started=False, is_public=False)
        db_session.add(game)
        db_session.flush()
        team = models.Team(name="Alice", game_session_id=game.id, score=0)
        db_session.add(team)
        db_session.flush()
        db_session.add(models.Player(name="Alice", team_id=team.id))
        for token_type in (models.TokenType.SWAP, models.TokenType.PENALTY, models.TokenType.BONUS):
            db_session.add(models.Token(team_id=team.id, token_type=token_type, is_used=False))
        db_session.commit()

        response = _leave_public(test_client, "PRIV01", team.id, team.team_token)
        assert response.status_code == 409
        assert _seat_rows(db_session, team.id) == (1, 1, 3)
