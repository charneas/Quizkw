"""Tests pour la connexion Discord facultative (Epic O, Story O.1.1, AD-19/AD-22).
Cookie de session signé HttpOnly/SameSite=Strict, secret dédié distinct de
l'admin (AD-17), résolution-ou-création d'Account par discord_id, protection
CSRF `state` (RFC 6749 §10.12, ajoutée en revue de code)."""
import os
from unittest.mock import patch, MagicMock

import httpx

from app import models


def _mock_httpx_client(user_data: dict | None = None, token_status_ok: bool = True,
                        user_status_ok: bool = True, token_raises: Exception | None = None,
                        user_raises: Exception | None = None):
    """Construit un mock de httpx.Client couvrant le `with httpx.Client(...) as client:`
    utilisé par main_auth_discord.discord_callback."""
    mock_client = MagicMock()

    token_resp = MagicMock()
    if token_raises is not None:
        mock_client.post.side_effect = token_raises
    elif token_status_ok:
        token_resp.raise_for_status = MagicMock()
        token_resp.json.return_value = {"access_token": "fake-access-token"}
        mock_client.post.return_value = token_resp
    else:
        token_resp.raise_for_status.side_effect = httpx.HTTPStatusError("token error", request=MagicMock(), response=MagicMock())
        mock_client.post.return_value = token_resp

    user_resp = MagicMock()
    if user_raises is not None:
        mock_client.get.side_effect = user_raises
    elif user_status_ok:
        user_resp.raise_for_status = MagicMock()
        user_resp.json.return_value = user_data or {}
        mock_client.get.return_value = user_resp
    else:
        user_resp.raise_for_status.side_effect = httpx.HTTPStatusError("user error", request=MagicMock(), response=MagicMock())
        mock_client.get.return_value = user_resp

    context_manager = MagicMock()
    context_manager.__enter__.return_value = mock_client
    context_manager.__exit__.return_value = False
    return context_manager


def _login_and_get_state(test_client) -> str:
    """Suit le flux réel : GET /login pose le cookie CSRF `discord_oauth_state`
    et l'inclut dans l'URL Discord — on récupère la même valeur pour l'appel
    callback qui suit, comme le ferait un vrai aller-retour navigateur."""
    resp = test_client.get("/auth/discord/login", follow_redirects=False)
    state_cookie = test_client.cookies.get("discord_oauth_state")
    assert state_cookie is not None
    return state_cookie


def test_discord_login_redirects_to_discord_authorize_url_with_state(test_client):
    resp = test_client.get("/auth/discord/login", follow_redirects=False)
    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    assert location.startswith("https://discord.com/oauth2/authorize")
    assert "client_id=test-discord-client-id" in location
    assert "scope=identify" in location
    assert "redirect_uri=" in location
    assert "state=" in location
    cookie_header = resp.headers.get("set-cookie", "")
    assert "discord_oauth_state=" in cookie_header
    assert "httponly" in cookie_header.lower()
    assert "samesite=lax" in cookie_header.lower()


def test_discord_callback_creates_account_and_sets_cookie(test_client, db_session):
    state = _login_and_get_state(test_client)
    user_data = {"id": "123456789", "username": "TestPlayer", "avatar": "abc123hash"}
    with patch("main_auth_discord.httpx.Client", return_value=_mock_httpx_client(user_data)):
        resp = test_client.get(f"/auth/discord/callback?code=fake-code&state={state}", follow_redirects=False)

    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "/?discord=connected"
    cookie_header = resp.headers.get("set-cookie", "")
    assert "discord_session=" in cookie_header
    assert "httponly" in cookie_header.lower()
    assert "samesite=strict" in cookie_header.lower()
    assert "max-age=" in cookie_header.lower()

    account = db_session.query(models.Account).filter(models.Account.discord_id == "123456789").first()
    assert account is not None
    assert account.pseudo == "TestPlayer"
    assert account.avatar == "abc123hash"


def test_discord_callback_rejects_missing_state(test_client, db_session):
    # Aucun passage par /login au préalable -> pas de cookie discord_oauth_state.
    user_data = {"id": "1", "username": "NoState"}
    with patch("main_auth_discord.httpx.Client", return_value=_mock_httpx_client(user_data)):
        resp = test_client.get("/auth/discord/callback?code=fake-code&state=whatever", follow_redirects=False)

    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "/"
    assert db_session.query(models.Account).filter(models.Account.discord_id == "1").first() is None


def test_discord_callback_rejects_mismatched_state(test_client, db_session):
    _login_and_get_state(test_client)
    user_data = {"id": "2", "username": "WrongState"}
    with patch("main_auth_discord.httpx.Client", return_value=_mock_httpx_client(user_data)):
        resp = test_client.get("/auth/discord/callback?code=fake-code&state=attacker-supplied-state", follow_redirects=False)

    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "/"
    assert db_session.query(models.Account).filter(models.Account.discord_id == "2").first() is None


def test_discord_callback_reuses_account_and_refreshes_pseudo_avatar(test_client, db_session):
    state_1 = _login_and_get_state(test_client)
    first_data = {"id": "123456789", "username": "OldPseudo", "avatar": "old-avatar"}
    with patch("main_auth_discord.httpx.Client", return_value=_mock_httpx_client(first_data)):
        test_client.get(f"/auth/discord/callback?code=fake-code-1&state={state_1}", follow_redirects=False)

    state_2 = _login_and_get_state(test_client)
    second_data = {"id": "123456789", "username": "NewPseudo", "avatar": "new-avatar"}
    with patch("main_auth_discord.httpx.Client", return_value=_mock_httpx_client(second_data)):
        test_client.get(f"/auth/discord/callback?code=fake-code-2&state={state_2}", follow_redirects=False)

    accounts = db_session.query(models.Account).filter(models.Account.discord_id == "123456789").all()
    assert len(accounts) == 1
    assert accounts[0].pseudo == "NewPseudo"
    assert accounts[0].avatar == "new-avatar"


def test_discord_callback_token_exchange_failure_creates_no_account(test_client, db_session):
    state = _login_and_get_state(test_client)
    user_data = {"id": "999", "username": "Ghost"}
    with patch("main_auth_discord.httpx.Client", return_value=_mock_httpx_client(user_data, token_status_ok=False)):
        resp = test_client.get(f"/auth/discord/callback?code=fake-code&state={state}", follow_redirects=False)

    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "/"
    assert "discord_session=" not in resp.headers.get("set-cookie", "")
    assert db_session.query(models.Account).filter(models.Account.discord_id == "999").first() is None


def test_discord_callback_token_exchange_timeout_creates_no_account(test_client, db_session):
    state = _login_and_get_state(test_client)
    with patch(
        "main_auth_discord.httpx.Client",
        return_value=_mock_httpx_client(token_raises=httpx.TimeoutException("timed out")),
    ):
        resp = test_client.get(f"/auth/discord/callback?code=fake-code&state={state}", follow_redirects=False)

    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "/"
    assert "discord_session=" not in resp.headers.get("set-cookie", "")


def test_discord_callback_users_me_failure_creates_no_account(test_client, db_session):
    state = _login_and_get_state(test_client)
    with patch("main_auth_discord.httpx.Client", return_value=_mock_httpx_client(user_status_ok=False)):
        resp = test_client.get(f"/auth/discord/callback?code=fake-code&state={state}", follow_redirects=False)

    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "/"
    assert "discord_session=" not in resp.headers.get("set-cookie", "")


def test_discord_callback_users_me_missing_username_returns_guest_redirect_not_500(test_client, db_session):
    # Réponse Discord 200 mais sans `username` (schéma inattendu) — doit rester
    # dans le contrat "aucune 500 en plein flux de redirection" (AC #5).
    state = _login_and_get_state(test_client)
    with patch("main_auth_discord.httpx.Client", return_value=_mock_httpx_client({"id": "77"})):
        resp = test_client.get(f"/auth/discord/callback?code=fake-code&state={state}", follow_redirects=False)

    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "/"


def test_discord_callback_consent_refused_redirects_without_error(test_client):
    resp = test_client.get("/auth/discord/callback?error=access_denied", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "/"
    assert "discord_session=" not in resp.headers.get("set-cookie", "")


def test_discord_callback_without_code_redirects_without_error(test_client):
    resp = test_client.get("/auth/discord/callback", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "/"
    assert "discord_session=" not in resp.headers.get("set-cookie", "")


def test_discord_callback_concurrent_login_no_duplicate_account():
    # Simule la course décrite par AD-19 avec une vraie IntegrityError contre
    # une base SQLite dédiée (pas la fixture db_session partagée : un vrai
    # rollback mi-test y déassocie la transaction imbriquée de la fixture).
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database import Base
    from app.account_manager import resolve_or_create_account

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    resolve_or_create_account(session, discord_id="555", pseudo="First", avatar=None)
    winning_account = session.query(models.Account).filter(models.Account.discord_id == "555").first()
    assert winning_account is not None

    # La requête de lookup initiale du second appel ne voit pas encore la
    # ligne du premier (isolation de transaction, comme deux connexions
    # concurrentes) — on force ce seul premier `.first()` à renvoyer None —
    # puis l'insert heurte la vraie contrainte unique DB (`discord_id` déjà
    # présent) et lève une vraie IntegrityError. La branche de récupération
    # doit alors relire (requête réelle) la ligne posée par le premier appel
    # et la mettre à jour, sans planter ni dupliquer.
    real_query = session.query
    calls = {"n": 0}

    def _query_returns_none_once(*args, **kwargs):
        calls["n"] += 1
        result = real_query(*args, **kwargs)
        if calls["n"] == 1:
            result.first = lambda: None
        return result

    with patch.object(session, "query", side_effect=_query_returns_none_once):
        account_2 = resolve_or_create_account(session, discord_id="555", pseudo="Second", avatar="hash")

    accounts = session.query(models.Account).filter(models.Account.discord_id == "555").all()
    assert len(accounts) == 1
    assert account_2.pseudo == "Second"
    session.close()


def test_resolve_or_create_account_reraises_when_integrity_error_is_unrelated(db_session):
    # Si l'IntegrityError ne correspond à aucune ligne relisible par discord_id
    # (contrainte différente), la fonction doit propager plutôt que de planter
    # sur un accès None (bug trouvé en revue de code).
    from app.account_manager import resolve_or_create_account
    from sqlalchemy.exc import IntegrityError
    import pytest

    with patch.object(db_session, "commit", side_effect=IntegrityError("stmt", "params", "orig")):
        with patch.object(db_session, "rollback"):
            with pytest.raises(IntegrityError):
                resolve_or_create_account(db_session, discord_id="does-not-exist-after-rollback", pseudo="X", avatar=None)


def test_discord_routes_return_503_without_crashing_app_when_unconfigured(test_client):
    # Revue de code 2026-08-27 : la config Discord est vérifiée à l'appel, pas
    # à l'import du module — l'absence des variables ne doit jamais faire
    # tomber le reste de l'API (mode invité), seulement ces deux routes.
    discord_vars = ["DISCORD_CLIENT_ID", "DISCORD_CLIENT_SECRET", "DISCORD_REDIRECT_URI", "DISCORD_SESSION_SECRET_KEY"]
    original = {k: os.environ.get(k) for k in discord_vars}
    try:
        for k in discord_vars:
            os.environ.pop(k, None)
        resp = test_client.get("/auth/discord/login", follow_redirects=False)
        assert resp.status_code == 503
    finally:
        for k, v in original.items():
            if v is not None:
                os.environ[k] = v


def test_discord_callback_never_stores_email(test_client, db_session):
    # Même si la réponse mockée de GET /users/@me contient une adresse email
    # (le scope `identify` ne la garantit pas absente côté API réelle), AC #7
    # exige qu'elle ne soit jamais lue ni stockée — vérifié structurellement
    # (le modèle Account n'a pas de colonne email) ET par une lecture SQL brute
    # de la ligne insérée, pour couvrir aussi une éventuelle table/colonne
    # ajoutée par erreur ailleurs.
    user_data = {"id": "42", "username": "EmailLeakTest", "avatar": None, "email": "leak@example.com"}
    state = _login_and_get_state(test_client)
    with patch("main_auth_discord.httpx.Client", return_value=_mock_httpx_client(user_data)):
        test_client.get(f"/auth/discord/callback?code=fake-code&state={state}", follow_redirects=False)

    account = db_session.query(models.Account).filter(models.Account.discord_id == "42").first()
    assert account is not None
    assert not hasattr(account, "email")
    assert "email" not in models.Account.__table__.columns.keys()
