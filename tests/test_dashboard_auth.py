"""Tests for dashboard login env and credential verification."""

from __future__ import annotations

import pytest

from src.config import dashboard_auth_required
from src.dashboard_shared.auth import verify_dashboard_credentials


@pytest.fixture(autouse=True)
def _clear_dashboard_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "DASHBOARD_USERNAME",
        "DASHBOARD_PASSWORD",
        "DASHBOARD_SERVER_ADDRESS",
        "DASHBOARD_SERVER_PORT",
    ):
        monkeypatch.delenv(key, raising=False)


def test_auth_not_required_without_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DASHBOARD_PASSWORD", raising=False)
    assert dashboard_auth_required() is False
    assert verify_dashboard_credentials("any", "any") is True


def test_auth_required_when_password_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    assert dashboard_auth_required() is True


def test_correct_credentials_with_username(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DASHBOARD_USERNAME", "admin")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    assert verify_dashboard_credentials("admin", "secret") is True


def test_wrong_password_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DASHBOARD_USERNAME", "admin")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    assert verify_dashboard_credentials("admin", "wrong") is False


def test_wrong_username_rejected_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DASHBOARD_USERNAME", "admin")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    assert verify_dashboard_credentials("", "secret") is False
    assert verify_dashboard_credentials("other", "secret") is False


def test_password_only_when_username_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    assert verify_dashboard_credentials("", "secret") is True
    assert verify_dashboard_credentials("anyone", "secret") is True
    assert verify_dashboard_credentials("anyone", "nope") is False
