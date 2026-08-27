"""Tests pour l'attribution des réponses au Compte (Epic O, Story O.2.1).
Player.account_id écrit une seule fois à la création (join_team/create_player),
résolution silencieuse par cookie Discord — jamais d'erreur en mode invité."""
import os

from itsdangerous import URLSafeSerializer

from app import models
from app.account_manager import resolve_account_from_discord_id, resolve_or_create_account

DISCORD_SESSION_SECRET_KEY = "test-discord-secret-key-not-for-production"


def _signed_discord_cookie(discord_id: str) -> str:
    return URLSafeSerializer(DISCORD_SESSION_SECRET_KEY, salt="discord-session").dumps({"discord_id": discord_id})


def _make_account(db_session, discord_id: str, pseudo: str = "TestPlayer") -> models.Account:
    return resolve_or_create_account(db_session, discord_id=discord_id, pseudo=pseudo, avatar=None)


def _make_game_and_team(db_session, code="GAME01"):
    game = models.GameSession(code=code, total_players=8, players_per_team=2, is_active=True)
    db_session.add(game)
    db_session.commit()
    db_session.refresh(game)
    team = models.Team(name="Equipe A", game_session_id=game.id, score=0)
    db_session.add(team)
    db_session.commit()
    db_session.refresh(team)
    return game, team


# === join_team ===

def test_join_team_with_valid_discord_cookie_sets_account_id(test_client, db_session):
    account = _make_account(db_session, "111")
    game, team = _make_game_and_team(db_session)
    test_client.cookies.set("discord_session", _signed_discord_cookie("111"))

    resp = test_client.post(f"/games/{game.code}/teams/{team.id}/players/", json={"name": "Alice"})
    assert resp.status_code == 200

    player = db_session.query(models.Player).filter(models.Player.name == "Alice").first()
    assert player.account_id == account.id


def test_join_team_without_cookie_leaves_account_id_null(test_client, db_session):
    game, team = _make_game_and_team(db_session)

    resp = test_client.post(f"/games/{game.code}/teams/{team.id}/players/", json={"name": "Bob"})
    assert resp.status_code == 200

    player = db_session.query(models.Player).filter(models.Player.name == "Bob").first()
    assert player.account_id is None


def test_join_team_with_tampered_cookie_leaves_account_id_null_no_500(test_client, db_session):
    game, team = _make_game_and_team(db_session)
    test_client.cookies.set("discord_session", "tampered.invalid.signature")

    resp = test_client.post(f"/games/{game.code}/teams/{team.id}/players/", json={"name": "Carol"})
    assert resp.status_code == 200

    player = db_session.query(models.Player).filter(models.Player.name == "Carol").first()
    assert player.account_id is None


def test_join_team_without_discord_config_still_creates_guest_player(test_client, db_session):
    game, team = _make_game_and_team(db_session)
    test_client.cookies.set("discord_session", _signed_discord_cookie("222"))

    original = os.environ.pop("DISCORD_SESSION_SECRET_KEY", None)
    try:
        resp = test_client.post(f"/games/{game.code}/teams/{team.id}/players/", json={"name": "Dave"})
        assert resp.status_code == 200
        player = db_session.query(models.Player).filter(models.Player.name == "Dave").first()
        assert player.account_id is None
    finally:
        if original is not None:
            os.environ["DISCORD_SESSION_SECRET_KEY"] = original


# === create_player (Round 2) ===

def test_create_player_with_valid_discord_cookie_sets_account_id(test_client, db_session):
    account = _make_account(db_session, "333")
    game, _ = _make_game_and_team(db_session, code="GAME02")
    test_client.cookies.set("discord_session", _signed_discord_cookie("333"))

    resp = test_client.post(f"/games/{game.code}/players/", json={"name": "Eve"})
    assert resp.status_code == 200

    player = db_session.query(models.Player).filter(models.Player.name == "Eve").first()
    assert player.account_id == account.id


def test_create_player_without_cookie_leaves_account_id_null(test_client, db_session):
    game, _ = _make_game_and_team(db_session, code="GAME03")

    resp = test_client.post(f"/games/{game.code}/players/", json={"name": "Frank"})
    assert resp.status_code == 200

    player = db_session.query(models.Player).filter(models.Player.name == "Frank").first()
    assert player.account_id is None


def test_create_player_with_tampered_cookie_leaves_account_id_null_no_500(test_client, db_session):
    game, _ = _make_game_and_team(db_session, code="GAME04")
    test_client.cookies.set("discord_session", "tampered.invalid.signature")

    resp = test_client.post(f"/games/{game.code}/players/", json={"name": "Gina"})
    assert resp.status_code == 200

    player = db_session.query(models.Player).filter(models.Player.name == "Gina").first()
    assert player.account_id is None


def test_create_player_without_discord_config_still_creates_guest_player(test_client, db_session):
    game, _ = _make_game_and_team(db_session, code="GAME05")
    test_client.cookies.set("discord_session", _signed_discord_cookie("444"))

    original = os.environ.pop("DISCORD_SESSION_SECRET_KEY", None)
    try:
        resp = test_client.post(f"/games/{game.code}/players/", json={"name": "Hank"})
        assert resp.status_code == 200
        player = db_session.query(models.Player).filter(models.Player.name == "Hank").first()
        assert player.account_id is None
    finally:
        if original is not None:
            os.environ["DISCORD_SESSION_SECRET_KEY"] = original


# === resolve_account_from_discord_id ===

def test_resolve_account_from_discord_id_returns_none_for_unknown_discord_id(db_session):
    assert resolve_account_from_discord_id(db_session, "does-not-exist") is None
