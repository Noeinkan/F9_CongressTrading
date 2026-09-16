"""The demo's email gate: one verified address, one 45-minute session, a usage log.

Each test drives the real app through ``TestClient`` with the console mail
backend, so a code is read from the outbox instead of an inbox, and moves the
store's clock instead of sleeping.
"""
from __future__ import annotations

import re
import socket
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ADMIN_TOKEN = "a-very-long-admin-token-for-tests-0123"
START = 1_790_000_000.0  # 2026-09-21, a fixed instant for the store's clock


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> float:
        return self.now

    def advance(self, *, minutes: float = 0, days: float = 0) -> None:
        self.now += minutes * 60 + days * 86400


@pytest.fixture
def demo_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DEMO_SNAPSHOT_DATE", "2026-09-12")
    monkeypatch.setenv("DEMO_MAIL_BACKEND", "console")
    monkeypatch.setenv("DEMO_ACCESS_DB", str(tmp_path / "access.sqlite3"))
    for name in (
        "DEMO_ACCESS_GATE", "DEMO_ADMIN_TOKEN", "DEMO_NOTIFY_EMAIL", "DEMO_SESSION_MINUTES", "DEMO_CODES_PER_DAY",
        "DEMO_CODES_PER_HOUR", "DEMO_SIGNUPS_PER_IP_PER_DAY", "DEMO_PUBLIC_URL", "APP_USERNAME", "APP_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("APP_SESSION_SECRET", "test-secret")


@pytest.fixture
def clock() -> Clock:
    return Clock()


def _client(clock: Clock) -> TestClient:
    from src.api.app import create_app

    client = TestClient(create_app())
    client.app.state.demo_access.store.clock = clock
    return client


def _outbox(client: TestClient):
    return client.app.state.demo_access.mailer.outbox


def _store(client: TestClient):
    return client.app.state.demo_access.store


def _ask(client: TestClient, address: str, **headers: str):
    return client.post("/api/demo/access/request", json={"email": address}, headers=headers)


def _code(client: TestClient) -> str:
    match = re.search(r"code is (\d{3}) (\d{3})", _outbox(client)[-1].text)
    assert match, _outbox(client)[-1].text
    return "".join(match.groups())


def _link_token(client: TestClient) -> str:
    match = re.search(r"/access/verify\?t=([\w-]+)", _outbox(client)[-1].text)
    assert match
    return match.group(1)


def _sign_in(client: TestClient, address: str = "visitor@example.com"):
    assert _ask(client, address).status_code == 200
    response = client.post("/api/demo/access/code", json={"email": address, "code": _code(client)})
    assert response.status_code == 200, response.text
    return response


def _events(client: TestClient, kind: str | None = None):
    return [e for e in _store(client).recent_events(1000) if kind is None or e["kind"] == kind]


# --------------------------------------------------------------------------
# Signed out
# --------------------------------------------------------------------------


def test_signed_out_api_call_gets_the_notice_and_nothing_is_recorded(demo_env, clock):
    client = _client(clock)
    response = client.get("/api/home/summary")
    assert response.status_code == 401
    assert response.json()["code"] == "DEMO_SIGNED_OUT"
    assert _events(client) == []


def test_status_and_health_answer_without_signing_in(demo_env, clock):
    client = _client(clock)
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/demo/status").json()["access"]["status"] == "signed_out"


def test_the_openapi_docs_are_behind_the_gate(demo_env, clock):
    assert _client(clock).get("/openapi.json").status_code == 401


# --------------------------------------------------------------------------
# Signing in
# --------------------------------------------------------------------------


def test_the_code_signs_in_starts_the_session_and_records_usage(demo_env, clock):
    client = _client(clock)
    body = _sign_in(client).json()
    assert body["access"]["status"] == "active"
    assert body["access"]["address"] == "visitor@example.com"
    assert body["access"]["startedAt"] == "2026-09-21T14:13:20Z"
    assert body["access"]["expiresAt"] == "2026-09-21T14:58:20Z"  # 45 minutes later

    status = client.get("/api/demo/status").json()["access"]
    assert status["status"] == "active"
    assert status["expiresAt"] == body["access"]["expiresAt"]

    client.get("/api/home/summary")
    client.get("/api/home/summary")  # the same page again is one event, not two
    client.get("/api/tickers/NVDA")
    client.get("/api/members/Nancy%20Pelosi/tickers")
    assert [(e["kind"], e["detail"]) for e in _events(client) if e["kind"] in ("page", "ticker", "member")] == [
        ("member", "Nancy Pelosi"),
        ("ticker", "NVDA"),
        ("page", "home"),
    ]


def test_the_email_says_what_the_session_is(demo_env, clock):
    client = _client(clock)
    _ask(client, "visitor@example.com")
    mail = _outbox(client)[-1]
    assert mail.to == "visitor@example.com"
    assert "45-minute session" in mail.text
    assert "15 minutes" in mail.text
    assert "http://testserver/access/verify?t=" in mail.text


def test_the_link_is_not_spent_by_a_get(demo_env, clock):
    """Mail scanners open every link: only the POST behind the button signs in."""
    client = _client(clock)
    _ask(client, "Visitor@Example.com")
    token = _link_token(client)
    for _ in range(2):
        response = client.get(f"/api/demo/access/link?t={token}")
        assert response.status_code == 200
        assert response.json() == {"address": "Visitor@Example.com"}
    assert client.get("/api/home/summary").status_code == 401

    assert client.post("/api/demo/access/link", json={"t": token}).status_code == 200
    assert client.get("/api/session").json()["authenticated"] is True
    second = client.post("/api/demo/access/link", json={"t": token})
    assert second.status_code == 410
    assert second.json()["code"] == "LINK_DEAD"
    assert client.get(f"/api/demo/access/link?t={token}").status_code == 410


def test_wrong_codes_run_out_and_then_the_right_code_is_refused(demo_env, clock):
    client = _client(clock)
    _ask(client, "visitor@example.com")
    right = _code(client)
    wrong = "000000" if right != "000000" else "111111"
    for left in (4, 3, 2, 1):
        response = client.post("/api/demo/access/code", json={"email": "visitor@example.com", "code": wrong})
        assert response.json()["code"] == "WRONG_CODE"
        assert response.json()["attemptsLeft"] == left
    last = client.post("/api/demo/access/code", json={"email": "visitor@example.com", "code": wrong})
    assert last.json()["code"] == "CODE_DEAD"
    refused = client.post("/api/demo/access/code", json={"email": "visitor@example.com", "code": right})
    assert refused.status_code == 400
    assert refused.json()["code"] == "CODE_DEAD"


def test_a_code_expires(demo_env, clock):
    client = _client(clock)
    _ask(client, "visitor@example.com")
    code = _code(client)
    clock.advance(minutes=16)
    response = client.post("/api/demo/access/code", json={"email": "visitor@example.com", "code": code})
    assert response.json()["code"] == "CODE_DEAD"


def test_a_mail_failure_says_so_and_counts_against_nothing(demo_env, clock):
    from src.demo.access.mailer import MailError

    client = _client(clock)

    def broken(mail):
        raise MailError("timed out")

    client.app.state.demo_access.mailer.send = broken
    response = _ask(client, "visitor@example.com")
    assert response.status_code == 503
    assert response.json()["code"] == "MAIL_FAILED"
    assert "could not be sent" in response.json()["detail"]
    assert _store(client).codes_sent_since(0) == 0
    assert _store(client).visitor("visitor@example.com") is None


# --------------------------------------------------------------------------
# One session per person
# --------------------------------------------------------------------------


def test_the_session_ends_at_its_length_and_cannot_be_restarted(demo_env, clock):
    client = _client(clock)
    _sign_in(client)
    clock.advance(minutes=44)
    assert client.get("/api/home/summary").status_code == 200
    clock.advance(minutes=2)

    response = client.get("/api/home/summary")
    assert response.status_code == 403
    assert response.json()["code"] == "DEMO_EXPIRED"
    assert response.json()["contactEmail"] == "support@noeinsolutions.com"
    assert client.get("/api/demo/status").json()["access"]["status"] == "ended"

    # Asking again mails an "ended" note, and the page says the usual thing.
    asked = _ask(client, "visitor@example.com")
    assert asked.status_code == 200
    assert asked.json()["status"] == "sent"
    note = _outbox(client)[-1]
    assert "ended" in note.text
    assert not re.search(r"\d{3} \d{3}", note.text)

    # A fresh browser cannot start another one either.
    other = _client(clock)
    other.app.state.demo_access.store.clock = clock
    _ask(other, "visitor@example.com")
    assert other.get("/api/home/summary").status_code == 401


def test_signing_in_again_elsewhere_resumes_the_same_session(demo_env, clock):
    first = _client(clock)
    started = _sign_in(first).json()["access"]["expiresAt"]
    clock.advance(minutes=20)

    second = TestClient(first.app)  # another device: no cookies, same server
    resumed = _sign_in(second).json()["access"]
    assert resumed["expiresAt"] == started
    assert _store(first).visitor("visitor@example.com").sessions == 1


def test_two_spellings_of_one_mailbox_share_one_session(demo_env, clock):
    client = _client(clock)
    _sign_in(client, "Jane.Doe+demo@gmail.com")
    clock.advance(minutes=50)
    _ask(client, "janedoe@googlemail.com")
    assert "ended" in _outbox(client)[-1].text


def test_throwaway_domains_and_nonsense_are_refused(demo_env, clock):
    client = _client(clock)
    assert _ask(client, "someone@mailinator.com").json()["code"] == "BLOCKED_DOMAIN"
    assert _ask(client, "not an address").json()["code"] == "INVALID_EMAIL"


def test_codes_per_address_per_hour(demo_env, clock):
    client = _client(clock)
    for _ in range(3):
        assert _ask(client, "visitor@example.com").status_code == 200
    assert _ask(client, "visitor@example.com").status_code == 429
    clock.advance(minutes=61)
    assert _ask(client, "visitor@example.com").status_code == 200


def test_new_addresses_per_ip_per_day(demo_env, clock):
    client = _client(clock)
    for n in range(5):
        assert _ask(client, f"person{n}@example.com", **{"X-Real-IP": "203.0.113.9"}).status_code == 200
    refused = _ask(client, "person9@example.com", **{"X-Real-IP": "203.0.113.9"})
    assert refused.status_code == 429
    assert _ask(client, "person9@example.com", **{"X-Real-IP": "198.51.100.1"}).status_code == 200


def test_the_global_daily_email_cap_refuses_then_releases(demo_env, clock, monkeypatch):
    monkeypatch.setenv("DEMO_CODES_PER_DAY", "2")
    client = _client(clock)
    assert _ask(client, "a@example.com").status_code == 200
    assert _ask(client, "b@example.org").status_code == 200
    refused = _ask(client, "c@example.net")
    assert refused.status_code == 429
    assert refused.json()["code"] == "RATE_LIMITED"
    clock.advance(days=1, minutes=1)
    assert _ask(client, "c@example.net").status_code == 200


def test_zero_never_means_no_limit(demo_env, clock, monkeypatch):
    monkeypatch.setenv("DEMO_SESSION_MINUTES", "0")
    client = _client(clock)
    assert client.get("/api/demo/status").json()["session"] == {"minutes": 1}


# --------------------------------------------------------------------------
# Mail settings, the relay and the start-up check
# --------------------------------------------------------------------------


def test_neo_names_win_and_the_port_picks_the_tls_mode(monkeypatch):
    from src.demo.access.mailer import sender
    from src.demo.access.settings import AccessSettings

    monkeypatch.setenv("SMTP_HOST", "fallback.example.com")
    monkeypatch.setenv("NEO_SMTP_HOST", "smtp0001.neo.space")
    monkeypatch.setenv("NEO_SMTP_USER", "owner@noeinsolutions.com")
    monkeypatch.setenv("NEO_SMTP_PASS", " pa$$word ")
    monkeypatch.delenv("EMAIL_FROM", raising=False)
    monkeypatch.delenv("SMTP_FROM", raising=False)
    monkeypatch.setenv("NEO_SMTP_PORT", "465")
    settings = AccessSettings.from_env()
    assert settings.smtp_host == "smtp0001.neo.space"
    assert settings.smtp_password == " pa$$word "  # taken exactly as written
    assert settings.tls_mode == "ssl"
    assert settings.mail_from == "owner@noeinsolutions.com"
    assert sender(settings.mail_from) == "Congressional Disclosure Tracker demo <owner@noeinsolutions.com>"

    monkeypatch.setenv("NEO_SMTP_PORT", "587")
    assert AccessSettings.from_env().tls_mode == "starttls"


def test_a_gate_nobody_can_pass_refuses_to_start(demo_env, monkeypatch):
    from src.api.app import create_app

    monkeypatch.setenv("DEMO_MAIL_BACKEND", "smtp")
    for name in ("NEO_SMTP_HOST", "SMTP_HOST", "NEO_SMTP_USER", "SMTP_USER", "NEO_SMTP_PASS", "SMTP_PASS"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(RuntimeError, match="NEO_SMTP_HOST"):
        create_app()


def _smtp_settings(**overrides):
    from src.demo.access.settings import AccessSettings

    values = dict(
        mail_backend="smtp", smtp_host="smtp0001.neo.space", smtp_port=587, smtp_user="owner@noeinsolutions.com",
        smtp_password="secret", mail_from="support@noeinsolutions.com",
    )
    values.update(overrides)
    return AccessSettings(**values)


def test_through_the_relay_the_socket_goes_to_the_relay_and_tls_to_neo(monkeypatch):
    from src.demo.access import mailer as mailer_module

    dialled = []
    server_side, client_side = socket.socketpair()
    server_side.sendall(b"220 fake ready\r\n")

    def fake_connect(address, timeout=None, source_address=None):
        dialled.append(address)
        return client_side

    monkeypatch.setattr(mailer_module.socket, "create_connection", fake_connect)
    client = mailer_module.SmtpMailer(_smtp_settings(mail_relay="mail-relay:2587"))._client()
    try:
        assert dialled == [("mail-relay", 2587)]
        # STARTTLS verifies the certificate against this name, not the relay's.
        assert client._host == "smtp0001.neo.space"
    finally:
        client.close()
        server_side.close()


def test_the_startup_check_signs_in_without_sending(monkeypatch):
    from src.demo.access import mailer as mailer_module

    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            calls.append(("connect", host, port))

        def starttls(self, context=None):
            calls.append(("starttls",))

        def login(self, user, password):
            calls.append(("login", user))

        def mail(self, address):
            calls.append(("mail", address))
            return 250, b"ok"

        def rset(self):
            calls.append(("rset",))

        def send_message(self, message):  # pragma: no cover - must not happen
            calls.append(("send",))

        def close(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(mailer_module.smtplib, "SMTP", FakeSMTP)
    mailer_module.SmtpMailer(_smtp_settings()).check()
    assert calls == [
        ("connect", "smtp0001.neo.space", 587),
        ("starttls",),
        ("login", "owner@noeinsolutions.com"),
        ("mail", "support@noeinsolutions.com"),
        ("rset",),
    ]


def test_a_blocked_port_becomes_the_logged_mail_error(monkeypatch, caplog):
    from src.demo.access import mailer as mailer_module
    from src.demo.access.service import DemoAccess
    from src.demo.access.store import AccessStore

    def timeout(*args, **kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr(mailer_module.smtplib, "SMTP", timeout)
    settings = _smtp_settings()
    access = DemoAccess(settings, AccessStore(":memory:"), mailer_module.SmtpMailer(settings))
    with pytest.raises(mailer_module.MailError):
        access.mailer.check()
    with caplog.at_level("ERROR"):
        access.check_mail()
    assert "NOT usable" in caplog.text


def test_the_relay_forwards_only_to_its_fixed_target():
    from src.demo.access.relay import MailRelay, parse_address

    received = []
    target = socket.create_server(("127.0.0.1", 0))

    def echo_once():
        conn, _ = target.accept()
        data = conn.recv(1024)
        received.append(data)
        conn.sendall(b"echo:" + data)
        conn.close()

    threading.Thread(target=echo_once, daemon=True).start()
    relay = MailRelay(("127.0.0.1", 0), target.getsockname()[:2])
    threading.Thread(target=relay.serve_forever, daemon=True).start()
    try:
        with socket.create_connection(relay.address, timeout=5) as conn:
            # Whatever the client says, the destination does not change.
            conn.sendall(b"CONNECT evil.example.com:25")
            assert conn.recv(1024) == b"echo:CONNECT evil.example.com:25"
        assert received == [b"CONNECT evil.example.com:25"]
    finally:
        relay.close()
        target.close()

    with pytest.raises(ValueError):
        parse_address("smtp0001.neo.space")


def test_the_deploy_seals_the_api_and_opens_only_the_mail_port():
    yaml = pytest.importorskip("yaml")
    compose = yaml.safe_load((Path(__file__).resolve().parents[1] / ".deploy" / "compose.yml").read_text())
    services = compose["services"]
    assert compose["networks"]["internal"]["internal"] is True
    assert services["api"]["networks"] == ["internal"]
    relay = services["mail-relay"]
    assert relay["environment"]["MAIL_RELAY_TARGET"] == "smtp0001.neo.space:587"
    assert "env_file" not in relay  # the relay holds no secrets
    assert services["api"]["environment"]["DEMO_MAIL_RELAY"].startswith("mail-relay:")
    # The session store survives restarts; the snapshot does not need to.
    assert any(str(v).endswith(":/app/data/access") for v in services["api"]["volumes"])
    # No published password on the demo.
    assert "APP_PASSWORD" not in services["api"]["environment"]


# --------------------------------------------------------------------------
# The owner's side
# --------------------------------------------------------------------------


def test_the_owner_gets_one_notice_per_new_person(demo_env, clock, monkeypatch):
    monkeypatch.setenv("DEMO_NOTIFY_EMAIL", "owner@noeinsolutions.com")
    client = _client(clock)
    _sign_in(client)
    notices = [m for m in _outbox(client) if m.to == "owner@noeinsolutions.com"]
    assert len(notices) == 1
    assert "visitor@example.com" in notices[0].text
    assert "http://testserver/admin" in notices[0].text

    other = TestClient(client.app)
    _sign_in(other)  # resuming is not a new person
    assert len([m for m in _outbox(client) if m.to == "owner@noeinsolutions.com"]) == 1


def test_admin_is_a_404_without_a_token(demo_env, clock):
    client = _client(clock)
    for path in ("/admin", "/admin/visitors.csv", "/admin/anything"):
        assert client.get(path).status_code == 404
    assert client.post("/admin/login", data={"token": "x" * 30}).status_code == 404


def _admin(client: TestClient) -> None:
    response = client.post("/admin/login", data={"token": ADMIN_TOKEN}, follow_redirects=False)
    assert response.status_code == 303


def test_admin_sign_in_shows_the_person_and_escapes_what_they_typed(demo_env, clock, monkeypatch):
    monkeypatch.setenv("DEMO_ADMIN_TOKEN", ADMIN_TOKEN)
    client = _client(clock)
    _sign_in(client, "o'brien&co@example.com")
    client.get("/api/tickers/NVDA")

    admin = TestClient(client.app)
    page = admin.get("/admin")
    assert page.status_code == 200
    assert 'name="token"' in page.text  # the form, not the data
    assert "brien" not in page.text
    assert admin.post("/admin/login", data={"token": "wrong-token-wrong-token-wrong"}).status_code == 401
    _admin(admin)

    page = admin.get("/admin")
    assert page.headers["cache-control"] == "no-store"
    assert "noindex" in page.headers["x-robots-tag"]
    assert "o&#x27;brien&amp;co@example.com" in page.text
    assert "o'brien&co@example.com" not in page.text
    assert "NVDA" in page.text


def test_admin_csv_exports_neutralise_formula_cells(demo_env, clock, monkeypatch):
    monkeypatch.setenv("DEMO_ADMIN_TOKEN", ADMIN_TOKEN)
    client = _client(clock)
    _sign_in(client, "=1+2@example.com")
    admin = TestClient(client.app)
    _admin(admin)
    people = admin.get("/admin/visitors.csv")
    assert people.status_code == 200
    assert "'=1+2@example.com" in people.text
    events = admin.get("/admin/events.csv")
    assert "'=1@example.com" in events.text  # the canonical address the events are keyed on


def test_admin_grants_another_session_revokes_and_deletes(demo_env, clock, monkeypatch):
    monkeypatch.setenv("DEMO_ADMIN_TOKEN", ADMIN_TOKEN)
    client = _client(clock)
    _sign_in(client)
    admin = TestClient(client.app)
    _admin(admin)

    # More time on a running session.
    admin.post("/admin/visitor", data={"email": "visitor@example.com", "action": "grant"})
    assert _store(client).visitor("visitor@example.com").expires_at == START + 90 * 60

    # After it ends: a fresh window that starts at the next sign-in.
    clock.advance(minutes=91)
    assert client.get("/api/home/summary").json()["code"] == "DEMO_EXPIRED"
    admin.post("/admin/visitor", data={"email": "visitor@example.com", "action": "grant"})
    assert client.get("/api/home/summary").json()["code"] == "DEMO_SIGNED_OUT"
    clock.advance(minutes=5)
    renewed = _sign_in(client).json()["access"]
    assert renewed["status"] == "active"
    visitor = _store(client).visitor("visitor@example.com")
    assert visitor.sessions == 2
    assert visitor.expires_at == clock.now + 45 * 60

    # Revoke drops every browser at once, and a new code request gets the "ended" note.
    admin.post("/admin/visitor", data={"email": "visitor@example.com", "action": "revoke"})
    assert client.get("/api/home/summary").status_code == 401
    _ask(client, "visitor@example.com")
    assert "switched off" in _outbox(client)[-1].text

    # Delete honours a deletion request: the person and all their usage.
    admin.post("/admin/visitor", data={"email": "visitor@example.com", "action": "delete"})
    assert _store(client).visitor("visitor@example.com") is None
    assert [e for e in _events(client) if e["email"] == "visitor@example.com"] == []


def test_admin_actions_need_the_admin_cookie(demo_env, clock, monkeypatch):
    monkeypatch.setenv("DEMO_ADMIN_TOKEN", ADMIN_TOKEN)
    client = _client(clock)
    _sign_in(client)
    stranger = TestClient(client.app)
    response = stranger.post(
        "/admin/visitor", data={"email": "visitor@example.com", "action": "delete"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert _store(client).visitor("visitor@example.com") is not None
    assert stranger.get("/admin/events.csv").status_code == 404


def test_retention_purge_deletes_the_person_and_their_events(demo_env, clock):
    client = _client(clock)
    _sign_in(client)
    client.get("/api/home/summary")
    clock.advance(days=364)
    assert client.app.state.demo_access.purge() == 0
    clock.advance(days=2)
    assert client.app.state.demo_access.purge() == 1
    assert _store(client).visitor("visitor@example.com") is None
    assert _events(client) == []


def test_unverified_addresses_are_not_kept_for_a_year(demo_env, clock):
    client = _client(clock)
    _ask(client, "someone-else@example.com")  # anyone can type anyone's address
    clock.advance(days=31)
    assert client.app.state.demo_access.purge() == 1
