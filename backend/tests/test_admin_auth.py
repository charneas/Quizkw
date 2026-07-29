"""
Tests pour l'authentification admin (Epic F-ext-2, Story F-ext-2.1, AD-17).
Cookie de session signé HttpOnly/SameSite=Strict, guard partagé sur /admin/*.
"""
import os


def test_login_success_sets_cookie(test_client, sample_admin):
    resp = test_client.post("/admin/login", json={"email": sample_admin.email, "password": "correct-password"})
    assert resp.status_code == 200
    cookie_header = resp.headers.get("set-cookie", "")
    assert "admin_session=" in cookie_header
    assert "httponly" in cookie_header.lower()
    assert "samesite=strict" in cookie_header.lower()
    # SESSION_COOKIE_SECURE=false en test (TestClient n'est pas en HTTPS) ; le
    # comportement par défaut en dehors des tests est secure=true (AD-17).
    assert "secure" not in cookie_header.lower()


def test_login_unknown_email(test_client):
    resp = test_client.post("/admin/login", json={"email": "unknown@test.local", "password": "whatever"})
    assert resp.status_code == 400
    assert "detail" in resp.json()


def test_login_wrong_password(test_client, sample_admin):
    resp = test_client.post("/admin/login", json={"email": sample_admin.email, "password": "wrong-password"})
    assert resp.status_code == 400
    assert "detail" in resp.json()


def test_login_unknown_email_and_wrong_password_same_message(test_client, sample_admin):
    resp_unknown = test_client.post("/admin/login", json={"email": "unknown@test.local", "password": "whatever"})
    resp_wrong = test_client.post("/admin/login", json={"email": sample_admin.email, "password": "wrong-password"})
    assert resp_unknown.json()["detail"] == resp_wrong.json()["detail"]


def test_logout_clears_cookie(authenticated_client):
    resp = authenticated_client.post("/admin/logout")
    assert resp.status_code == 200
    cookie_header = resp.headers.get("set-cookie", "")
    assert "admin_session=" in cookie_header
    # Mêmes attributs qu'au login, sinon certains navigateurs ne l'effacent pas.
    assert "httponly" in cookie_header.lower()
    assert "samesite=strict" in cookie_header.lower()


def test_app_fails_to_start_without_session_secret_key_configured():
    # AD-17 : SESSION_SECRET_KEY est requise, sans défaut inséré en clair dans le
    # code. Test comportemental réel (pas un grep de source) : sous-processus
    # frais, sans la variable, important app.auth doit lever au chargement.
    import subprocess
    import sys

    env = {k: v for k, v in os.environ.items() if k != "SESSION_SECRET_KEY"}
    result = subprocess.run(
        [sys.executable, "-c", "import app.auth"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "SESSION_SECRET_KEY est requise" in result.stderr


def test_admin_route_without_cookie_rejected(test_client):
    resp = test_client.get("/admin/themes")
    assert resp.status_code == 401


def test_admin_route_with_valid_cookie_succeeds(authenticated_client):
    resp = authenticated_client.get("/admin/themes")
    assert resp.status_code == 200


def test_admin_route_with_invalid_cookie_rejected(test_client):
    test_client.cookies.set("admin_session", "tampered-invalid-value")
    resp = test_client.get("/admin/themes")
    assert resp.status_code == 401


def test_admin_content_gen_route_without_cookie_rejected(test_client):
    # main_content_gen.py:router est un routeur distinct, monté sous /admin/content
    # (AD-17 : "every route under /admin"), doit être couvert par le même guard.
    resp = test_client.get("/admin/content/category-mix")
    assert resp.status_code == 401


def test_admin_content_gen_route_with_valid_cookie_succeeds(authenticated_client):
    resp = authenticated_client.get("/admin/content/category-mix")
    assert resp.status_code == 200


def test_player_flag_route_not_guarded(test_client, sample_question):
    # player_router (signalement joueur) est délibérément hors /admin — non concerné par AD-17.
    resp = test_client.post(f"/questions/{sample_question.id}/flag", json={"reason": "test"})
    assert resp.status_code == 200
