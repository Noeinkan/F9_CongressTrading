"""Sending the sign-in email -- the one message the demo process may send.

``SmtpMailer`` speaks plain SMTP through the standard library, so nothing new is
installed. In production it signs in to the Neo mailbox that hosts
noeinsolutions.com mail -- the same account Capsar and the SearchForAlpha demo
send from -- on port 587 with STARTTLS. Not 465: the Hetzner server blocks
outbound 465 (and 25), so a connection there hangs until the timeout.

**The relay.** The demo API sits on a Docker network with no route out
(``.deploy/compose.yml``). The one door is a relay container that forwards to the
mail server's ``host:port`` and nowhere else (``relay.py``). When
``DEMO_MAIL_RELAY`` is set, the socket is dialled to the relay while the
conversation -- STARTTLS, certificate check, login -- is still held with
``smtp0001.neo.space`` by name, so the relay only ever carries ciphertext and the
certificate is verified against the real mail server.

``check`` signs in, offers the From address and cancels, so nothing is sent. The
server runs it once at start and logs the result: a blocked port, a changed
password or a missing alias is otherwise invisible until a visitor asks for a code.

The login is the owner's mailbox; the From address is
``support@noeinsolutions.com`` (``EMAIL_FROM``), which Neo accepts only as an
alias of that mailbox -- otherwise "553 Sender address rejected: not owned by user".

``ConsoleMailer`` logs the message instead and keeps it in ``outbox``: for a local
run without a mail account, and for the tests.

Sending happens inside the request, on purpose. It costs a second or two, but the
visitor is then told the truth -- "sent" or "could not send" -- instead of being
sent to wait for an email that is never coming.
"""
from __future__ import annotations

import logging
import smtplib
import socket
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid, parseaddr

from .settings import AccessSettings

logger = logging.getLogger(__name__)

SENDER_NAME = "Congressional Disclosure Tracker demo"
TIMEOUT_SECONDS = 15


def sender(mail_from: str) -> str:
    """``mail_from`` with a display name, unless it already carries one."""
    name, address = parseaddr(mail_from)
    return mail_from if name or not address else formataddr((SENDER_NAME, address))


class MailError(Exception):
    """The email could not be handed to the mail server."""


@dataclass(frozen=True)
class Mail:
    to: str
    subject: str
    text: str
    html: str


class ConsoleMailer:
    def __init__(self) -> None:
        self.outbox: list[Mail] = []

    def check(self) -> None:
        return None

    def send(self, mail: Mail) -> None:
        self.outbox.append(mail)
        logger.warning("DEMO_MAIL_BACKEND=console, not sending. To %s: %s\n%s", mail.to, mail.subject, mail.text)


class _RelaySMTP(smtplib.SMTP):
    """SMTP that dials ``relay`` but talks to (and verifies TLS for) the host it was given."""

    def __init__(self, *args, relay: tuple[str, int], **kwargs) -> None:
        self._relay = relay
        super().__init__(*args, **kwargs)

    def _get_socket(self, host, port, timeout):  # noqa: D401 - smtplib hook
        return socket.create_connection(self._relay, timeout, self.source_address)


class _RelaySMTP_SSL(smtplib.SMTP_SSL):
    def __init__(self, *args, relay: tuple[str, int], **kwargs) -> None:
        self._relay = relay
        super().__init__(*args, **kwargs)

    def _get_socket(self, host, port, timeout):  # noqa: D401 - smtplib hook
        raw = socket.create_connection(self._relay, timeout, self.source_address)
        return self.context.wrap_socket(raw, server_hostname=self._host)


class SmtpMailer:
    def __init__(self, settings: AccessSettings) -> None:
        self.settings = settings

    def _client(self) -> smtplib.SMTP:
        s = self.settings
        relay = s.relay_address
        if s.tls_mode == "ssl":
            context = ssl.create_default_context()
            if relay:
                return _RelaySMTP_SSL(s.smtp_host, s.smtp_port, timeout=TIMEOUT_SECONDS, context=context, relay=relay)
            return smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=TIMEOUT_SECONDS, context=context)
        if relay:
            return _RelaySMTP(s.smtp_host, s.smtp_port, timeout=TIMEOUT_SECONDS, relay=relay)
        return smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=TIMEOUT_SECONDS)

    def _session(self) -> smtplib.SMTP:
        """Connected, encrypted and signed in; use as a context manager."""
        s = self.settings
        client = self._client()
        try:
            if s.tls_mode == "starttls":
                client.starttls(context=ssl.create_default_context())
            if s.smtp_user:
                client.login(s.smtp_user, s.smtp_password)
        except BaseException:
            client.close()
            raise
        return client

    def check(self) -> None:
        """Sign in, offer the From address, cancel. Sends nothing. Raises ``MailError`` on any refusal."""
        address = parseaddr(self.settings.mail_from)[1] or self.settings.smtp_user
        try:
            with self._session() as client:
                code, reply = client.mail(address)
                client.rset()
        except (OSError, smtplib.SMTPException) as exc:
            raise MailError(f"{type(exc).__name__}: {exc}") from exc
        if code != 250:
            raise MailError(f"sender {address} refused: {code} {reply.decode(errors='replace')}")

    def send(self, mail: Mail) -> None:
        s = self.settings
        message = EmailMessage()
        message["From"] = sender(s.mail_from)
        message["To"] = mail.to
        message["Subject"] = mail.subject
        message["Date"] = formatdate(localtime=False)
        domain = parseaddr(s.mail_from)[1].rpartition("@")[2] or None
        message["Message-ID"] = make_msgid(domain=domain)
        message["Auto-Submitted"] = "auto-generated"
        message.set_content(mail.text)
        message.add_alternative(mail.html, subtype="html")
        try:
            with self._session() as client:
                client.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            # The recipient's domain only: never the full address, never the code.
            logger.error("demo email to @%s failed: %s", mail.to.rpartition("@")[2], exc)
            raise MailError(str(exc)) from exc


def build_mailer(settings: AccessSettings) -> ConsoleMailer | SmtpMailer:
    return ConsoleMailer() if settings.mail_backend == "console" else SmtpMailer(settings)
