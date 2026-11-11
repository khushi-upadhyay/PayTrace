from app.api.dependencies import get_current_user
from app.main import app
from app.core.config import settings
from fastapi.testclient import TestClient


def _real_auth(client):
    """Drop the conftest bypass so the real cookie/bearer auth check runs."""
    app.dependency_overrides.pop(get_current_user, None)


def test_register_login_and_me(client):
    _real_auth(client)
    body = {"name": "Aayushi", "email": "Aayushi@Example.com", "password": "Palak#25xx"}
    r = client.post("/api/v1/auth/register", json=body)
    assert r.status_code == 201
    assert r.json()["user"]["email"] == "aayushi@example.com"

    assert client.post("/api/v1/auth/register", json=body).status_code == 409

    r = client.post("/api/v1/auth/login", json={"email": "aayushi@example.com", "password": "Palak#25xx"})
    assert r.status_code == 200
    token = r.json()["access_token"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["name"] == "Aayushi"


def test_wrong_password_and_unknown_email_rejected(client):
    _real_auth(client)
    client.post("/api/v1/auth/register", json={"name": "A", "email": "a@example.com", "password": "longenough1"})
    assert client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "nope"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "x@example.com", "password": "nope"}).status_code == 401


def test_operator_routes_require_token(client):
    _real_auth(client)
    assert client.get("/api/v1/payments").status_code == 401
    assert client.get("/api/v1/payments", headers={"Authorization": "Bearer garbage"}).status_code == 401
    assert client.get("/api/v1/health").status_code == 200


def test_short_password_rejected(client):
    _real_auth(client)
    r = client.post("/api/v1/auth/register", json={"name": "A", "email": "b@example.com", "password": "short"})
    assert r.status_code == 422


def test_registration_closed_outside_development(client):
    from app.core.config import settings
    _real_auth(client)
    original = settings.APP_ENV
    settings.APP_ENV = "production"
    try:
        r = client.post("/api/v1/auth/register", json={"name": "A", "email": "z@example.com", "password": "longenough1"})
        assert r.status_code == 403
    finally:
        settings.APP_ENV = original


def test_login_sets_httponly_cookie_and_cookie_authenticates(client, monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "test")
    monkeypatch.setattr(settings, "FRONTEND_ORIGIN", "http://localhost:3000")
    monkeypatch.setattr(settings, "COOKIE_SAMESITE", "lax")
    _real_auth(client)
    client.post("/api/v1/auth/register", json={"name": "C", "email": "c@example.com", "password": "longenough1"})
    r = client.post("/api/v1/auth/login", json={"email": "c@example.com", "password": "longenough1"})
    cookie = r.headers["set-cookie"].lower()
    assert "paytrace_session=" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    assert "; secure" not in cookie
    assert "max-age" in cookie
    client.cookies.set("paytrace_session", r.json()["access_token"])
    assert client.get("/api/v1/auth/me").status_code == 200

    # Unsafe cookie-authenticated requests need the CSRF header; with it they get past auth.
    assert client.post("/api/v1/auth/logout").status_code == 204  # public route
    assert client.post("/api/v1/approvals/x/decision", json={"decision": "APPROVED"}).status_code == 403
    r2 = client.post(
        "/api/v1/approvals/x/decision", json={"decision": "APPROVED"}, headers={"X-Requested-With": "PayTrace"}
    )
    assert r2.status_code != 401 and "CSRF" not in r2.text  # authenticated; reaches the route
    assert "CSRF" not in r2.text


def test_production_cookie_is_cross_site_and_authenticates_workspace(client, monkeypatch):
    _real_auth(client)
    registered = client.post(
        "/api/v1/auth/register",
        json={"name": "Production", "email": "prod-cookie@example.com", "password": "longenough1"},
    )
    assert registered.status_code == 201

    # Simulate a stale Render setting: production must still issue a cross-site cookie.
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "FRONTEND_ORIGIN", "https://paytraceai.vercel.app")
    monkeypatch.setattr(settings, "COOKIE_SAMESITE", "lax")
    with TestClient(app, base_url="https://testserver") as browser:
        response = browser.post(
            "/api/v1/auth/login",
            json={"email": "prod-cookie@example.com", "password": "longenough1"},
        )
        assert response.status_code == 200
        cookie = response.headers["set-cookie"].lower()
        assert "paytrace_session=" in cookie
        assert "samesite=none" in cookie
        assert "secure" in cookie
        assert "httponly" in cookie
        assert "path=/" in cookie

        # The HTTPS client stores and automatically sends the Secure cookie.
        me = browser.get("/api/v1/auth/me")
        workspace = browser.get("/api/v1/payments/workspace?limit=500")
        assert me.status_code == 200
        assert me.json()["email"] == "prod-cookie@example.com"
        assert workspace.status_code == 200

        logged_out = browser.post("/api/v1/auth/logout")
        cleared_cookie = logged_out.headers["set-cookie"].lower()
        assert logged_out.status_code == 204
        assert "samesite=none" in cleared_cookie and "secure" in cleared_cookie
        assert browser.get("/api/v1/auth/me").status_code == 401


def test_missing_and_invalid_session_cookies_return_401(client):
    _real_auth(client)
    assert client.get("/api/v1/auth/me").status_code == 401
    client.cookies.set("paytrace_session", "not-a-valid-session")
    assert client.get("/api/v1/auth/me").status_code == 401


def test_cors_allows_only_the_configured_origin_with_credentials(client):
    origin = settings.FRONTEND_ORIGIN
    allowed = client.options(
        "/api/v1/auth/me",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert allowed.headers.get("access-control-allow-origin") == origin
    assert allowed.headers.get("access-control-allow-credentials") == "true"

    denied = client.options(
        "/api/v1/auth/me",
        headers={
            "Origin": "https://not-paytrace.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert denied.headers.get("access-control-allow-origin") is None


def test_session_only_cookie_without_remember(client):
    _real_auth(client)
    client.post("/api/v1/auth/register", json={"name": "D", "email": "d@example.com", "password": "longenough1"})
    r = client.post("/api/v1/auth/login", json={"email": "d@example.com", "password": "longenough1", "remember": False})
    assert "max-age" not in r.headers["set-cookie"].lower()


def test_logout_clears_cookie(client):
    r = client.post("/api/v1/auth/logout")
    assert r.status_code == 204 and "paytrace_session=" in r.headers["set-cookie"]


def test_register_rejects_malformed_emails_and_strips_nul(client):
    _real_auth(client)
    for bad in ("a@@b.com", "a@b", "a b@c.com", "@b.com", "a@.com"):
        r = client.post("/api/v1/auth/register", json={"name": "X", "email": bad, "password": "longenough1"})
        assert r.status_code == 422, bad
    ok = client.post("/api/v1/auth/register", json={"name": "a\x00b", "email": "nul@example.com", "password": "longenough1"})
    assert ok.status_code == 201 and ok.json()["user"]["name"] == "ab"
