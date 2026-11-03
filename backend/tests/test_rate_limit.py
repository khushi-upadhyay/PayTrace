import pytest

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.rate_limit import limiter
from app.main import app


@pytest.fixture
def limited(client):
    app.dependency_overrides.pop(get_current_user, None)
    settings.RATE_LIMIT_ENABLED = True
    limiter.reset()
    yield client
    settings.RATE_LIMIT_ENABLED = False
    limiter.reset()


def test_login_rate_limited_per_email(limited):
    body = {"email": "victim@example.com", "password": "wrong-password"}
    codes = [limited.post("/api/v1/auth/login", json=body).status_code for _ in range(10)]
    assert codes[:8] == [401] * 8
    assert codes[8] == 429
    resp = limited.post("/api/v1/auth/login", json=body)
    assert resp.status_code == 429 and int(resp.headers["Retry-After"]) >= 1


def test_login_rate_limited_per_ip(limited):
    codes = [
        limited.post("/api/v1/auth/login", json={"email": f"u{i}@example.com", "password": "x"}).status_code
        for i in range(22)
    ]
    assert 429 in codes and codes[0] == 401


def test_order_creation_rate_limited(limited):
    codes = [limited.post("/api/v1/paypal/orders", json={"amount": "5.00"}).status_code for _ in range(22)]
    assert codes[0] == 200 and codes[-1] == 429
