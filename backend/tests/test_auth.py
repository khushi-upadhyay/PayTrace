from app.api.dependencies import get_current_user
from app.main import app


def _real_auth(client):
    """Drop the conftest bypass so the real bearer-token check runs."""
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
