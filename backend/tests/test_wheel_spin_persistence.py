"""
Persistance et diffusion réelle des effets de la roue (story J.004, BUG-111).

Playtest 2026-07-31 : la roue ne s'affichait que pour le host — en réalité
POST /wheel/spin ne persistait rien en base et n'appliquait aucun score
(contrairement à trigger_wheel_effect, qui fonctionne correctement mais
n'est jamais déclenché par le host). Cette story fait persister spin_wheel
de la même façon, pour que last_wheel_event (déjà diffusé à toutes les
équipes) reflète un effet réel.
"""
from unittest.mock import patch

from app import models


def _make_team(db_session, game, name, score=5):
    team = models.Team(name=name, game_session_id=game.id, score=score)
    db_session.add(team)
    db_session.commit()
    db_session.refresh(team)
    return team


class TestWheelSpinPersistence:
    def test_malus_applies_score_and_persists_effect(self, test_client, db_session, sample_game_session):
        team1 = _make_team(db_session, sample_game_session, "Team A", score=5)
        _make_team(db_session, sample_game_session, "Team B")

        with patch("main.random.randint", return_value=3):
            response = test_client.post("/wheel/spin", json={"team_id": team1.id})

        assert response.status_code == 200
        data = response.json()
        assert data == {"effect_type": "malus", "value": -3, "message": "Résultat 3: Malus de 3 points"}

        db_session.expire_all()
        refreshed = db_session.query(models.Team).filter(models.Team.id == team1.id).first()
        assert refreshed.score == 2

        effect = db_session.query(models.WheelEffect).filter(
            models.WheelEffect.game_session_id == sample_game_session.id
        ).order_by(models.WheelEffect.id.desc()).first()
        assert effect is not None
        assert effect.effect_type == "malus"
        assert effect.value == -3
        assert effect.target_team_id == team1.id
        assert effect.is_applied is True

    def test_malus_floors_score_at_zero(self, test_client, db_session, sample_game_session):
        team1 = _make_team(db_session, sample_game_session, "Team A", score=1)
        _make_team(db_session, sample_game_session, "Team B")

        with patch("main.random.randint", return_value=1):
            response = test_client.post("/wheel/spin", json={"team_id": team1.id})

        assert response.status_code == 200
        db_session.expire_all()
        refreshed = db_session.query(models.Team).filter(models.Team.id == team1.id).first()
        assert refreshed.score == 0

    def test_bonus_19_20_applies_three_points(self, test_client, db_session, sample_game_session):
        team1 = _make_team(db_session, sample_game_session, "Team A", score=5)
        _make_team(db_session, sample_game_session, "Team B")

        with patch("main.random.randint", return_value=20):
            response = test_client.post("/wheel/spin", json={"team_id": team1.id})

        assert response.status_code == 200
        assert response.json() == {"effect_type": "bonus", "value": 3, "message": "Résultat 20: Bonus de 3 points!"}

        db_session.expire_all()
        refreshed = db_session.query(models.Team).filter(models.Team.id == team1.id).first()
        assert refreshed.score == 8

    def test_result_6_to_10_auto_resolves_to_one_point_bonus(self, test_client, db_session, sample_game_session):
        """Pas de branche 'choice' : jamais arbitrable côté UI (WheelModal.tsx)."""
        team1 = _make_team(db_session, sample_game_session, "Team A", score=5)
        _make_team(db_session, sample_game_session, "Team B")

        with patch("main.random.randint", return_value=8):
            response = test_client.post("/wheel/spin", json={"team_id": team1.id})

        assert response.status_code == 200
        data = response.json()
        assert data["effect_type"] == "bonus"
        assert data["value"] == 1

        db_session.expire_all()
        refreshed = db_session.query(models.Team).filter(models.Team.id == team1.id).first()
        assert refreshed.score == 6

    def test_ping_pong_result_does_not_change_score(self, test_client, db_session, sample_game_session):
        team1 = _make_team(db_session, sample_game_session, "Team A", score=5)
        _make_team(db_session, sample_game_session, "Team B")

        with patch("main.random.randint", return_value=15):
            response = test_client.post("/wheel/spin", json={"team_id": team1.id})

        assert response.status_code == 200
        data = response.json()
        assert data["effect_type"] == "ping_pong"
        assert data["value"] is None

        db_session.expire_all()
        refreshed = db_session.query(models.Team).filter(models.Team.id == team1.id).first()
        assert refreshed.score == 5

        effect = db_session.query(models.WheelEffect).filter(
            models.WheelEffect.game_session_id == sample_game_session.id
        ).order_by(models.WheelEffect.id.desc()).first()
        assert effect.effect_type == "ping_pong"
        assert effect.value is None

    def test_ping_pong_result_falls_back_to_bonus_when_no_opponent(self, test_client, db_session, sample_game_session):
        team1 = _make_team(db_session, sample_game_session, "Solo Team", score=5)

        with patch("main.random.randint", return_value=15):
            response = test_client.post("/wheel/spin", json={"team_id": team1.id})

        assert response.status_code == 200
        data = response.json()
        assert data["effect_type"] == "bonus"
        assert data["value"] == 2

        db_session.expire_all()
        refreshed = db_session.query(models.Team).filter(models.Team.id == team1.id).first()
        assert refreshed.score == 7

    def test_spin_broadcast_to_other_teams_via_last_wheel_event(self, test_client, db_session, sample_game_session):
        team1 = _make_team(db_session, sample_game_session, "Team A", score=5)
        team2 = _make_team(db_session, sample_game_session, "Team B", score=5)

        with patch("main.random.randint", return_value=20):
            spin_response = test_client.post("/wheel/spin", json={"team_id": team1.id})
        assert spin_response.status_code == 200

        # AC #2 : une AUTRE équipe (pas celle qui a tourné) voit l'événement.
        state_response = test_client.get(f"/game/{sample_game_session.code}/team/{team2.id}/state")
        assert state_response.status_code == 200
        event = state_response.json()["last_wheel_event"]
        assert event is not None
        assert event["effect_type"] == "bonus"
        assert event["value"] == 3
        assert event["target_team_id"] == team1.id
        assert event["target_team_name"] == "Team A"

    def test_spin_unknown_team_returns_404(self, test_client, db_session, sample_game_session):
        response = test_client.post("/wheel/spin", json={"team_id": 999999})
        assert response.status_code == 404

    def test_response_schema_has_no_extra_fields(self, test_client, db_session, sample_game_session):
        """AC #4 : régression de contrat — pas de champ ajouté à WheelSpinResponse."""
        team1 = _make_team(db_session, sample_game_session, "Team A", score=5)
        _make_team(db_session, sample_game_session, "Team B")

        with patch("main.random.randint", return_value=20):
            response = test_client.post("/wheel/spin", json={"team_id": team1.id})

        assert response.status_code == 200
        assert set(response.json().keys()) == {"effect_type", "value", "message"}