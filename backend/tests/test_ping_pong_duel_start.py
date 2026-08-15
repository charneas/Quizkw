"""BUG-101c : rien n'empêchait une équipe de se retrouver dans 2 duels
ping-pong actifs simultanés (start_duel ne vérifiait pas l'état existant des
équipes). Les endroits qui cherchent "le" duel actif d'une équipe (ex. SWAP
dans /tokens/use, /game/{code}/team/{team_id}/state) utilisent tous un
.first() sans critère de désambiguïsation : avec 2 duels actifs, l'un
d'eux serait choisi arbitrairement et pourrait recevoir l'effet d'un jeton
ou un état destiné à l'autre."""
from app import models


def _make_team(db_session, game, name, score=0):
    team = models.Team(name=name, game_session_id=game.id, score=score)
    db_session.add(team)
    db_session.commit()
    db_session.refresh(team)
    return team


def _make_theme(db_session, title, correct_answers):
    theme = models.PingPongTheme(title=title, correct_answers=correct_answers)
    db_session.add(theme)
    db_session.commit()
    db_session.refresh(theme)
    return theme


def test_starting_duel_fails_if_team_already_has_active_duel(test_client, db_session, sample_game_session):
    team1 = _make_team(db_session, sample_game_session, "Team A")
    team2 = _make_team(db_session, sample_game_session, "Team B")
    team3 = _make_team(db_session, sample_game_session, "Team C")
    theme = _make_theme(db_session, "Capitales", ["Paris"])

    first = test_client.post("/ping-pong/duel/start", json={
        "game_session_id": sample_game_session.id,
        "theme_id": theme.id,
        "team1_id": team1.id,
        "team2_id": team2.id,
    }, headers={"X-Host-Token": sample_game_session.host_token})
    assert first.status_code == 200

    # team1 est déjà engagée dans un duel actif : un nouveau duel la
    # impliquant (même comme team2) doit être refusé, pas créé en silence.
    second = test_client.post("/ping-pong/duel/start", json={
        "game_session_id": sample_game_session.id,
        "theme_id": theme.id,
        "team1_id": team3.id,
        "team2_id": team1.id,
    }, headers={"X-Host-Token": sample_game_session.host_token})
    assert second.status_code == 400

    duels = db_session.query(models.PingPongDuel).filter(
        models.PingPongDuel.is_completed == False
    ).all()
    assert len(duels) == 1


def test_starting_duel_allowed_again_once_previous_duel_completed(test_client, db_session, sample_game_session):
    team1 = _make_team(db_session, sample_game_session, "Team A")
    team2 = _make_team(db_session, sample_game_session, "Team B")
    team3 = _make_team(db_session, sample_game_session, "Team C")
    theme = _make_theme(db_session, "Capitales", ["Paris"])

    first = test_client.post("/ping-pong/duel/start", json={
        "game_session_id": sample_game_session.id,
        "theme_id": theme.id,
        "team1_id": team1.id,
        "team2_id": team2.id,
    }, headers={"X-Host-Token": sample_game_session.host_token})
    duel_id = first.json()["duel_id"]

    duel = db_session.query(models.PingPongDuel).filter(models.PingPongDuel.id == duel_id).first()
    duel.is_completed = True
    db_session.commit()

    second = test_client.post("/ping-pong/duel/start", json={
        "game_session_id": sample_game_session.id,
        "theme_id": theme.id,
        "team1_id": team1.id,
        "team2_id": team3.id,
    }, headers={"X-Host-Token": sample_game_session.host_token})
    assert second.status_code == 200


def test_swap_targets_most_recent_active_duel_if_several_exist(test_client, db_session, sample_game_session):
    """Défense en profondeur : même si 2 duels actifs existaient malgré la
    garde de start_duel (ex. donnée historique, ou garde contournée par une
    voie non couverte), le jeton SWAP doit cibler le duel le plus récent
    plutôt qu'un résultat arbitraire."""
    team1 = _make_team(db_session, sample_game_session, "Team A")
    team2 = _make_team(db_session, sample_game_session, "Team B")
    team3 = _make_team(db_session, sample_game_session, "Team C")
    theme1 = _make_theme(db_session, "Capitales", ["Paris"])
    theme2 = _make_theme(db_session, "Fleuves", ["Loire"])

    old_duel = models.PingPongDuel(
        game_session_id=sample_game_session.id, theme_id=theme1.id,
        team1_id=team1.id, team2_id=team2.id,
        current_turn_team_id=team1.id, is_completed=False, answers_used=[],
    )
    db_session.add(old_duel)
    db_session.commit()

    recent_duel = models.PingPongDuel(
        game_session_id=sample_game_session.id, theme_id=theme2.id,
        team1_id=team1.id, team2_id=team3.id,
        current_turn_team_id=team1.id, is_completed=False, answers_used=[],
    )
    db_session.add(recent_duel)
    db_session.add(models.Token(team_id=team1.id, token_type=models.TokenType.SWAP, is_used=False))
    db_session.commit()
    db_session.refresh(recent_duel)

    resp = test_client.post(
        "/tokens/use",
        json={"team_id": team1.id, "token_type": "SWAP"},
        headers={"X-Team-Token": team1.team_token},
    )
    assert resp.status_code == 200

    db_session.refresh(old_duel)
    db_session.refresh(recent_duel)
    assert old_duel.theme_id == theme1.id  # inchangé
    assert recent_duel.theme_id != theme2.id  # c'est celui-ci qui a été swappé
