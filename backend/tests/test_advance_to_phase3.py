"""
Tests de l'endpoint POST /games/{code}/advance-to-phase3.

E-001 (Task 2) : AD-7 exige qu'une transition de phase vérifie que la manche
précédente a réellement eu lieu, et qu'un rejeu (plusieurs finalistes qui
atterrissent en même temps sur l'écran Manche 3 et déclenchent chacun cet
appel) soit sans danger plutôt que de lever une erreur.
"""
from app import models


class TestAdvanceToPhase3:
    def test_rejects_from_manche_1(self, test_client, sample_game_session):
        """La Manche 3 ne peut pas démarrer directement depuis la Manche 1."""
        response = test_client.post(f"/games/{sample_game_session.code}/advance-to-phase3")

        assert response.status_code == 400
        assert "Manche 2" in response.json()["detail"]

    def test_advances_from_manche_2(self, test_client, db_session, sample_game_session):
        sample_game_session.current_round = models.RoundType.MANCHE_2
        db_session.commit()

        response = test_client.post(f"/games/{sample_game_session.code}/advance-to-phase3")

        assert response.status_code == 200
        assert response.json()["current_round"] == "manche_3"

        db_session.refresh(sample_game_session)
        assert sample_game_session.current_round == models.RoundType.MANCHE_3

    def test_idempotent_when_already_in_manche_3(self, test_client, db_session, sample_game_session):
        """Plusieurs finalistes appelant l'endpoint en même temps ne doivent pas échouer."""
        sample_game_session.current_round = models.RoundType.MANCHE_3
        db_session.commit()

        response = test_client.post(f"/games/{sample_game_session.code}/advance-to-phase3")

        assert response.status_code == 200
        assert response.json()["current_round"] == "manche_3"

    def test_unknown_game_returns_404(self, test_client):
        response = test_client.post("/games/DOESNOTEXIST/advance-to-phase3")
        assert response.status_code == 404

    def test_idempotent_even_when_game_no_longer_active(self, test_client, db_session, sample_game_session):
        """Trouvé en revue de code : le garde is_active passait AVANT le garde
        d'idempotence MANCHE_3, si bien qu'un rejeu après désactivation de la
        partie renvoyait "Game is not active" au lieu du no-op attendu."""
        sample_game_session.current_round = models.RoundType.MANCHE_3
        sample_game_session.is_active = False
        db_session.commit()

        response = test_client.post(f"/games/{sample_game_session.code}/advance-to-phase3")

        assert response.status_code == 200
        assert response.json()["current_round"] == "manche_3"

    def test_rejects_from_manche_2_when_game_not_active(self, test_client, db_session, sample_game_session):
        """Le garde is_active reste appliqué pour une vraie transition (pas
        un rejeu idempotent)."""
        sample_game_session.current_round = models.RoundType.MANCHE_2
        sample_game_session.is_active = False
        db_session.commit()

        response = test_client.post(f"/games/{sample_game_session.code}/advance-to-phase3")

        assert response.status_code == 400
        assert "not active" in response.json()["detail"]
