"""Tests pour la suppression de compte en libre-service (Epic O, Story O.3.1,
RGPD/FR6/NFR1). `DELETE /account` supprime immédiatement la ligne `Account` —
jamais un flag de désactivation — et laisse orphelins les `Player`/`Answer`
déjà rattachés (`account_id` mis à NULL par la contrainte DB ON DELETE SET
NULL, AD-21)."""
from itsdangerous import URLSafeSerializer

from app import models
from app.account_manager import resolve_or_create_account

DISCORD_SESSION_SECRET_KEY = "test-discord-secret-key-not-for-production"


def _signed_discord_cookie(discord_id: str) -> str:
    return URLSafeSerializer(DISCORD_SESSION_SECRET_KEY, salt="discord-session").dumps({"discord_id": discord_id})


def _make_account(db_session, discord_id: str, pseudo: str = "TestPlayer") -> models.Account:
    return resolve_or_create_account(db_session, discord_id=discord_id, pseudo=pseudo, avatar=None)


def test_delete_account_without_cookie_returns_401(test_client):
    resp = test_client.delete("/account")
    assert resp.status_code == 401


def test_delete_account_removes_account_row_immediately(test_client, db_session):
    account = _make_account(db_session, "801")
    account_id = account.id
    test_client.cookies.set("discord_session", _signed_discord_cookie("801"))

    resp = test_client.delete("/account")
    assert resp.status_code == 200

    assert db_session.query(models.Account).filter(models.Account.id == account_id).first() is None


def test_delete_account_clears_session_cookie(test_client, db_session):
    _make_account(db_session, "802")
    test_client.cookies.set("discord_session", _signed_discord_cookie("802"))

    resp = test_client.delete("/account")
    assert resp.status_code == 200
    set_cookie = resp.headers.get("set-cookie", "")
    assert 'discord_session=""' in set_cookie or "discord_session=;" in set_cookie
    assert "Max-Age=0" in set_cookie or "max-age=0" in set_cookie.lower()


def test_delete_account_orphans_player_and_answer_via_db_constraint(test_client, db_session, sample_theme):
    account = _make_account(db_session, "803")
    game = models.GameSession(code="DELGAME", total_players=8, players_per_team=2, is_active=True)
    db_session.add(game)
    db_session.commit()
    db_session.refresh(game)
    team = models.Team(name="Equipe Del", game_session_id=game.id, score=0)
    db_session.add(team)
    db_session.commit()
    db_session.refresh(team)
    player = models.Player(name="Joueur", team_id=team.id, account_id=account.id)
    db_session.add(player)
    db_session.commit()
    db_session.refresh(player)
    player_id = player.id

    question = models.Question(
        text="Q",
        category="Test",
        difficulty=models.Difficulty.EASY,
        points=2,
        correct_answer="ok",
        wrong_answers="[]",
        theme_id=sample_theme.id,
    )
    db_session.add(question)
    db_session.commit()
    db_session.refresh(question)
    answer = models.Answer(question_id=question.id, team_id=team.id, player_answer="ok", is_correct=True, points_earned=2)
    db_session.add(answer)
    db_session.commit()

    test_client.cookies.set("discord_session", _signed_discord_cookie("803"))
    resp = test_client.delete("/account")
    assert resp.status_code == 200

    db_session.expire_all()
    survivor = db_session.query(models.Player).filter(models.Player.id == player_id).first()
    assert survivor is not None
    assert survivor.account_id is None


def test_delete_account_then_reconnect_with_same_discord_id_creates_fresh_account(test_client, db_session):
    # Note : SQLite peut réattribuer le même id après suppression de l'unique
    # ligne de la table (pas d'AUTOINCREMENT) — comparer l'id serait donc un
    # faux négatif propre à ce moteur de test. Ce qui compte pour l'AC (aucun
    # historique récupéré) est qu'aucun Player ne reste lié à ce nouveau
    # compte : la seule attribution passée est passée avec l'ancien.
    account = _make_account(db_session, "804", pseudo="Ancien")
    game = models.GameSession(code="RECOGAME", total_players=8, players_per_team=2, is_active=True)
    db_session.add(game)
    db_session.commit()
    db_session.refresh(game)
    team = models.Team(name="Equipe Reco", game_session_id=game.id, score=0)
    db_session.add(team)
    db_session.commit()
    db_session.refresh(team)
    old_player = models.Player(name="Ancien Joueur", team_id=team.id, account_id=account.id)
    db_session.add(old_player)
    db_session.commit()
    db_session.refresh(old_player)
    old_player_id = old_player.id

    test_client.cookies.set("discord_session", _signed_discord_cookie("804"))
    resp = test_client.delete("/account")
    assert resp.status_code == 200

    new_account = resolve_or_create_account(db_session, discord_id="804", pseudo="Nouveau", avatar=None)

    db_session.expire_all()
    orphan = db_session.query(models.Player).filter(models.Player.id == old_player_id).first()
    assert orphan.account_id is None

    new_players = db_session.query(models.Player).filter(models.Player.account_id == new_account.id).all()
    assert new_players == []
