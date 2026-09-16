"""Email addresses: validation, the canonical form a session is keyed on, blocklist.

A session belongs to a mailbox, not to a spelling of it. ``Jane.Doe+demo@gmail.com``
and ``janedoe@gmail.com`` land in the same inbox, so they share one session:
``canonical`` lower-cases, drops a ``+tag`` everywhere, and drops the dots Gmail
ignores. Mail is still sent to the address as typed.

The blocklist holds the throwaway-inbox services that make "one session per
person" meaningless. It is short on purpose -- the long tail is not worth a
dependency -- and ``DEMO_BLOCKED_EMAIL_DOMAINS`` adds to it.

The demo process has no route to the internet, so there is no MX lookup here:
a second real mailbox gets a second session, and ``docs/DEMO.md`` says so.
"""
from __future__ import annotations

import re

MAX_LENGTH = 254

_SHAPE = re.compile(
    r"^[^@\s<>()\[\],;:\"]{1,64}@[A-Za-z0-9](?:[A-Za-z0-9-]{0,62}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,62}[A-Za-z0-9])?)*\.[A-Za-z]{2,63}$"
)

_DOTLESS_DOMAINS = {"gmail.com", "googlemail.com"}

DISPOSABLE_DOMAINS = frozenset(
    {
        "10minutemail.com", "1secmail.com", "burnermail.io", "dispostable.com",
        "emailondeck.com", "fakeinbox.com", "getnada.com", "guerrillamail.com",
        "guerrillamail.net", "mailinator.com", "maildrop.cc", "mailnesia.com",
        "mintemail.com", "moakt.com", "mohmal.com", "mytemp.email", "sharklasers.com",
        "spamgourmet.com", "temp-mail.org", "tempmail.com", "tempmailo.com",
        "tempr.email", "throwawaymail.com", "tmpmail.org", "trashmail.com", "yopmail.com",
    }
)


def clean(raw: str | None) -> str:
    return (raw or "").strip()


def is_valid(address: str) -> bool:
    return 0 < len(address) <= MAX_LENGTH and bool(_SHAPE.match(address))


def domain(address: str) -> str:
    return address.rsplit("@", 1)[-1].lower()


def canonical(address: str) -> str:
    local, _, host = address.strip().lower().rpartition("@")
    local = local.split("+", 1)[0]
    if host in _DOTLESS_DOMAINS:
        local = local.replace(".", "")
        host = "gmail.com"
    return f"{local}@{host}"


def is_blocked(address: str, extra_domains: frozenset[str] = frozenset()) -> bool:
    host = domain(address)
    return host in DISPOSABLE_DOMAINS or host in extra_domains
