"""Google sign-in through the single address (frontend proxy).

The CSRF state rides in a per-host cookie, so Google must send the buyer back
to the SAME address they started on. Through the Next.js proxy that address
arrives as X-Forwarded-Host; forged hosts must be ignored."""

from urllib.parse import parse_qs, unquote, urlsplit

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "test-client-id.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "google_client_secret", "test-secret")
    from app.auth import oauth_router

    monkeypatch.setattr(oauth_router.oauth.google, "client_id", settings.google_client_id)
    monkeypatch.setattr(oauth_router.oauth.google, "client_secret", settings.google_client_secret)
    # don't fetch Google's discovery document in tests
    monkeypatch.setattr(oauth_router.oauth.google, "server_metadata", {
        "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_endpoint": "https://oauth2.googleapis.com/token",
        "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs",
        "issuer": "https://accounts.google.com",
    })
    return TestClient(app, follow_redirects=False)


def _redirect_uri(resp) -> str:
    q = parse_qs(urlsplit(resp.headers["location"]).query)
    return q["redirect_uri"][0]


@pytest.mark.parametrize("host", ["localhost:3000", "127.0.0.1:3000"])
def test_round_trip_uses_the_browser_address(client, host):
    resp = client.get("/api/auth/google/login", headers={"x-forwarded-host": host})
    assert resp.status_code in (302, 307)
    assert _redirect_uri(resp) == f"http://{host}/api/auth/google/callback"


def test_https_tunnel_is_kept_https(client):
    resp = client.get("/api/auth/google/login",
                      headers={"x-forwarded-host": "abc.ngrok-free.app", "x-forwarded-proto": "https"})
    assert _redirect_uri(resp) == "https://abc.ngrok-free.app/api/auth/google/callback"


def test_forged_host_is_ignored(client):
    resp = client.get("/api/auth/google/login", headers={"x-forwarded-host": "evil.example.com"})
    assert "evil.example.com" not in _redirect_uri(resp)


def test_direct_backend_call_still_works(client):
    resp = client.get("/api/auth/google/login")
    assert _redirect_uri(resp).endswith("/api/auth/google/callback")


def test_not_configured_explains_instead_of_sending_to_google(client, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "")
    resp = client.get("/api/auth/google/login", headers={"x-forwarded-host": "localhost:3000"})
    loc = resp.headers["location"]
    assert loc.startswith("http://localhost:3000/login?error=")
    assert "GOOGLE_CLIENT_ID" in unquote(loc)
