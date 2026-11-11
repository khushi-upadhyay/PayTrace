def test_health_check(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("healthy", "degraded")
    assert data["paypal_environment"] == "sandbox"
    assert data["paypal_configured"] is False
    assert "ai_investigator" in data


def test_security_headers_present(client):
    r = client.get("/api/v1/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    assert "Referrer-Policy" in r.headers and "Permissions-Policy" in r.headers
    assert "Content-Security-Policy" not in client.get("/docs").headers


def test_health_does_not_leak_database_errors(client, monkeypatch):
    from app.api.routes import health

    class Boom:
        def execute(self, *_):
            raise RuntimeError("secret-connection-string")

    out = health.get_health(db=Boom())
    assert out["database"] == "unhealthy" and "secret" not in str(out)


def test_docs_disabled_outside_development():
    import subprocess, sys, os
    code = "from app.main import app; print(app.docs_url, app.redoc_url, app.openapi_url)"
    env = {**os.environ, "APP_ENV": "production", "AUTH_SECRET_KEY": "x" * 40}
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env,
                         cwd=os.path.dirname(os.path.dirname(__file__)))
    assert out.stdout.strip() == "None None None", out.stderr
