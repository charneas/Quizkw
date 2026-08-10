"""
Vue consolidée des tours de roue déjà joués (BUG-106, #8).
"""
from app import models


def _make_team(db_session, game, name, score=5):
    team = models.Team(name=name, game_session_id=game.id, score=score)
    db_session.add(team)
    db_session.commit()
    db_session.refresh(team)
    return team


def _make_effect(db_session, game, team, effect_type, value=None):
    effect = models.WheelEffect(
        game_session_id=game.id,
        effect_type=effect_type,
        value=value,
        target_team_id=team.id,
        is_applied=True,
    )
    db_session.add(effect)
    db_session.commit()
    db_session.refresh(effect)
    return effect


class TestWheelHistory:
    def test_history_is_chronological_and_messaged(self, test_client, db_session, sample_game_session):
        team1 = _make_team(db_session, sample_game_session, "Team A")
        team2 = _make_team(db_session, sample_game_session, "Team B")

        first = _make_effect(db_session, sample_game_session, team1, "malus", -3)
        second = _make_effect(db_session, sample_game_session, team2, "bonus", 3)

        response = test_client.get(f"/games/{sample_game_session.code}/wheel-history")
        assert response.status_code == 200
        history = response.json()["history"]

        assert len(history) == 2
        assert [h["id"] for h in history] == [first.id, second.id]
        assert history[0]["target_team_name"] == "Team A"
        assert "Malus" in history[0]["message"]
        assert history[1]["target_team_name"] == "Team B"
        assert "Bonus" in history[1]["message"]

    def test_history_excludes_token_effects(self, test_client, db_session, sample_game_session):
        team1 = _make_team(db_session, sample_game_session, "Team A")
        _make_effect(db_session, sample_game_session, team1, "malus", -3)
        _make_effect(db_session, sample_game_session, team1, "TOKEN_SWAP")

        response = test_client.get(f"/games/{sample_game_session.code}/wheel-history")
        history = response.json()["history"]

        assert len(history) == 1
        assert history[0]["effect_type"] == "malus"

    def test_history_empty_when_no_effects(self, test_client, db_session, sample_game_session):
        response = test_client.get(f"/games/{sample_game_session.code}/wheel-history")
        assert response.status_code == 200
        assert response.json() == {"history": []}

    def test_history_missing_game_returns_404(self, test_client):
        response = test_client.get("/games/DOESNOTEXIST/wheel-history")
        assert response.status_code == 404

    def test_history_scoped_to_its_own_game(self, test_client, db_session, sample_game_session):
        other_game = models.GameSession(
            code="OTHERWHEEL", total_players=4, players_per_team=2,
            current_round=models.RoundType.MANCHE_1, is_active=True,
        )
        db_session.add(other_game)
        db_session.commit()
        db_session.refresh(other_game)

        team_other = _make_team(db_session, other_game, "Team X")
        _make_effect(db_session, other_game, team_other, "malus", -3)

        response = test_client.get(f"/games/{sample_game_session.code}/wheel-history")
        assert response.json() == {"history": []}