"""BUG-101d : /tokens/use acceptait un team_id non authentifié — n'importe
quel client connaissant (ou devinant) un team_id valide pouvait consommer les
jetons SWAP/PENALTY/BONUS d'une équipe qui n'est pas la sienne. team_token
(généré à la création de l'équipe, renvoyé par create_team et join_team)
authentifie désormais l'appelant sur cet endpoint. join_team reste public
(pas de vérification pour rejoindre une équipe existante — décision produit
documentée sur #55) : la protection porte sur qui peut consommer les jetons,
pas sur qui peut rejoindre l'équipe."""
from app import models


def test_use_token_rejected_without_team_token_header(test_client, db_session, sample_game_session):
    team = models.Team(name="Team A", game_session_id=sample_game_session.id, score=0)
    db_session.add(team)
    db_session.commit()
    db_session.add(models.Token(team_id=team.id, token_type=models.TokenType.BONUS, is_used=False))
    db_session.commit()

    resp = test_client.post("/tokens/use", json={"team_id": team.id, "token_type": "BONUS"})
    assert resp.status_code == 403

    db_session.refresh(team)
    assert team.bonus_active is False


def test_use_token_rejected_with_wrong_team_token(test_client, db_session, sample_game_session):
    team = models.Team(name="Team A", game_session_id=sample_game_session.id, score=0)
    other_team = models.Team(name="Team B", game_session_id=sample_game_session.id, score=0)
    db_session.add_all([team, other_team])
    db_session.commit()
    db_session.add(models.Token(team_id=team.id, token_type=models.TokenType.BONUS, is_used=False))
    db_session.commit()

    # Un client qui connaît le team_id de "Team A" mais présente le token
    # d'une autre équipe ("Team B") ne peut pas consommer ses jetons.
    resp = test_client.post(
        "/tokens/use",
        json={"team_id": team.id, "token_type": "BONUS"},
        headers={"X-Team-Token": other_team.team_token},
    )
    assert resp.status_code == 403

    db_session.refresh(team)
    assert team.bonus_active is False


def test_use_token_accepted_with_correct_team_token(test_client, db_session, sample_game_session):
    team = models.Team(name="Team A", game_session_id=sample_game_session.id, score=0)
    db_session.add(team)
    db_session.commit()
    db_session.add(models.Token(team_id=team.id, token_type=models.TokenType.BONUS, is_used=False))
    db_session.commit()

    resp = test_client.post(
        "/tokens/use",
        json={"team_id": team.id, "token_type": "BONUS"},
        headers={"X-Team-Token": team.team_token},
    )
    assert resp.status_code == 200

    db_session.refresh(team)
    assert team.bonus_active is True


def test_create_team_returns_team_token(test_client, sample_game_session):
    resp = test_client.post(f"/games/{sample_game_session.code}/teams/", json={"name": "Les Foudroyants"})
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body.get("team_token"), str) and len(body["team_token"]) > 10


def test_join_team_returns_same_team_token_as_creation(test_client, sample_game_session):
    create_resp = test_client.post(f"/games/{sample_game_session.code}/teams/", json={"name": "Les Foudroyants"})
    team = create_resp.json()

    join_resp = test_client.post(
        f"/games/{sample_game_session.code}/teams/{team['id']}/players/",
        json={"name": "Bob"},
    )
    assert join_resp.status_code == 200
    assert join_resp.json()["team_token"] == team["team_token"]


def test_team_token_never_appears_in_public_game_state(test_client, sample_game_session):
    """team_token authentifie l'appelant sur /tokens/use : il ne doit jamais
    apparaître dans une réponse visible par d'autres joueurs (état de partie,
    liste d'équipes adverses), sous peine d'annuler la protection."""
    create_resp = test_client.post(f"/games/{sample_game_session.code}/teams/", json={"name": "Les Foudroyants"})
    assert create_resp.status_code == 200

    game_resp = test_client.get(f"/games/{sample_game_session.code}")
    assert game_resp.status_code == 200
    assert "team_token" not in str(game_resp.json())


def test_use_token_rejected_with_token_from_different_game_session(test_client, db_session):
    game1 = models.GameSession(code="GAMEONE", total_players=8, players_per_team=2, is_active=True)
    game2 = models.GameSession(code="GAMETWO", total_players=8, players_per_team=2, is_active=True)
    db_session.add_all([game1, game2])
    db_session.commit()

    team_in_game2 = models.Team(name="Intrus", game_session_id=game2.id, score=0)
    db_session.add(team_in_game2)
    db_session.commit()

    team_in_game1 = models.Team(name="Cible", game_session_id=game1.id, score=0)
    db_session.add(team_in_game1)
    db_session.commit()
    db_session.add(models.Token(team_id=team_in_game1.id, token_type=models.TokenType.BONUS, is_used=False))
    db_session.commit()

    # Le token d'une équipe d'une AUTRE partie ne doit pas passer, même s'il
    # est structurellement valide (comparaison sur le bon custodian, pas
    # juste "un token connu quelconque").
    resp = test_client.post(
        "/tokens/use",
        json={"team_id": team_in_game1.id, "token_type": "BONUS"},
        headers={"X-Team-Token": team_in_game2.team_token},
    )
    assert resp.status_code == 403


def test_use_token_rejected_with_non_integer_team_id(test_client, sample_game_session):
    resp = test_client.post(
        "/tokens/use",
        json={"team_id": "not-an-id", "token_type": "BONUS"},
        headers={"X-Team-Token": "whatever"},
    )
    assert resp.status_code == 400


def test_use_token_returns_same_status_for_unknown_team_and_wrong_token(test_client, db_session, sample_game_session):
    """404 sur une équipe inconnue mais 403 sur une équipe connue avec le
    mauvais token laisserait un appelant non authentifié énumérer les
    team_id valides — exactement ce que ce token doit empêcher."""
    team = models.Team(name="Team A", game_session_id=sample_game_session.id, score=0)
    db_session.add(team)
    db_session.commit()

    unknown_team_id = team.id + 999999

    unknown_resp = test_client.post(
        "/tokens/use",
        json={"team_id": unknown_team_id, "token_type": "BONUS"},
        headers={"X-Team-Token": "whatever"},
    )
    wrong_token_resp = test_client.post(
        "/tokens/use",
        json={"team_id": team.id, "token_type": "BONUS"},
        headers={"X-Team-Token": "whatever"},
    )
    assert unknown_resp.status_code == wrong_token_resp.status_code == 403
