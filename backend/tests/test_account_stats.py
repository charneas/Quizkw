"""Tests pour l'agrégation des statistiques personnelles par thème (Epic O,
Story O.2.2, AD-20). Calcul à la lecture, fusion Manche 1 (Answer, attribué à
chaque joueur de l'équipe) + Round 2 (PlayerRound2Stats, déjà individuel)."""
import json

from itsdangerous import URLSafeSerializer

from app import models
from app.account_manager import resolve_or_create_account
from app.account_stats import compute_account_stats

DISCORD_SESSION_SECRET_KEY = "test-discord-secret-key-not-for-production"


def _signed_discord_cookie(discord_id: str) -> str:
    return URLSafeSerializer(DISCORD_SESSION_SECRET_KEY, salt="discord-session").dumps({"discord_id": discord_id})


def _make_account(db_session, discord_id: str, pseudo: str = "TestPlayer") -> models.Account:
    return resolve_or_create_account(db_session, discord_id=discord_id, pseudo=pseudo, avatar=None)


def _make_game_and_team(db_session, code="STATGAME"):
    game = models.GameSession(code=code, total_players=8, players_per_team=2, is_active=True)
    db_session.add(game)
    db_session.commit()
    db_session.refresh(game)
    team = models.Team(name="Equipe Stats", game_session_id=game.id, score=0)
    db_session.add(team)
    db_session.commit()
    db_session.refresh(team)
    return game, team


def _make_player(db_session, team_id, account_id=None, name="Joueur"):
    player = models.Player(name=name, team_id=team_id, account_id=account_id)
    db_session.add(player)
    db_session.commit()
    db_session.refresh(player)
    return player


def _make_question(db_session, theme_id, number):
    question = models.Question(
        text=f"Question {number}",
        category="Test",
        difficulty=models.Difficulty.EASY,
        points=2,
        correct_answer="bonne reponse",
        wrong_answers=json.dumps(["a", "b", "c"]),
        theme_id=theme_id,
        question_number=number,
    )
    db_session.add(question)
    db_session.commit()
    db_session.refresh(question)
    return question


def _make_answer(db_session, question_id, team_id, is_correct):
    answer = models.Answer(
        question_id=question_id,
        team_id=team_id,
        player_answer="reponse",
        is_correct=is_correct,
        points_earned=0,
    )
    db_session.add(answer)
    db_session.commit()


def _make_round2_stats(db_session, player_id, game_session_id, theme_id, correct, answered):
    stats = models.PlayerRound2Stats(
        player_id=player_id,
        game_session_id=game_session_id,
        theme_id=theme_id,
        correct_answers=correct,
        questions_answered=answered,
        qualification_status=models.QualificationStatus.PLAYING,
    )
    db_session.add(stats)
    db_session.commit()


# === GET /account/stats ===

def test_account_stats_without_cookie_returns_401(test_client):
    resp = test_client.get("/account/stats")
    assert resp.status_code == 401


def test_account_stats_with_no_games_returns_zero_general_no_division_by_zero(test_client, db_session):
    _make_account(db_session, "700")
    test_client.cookies.set("discord_session", _signed_discord_cookie("700"))

    resp = test_client.get("/account/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["general"]["personal_total"] == 0
    assert data["general"]["personal_correct"] == 0
    assert data["themes"] == []


def test_account_stats_manche1_attributes_team_answers_to_every_teammate(test_client, db_session, sample_theme):
    account = _make_account(db_session, "701")
    game, team = _make_game_and_team(db_session)
    _make_player(db_session, team.id, account_id=account.id, name="Alice")
    _make_player(db_session, team.id, account_id=None, name="Bob")  # coéquipier invité

    q1 = _make_question(db_session, sample_theme.id, 1)
    q2 = _make_question(db_session, sample_theme.id, 2)
    _make_answer(db_session, q1.id, team.id, is_correct=True)
    _make_answer(db_session, q2.id, team.id, is_correct=False)

    test_client.cookies.set("discord_session", _signed_discord_cookie("701"))
    resp = test_client.get("/account/stats")
    assert resp.status_code == 200
    data = resp.json()
    theme = next(t for t in data["themes"] if t["theme_id"] == sample_theme.id)
    assert theme["personal_total"] == 2
    assert theme["personal_correct"] == 1


def test_account_stats_merges_manche1_and_round2_on_same_theme(test_client, db_session, sample_theme):
    account = _make_account(db_session, "702")
    game, team = _make_game_and_team(db_session)
    player = _make_player(db_session, team.id, account_id=account.id)

    for i in range(6):
        q = _make_question(db_session, sample_theme.id, i)
        _make_answer(db_session, q.id, team.id, is_correct=True)
    for i in range(6, 10):
        q = _make_question(db_session, sample_theme.id, i)
        _make_answer(db_session, q.id, team.id, is_correct=False)

    _make_round2_stats(db_session, player.id, game.id, sample_theme.id, correct=10, answered=20)

    test_client.cookies.set("discord_session", _signed_discord_cookie("702"))
    resp = test_client.get("/account/stats")
    data = resp.json()
    theme = next(t for t in data["themes"] if t["theme_id"] == sample_theme.id)
    assert theme["personal_total"] == 30  # 10 (Manche 1) + 20 (Round 2)
    assert theme["personal_correct"] == 16  # 6 + 10
    assert theme["insufficient_data"] is False


def test_account_stats_theme_below_threshold_flagged_insufficient_data(test_client, db_session, sample_theme):
    account = _make_account(db_session, "703")
    game, team = _make_game_and_team(db_session)
    _make_player(db_session, team.id, account_id=account.id)

    for i in range(3):
        q = _make_question(db_session, sample_theme.id, i)
        _make_answer(db_session, q.id, team.id, is_correct=True)

    test_client.cookies.set("discord_session", _signed_discord_cookie("703"))
    resp = test_client.get("/account/stats")
    data = resp.json()
    theme = next(t for t in data["themes"] if t["theme_id"] == sample_theme.id)
    assert theme["personal_total"] == 3
    assert theme["insufficient_data"] is True


def test_account_stats_global_is_not_filtered_by_account_and_not_duplicated_per_teammate(test_client, db_session, sample_theme):
    account_a = _make_account(db_session, "704", pseudo="A")
    _make_account(db_session, "705", pseudo="B")
    game, team = _make_game_and_team(db_session)
    # Deux coéquipiers, dont un invité — le global ne doit compter chaque
    # Answer qu'une seule fois, jamais une fois par joueur de l'équipe.
    _make_player(db_session, team.id, account_id=account_a.id, name="A")
    _make_player(db_session, team.id, account_id=None, name="Guest")

    q = _make_question(db_session, sample_theme.id, 1)
    _make_answer(db_session, q.id, team.id, is_correct=True)

    test_client.cookies.set("discord_session", _signed_discord_cookie("704"))
    resp = test_client.get("/account/stats")
    data = resp.json()
    theme = next(t for t in data["themes"] if t["theme_id"] == sample_theme.id)
    assert theme["global_total"] == 1
    assert theme["global_correct"] == 1


def test_account_stats_guest_player_never_appears_in_another_accounts_personal_stat(test_client, db_session, sample_theme):
    account = _make_account(db_session, "706")
    game, team = _make_game_and_team(db_session)
    _make_player(db_session, team.id, account_id=None, name="Guest")  # aucun compte connecté

    q = _make_question(db_session, sample_theme.id, 1)
    _make_answer(db_session, q.id, team.id, is_correct=True)

    test_client.cookies.set("discord_session", _signed_discord_cookie("706"))
    resp = test_client.get("/account/stats")
    data = resp.json()
    assert data["themes"] == []  # rien de personnel, mais contribue au global (test précédent)


def test_account_stats_not_double_counted_when_account_has_two_players_on_same_team(test_client, db_session, sample_theme):
    # Revue de code : un compte avec deux Player sur la même équipe (deux
    # pseudos rejoints par erreur/deux onglets) ne doit pas voir chaque
    # Answer comptée deux fois.
    account = _make_account(db_session, "708")
    game, team = _make_game_and_team(db_session)
    _make_player(db_session, team.id, account_id=account.id, name="Pseudo1")
    _make_player(db_session, team.id, account_id=account.id, name="Pseudo2")

    q = _make_question(db_session, sample_theme.id, 1)
    _make_answer(db_session, q.id, team.id, is_correct=True)

    test_client.cookies.set("discord_session", _signed_discord_cookie("708"))
    resp = test_client.get("/account/stats")
    data = resp.json()
    theme = next(t for t in data["themes"] if t["theme_id"] == sample_theme.id)
    assert theme["personal_total"] == 1
    assert theme["personal_correct"] == 1


def test_compute_account_stats_general_matches_theme_sums(db_session, sample_theme):
    account = _make_account(db_session, "707")
    game, team = _make_game_and_team(db_session)
    _make_player(db_session, team.id, account_id=account.id)
    for i in range(12):
        q = _make_question(db_session, sample_theme.id, i)
        _make_answer(db_session, q.id, team.id, is_correct=(i % 2 == 0))

    result = compute_account_stats(db_session, account.id)
    assert result["general"]["personal_total"] == 12
    assert result["general"]["personal_correct"] == 6
