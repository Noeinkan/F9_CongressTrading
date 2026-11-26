"""Owner login for the production copy (src/api/owner_login.py)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api import owner_login
from src.api.app import create_app

OWNER = "owner@example.com"
PASSWORD = "correct horse"
# Made with Werkzeug's generate_password_hash, the same format SearchForAlpha uses.
SCRYPT_HASH = (
    "scrypt:32768:8:1$MHpG9s181eWIN36p$622b152e2da2104be5228a3c694ebd2b10187e5d36b65aa059625edd083942e9"
    "e82d4a6f92e5d2fcd3e25ca985fbfb1e5b56aa171552ee077340fc99d34420d1"
)
PBKDF2_HASH = "pbkdf2:sha256:1000$CVLZCIuwHKRJX7OS$b60e9c4342af9450580c162cfaf162fe97945c1a4d391e83647dcc6a88be4a9b"


@pytest.fixture
def owner_env(monkeypatch):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    monkeypatch.delenv("APP_USERNAME", raising=False)
    monkeypatch.setenv("SITE_LOGIN_EMAIL", OWNER)
    monkeypatch.setenv("SITE_LOGIN_PASSWORD_HASH", PBKDF2_HASH)
    monkeypatch.setenv("APP_SESSION_SECRET", "s" * 40)


@pytest.fixture
def client(owner_env):
    return TestClient(create_app())


def _login(client, username=OWNER, password=PASSWORD):
    return client.post("/api/login", json={"username": username, "password": password})


@pytest.mark.parametrize("stored", [SCRYPT_HASH, PBKDF2_HASH])
def test_werkzeug_hashes_verify(stored):
    assert owner_login.check_password_hash(stored, PASSWORD)
    assert not owner_login.check_password_hash(stored, "wrong")


def test_signed_out_is_refused_and_owner_gets_in(client):
    assert client.get("/api/session").json()["authenticated"] is False
    assert client.get("/api/me").status_code == 401
    response = _login(client, username="Owner@Example.com")
    assert response.status_code == 200
    assert response.json()["user"] == OWNER
    assert client.get("/api/session").json() == {"authenticated": True, "auth_required": True, "user": OWNER}


def test_wrong_password_or_other_email_is_refused(client):
    assert _login(client, password="nope").status_code == 401
    assert _login(client, username="someone@example.com").status_code == 401
    assert client.get("/api/session").json()["authenticated"] is False


def test_five_failures_lock_the_login(client):
    for _ in range(owner_login.MAX_FAILURES):
        _login(client, password="nope")
    assert _login(client).status_code == 429


@pytest.mark.parametrize("unset", ["SITE_LOGIN_EMAIL", "APP_SESSION_SECRET"])
def test_half_configured_login_refuses_to_start(owner_env, monkeypatch, unset):
    monkeypatch.delenv(unset)
    with pytest.raises(owner_login.LoginConfigError):
        create_app()


def test_malformed_hash_refuses_to_start(owner_env, monkeypatch):
    monkeypatch.setenv("SITE_LOGIN_PASSWORD_HASH", "plain-text-password")
    with pytest.raises(owner_login.LoginConfigError):
        create_app()


def test_cannot_combine_with_demo_mode(owner_env, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    with pytest.raises(owner_login.LoginConfigError):
        create_app()
