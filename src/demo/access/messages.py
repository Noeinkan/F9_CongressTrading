"""What the gate says: the privacy note and the three emails.

The sign-in pages themselves are React routes (``frontend/src/routes/Access*.tsx``);
the words that carry a number or a promise -- the session length, the retention
period, the contact address -- come from here through ``/api/demo/status``, so
the form, the emails and the admin page cannot disagree.
"""
from __future__ import annotations

import html
import time

from .mailer import Mail
from .settings import AccessSettings
from .store import Visitor

PRODUCT = "Congressional Disclosure Tracker"


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def fmt_date(ts: float | None) -> str:
    if not ts:
        return "—"
    day = time.gmtime(ts)
    return f"{day.tm_mday} {time.strftime('%b %Y', day)}"


def fmt_time(ts: float | None) -> str:
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(ts)) if ts else "—"


def retention_phrase(days: int) -> str:
    months = round(days / 30)
    if months >= 1 and abs(days - months * 30) <= 5:
        return "1 month" if months == 1 else f"{months} months"
    return "1 day" if days == 1 else f"{days} days"


def privacy(settings: AccessSettings) -> list[dict[str, str]]:
    """The three paragraphs under the email field: what, why, for how long."""
    return [
        {
            "title": "What is stored.",
            "text": (
                "Your email address, when you sign in, the IP address you sign in from, and which parts "
                "of the demo you open (pages, members and tickers)."
            ),
        },
        {
            "title": "Why.",
            "text": (
                f"To give each person one {settings.session_minutes}-minute session, and to see how the demo "
                "is used so it can get better. Nothing is sold or shared, and you are not added to any mailing list."
            ),
        },
        {
            "title": "For how long.",
            "text": (
                f"Deleted {retention_phrase(settings.retention_days)} after your last visit, or as soon as you "
                f"ask: {settings.contact_email}."
            ),
        },
    ]


_MAIL_STYLE = "font:15px/1.55 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#111;max-width:480px"


def code_mail(settings: AccessSettings, *, to: str, code: str, link: str) -> Mail:
    spaced = f"{code[:3]} {code[3:]}"
    minutes = settings.session_minutes
    text = (
        f"Your {PRODUCT} demo sign-in code is {spaced}\n\n"
        f"Or open this link: {link}\n\n"
        f"The code and the link work once, for {settings.code_minutes} minutes.\n"
        f"Your first sign-in starts your {minutes}-minute session with the demo.\n\n"
        "If you did not ask for this, ignore it: nothing happens without the code.\n"
    )
    body = (
        f'<div style="{_MAIL_STYLE}">'
        f"<p>Your {PRODUCT} demo sign-in code is</p>"
        f'<p style="font:700 30px/1 ui-monospace,Menlo,Consolas,monospace;letter-spacing:.2em;margin:18px 0">{esc(spaced)}</p>'
        f'<p><a href="{esc(link)}" style="display:inline-block;background:#fd7e14;color:#fff;padding:11px 16px;'
        'border-radius:4px;text-decoration:none;font-weight:700">Open the demo</a></p>'
        f'<p style="color:#555;font-size:13px">The code and the link work once, for {settings.code_minutes} minutes. '
        f"Your first sign-in starts your {minutes}-minute session. If you did not ask for this, ignore it.</p>"
        "</div>"
    )
    return Mail(to=to, subject=f"{spaced} is your {PRODUCT} demo code", text=text, html=body)


def ended_mail(settings: AccessSettings, *, to: str, visitor: Visitor) -> Mail:
    if visitor.revoked_at:
        line = "Demo access for this address has been switched off."
    else:
        line = (
            f"The {settings.session_minutes}-minute demo session for this address ended on "
            f"{fmt_date(visitor.expires_at)}."
        )
    text = (
        f"Someone asked to sign in to the {PRODUCT} demo with this address.\n\n{line}\n\n"
        f"If you would like more time, or to talk about using it for real, write to {settings.contact_email}.\n"
    )
    body = (
        f'<div style="{_MAIL_STYLE}">'
        f"<p>Someone asked to sign in to the {PRODUCT} demo with this address.</p><p>{esc(line)}</p>"
        "<p>If you would like more time, or to talk about using it for real, write to "
        f'<a href="mailto:{esc(settings.contact_email)}">{esc(settings.contact_email)}</a>.</p>'
        "</div>"
    )
    return Mail(to=to, subject=f"Your {PRODUCT} demo session", text=text, html=body)


def signup_notice(settings: AccessSettings, *, visitor: Visitor, admin_url: str) -> Mail:
    """The owner's one line per new person (``DEMO_NOTIFY_EMAIL``)."""
    line = f"{visitor.address} started a {settings.session_minutes}-minute session on the {PRODUCT} demo."
    text = f"{line}\n\nEverything they open is on the admin page: {admin_url}\n"
    body = (
        f'<div style="{_MAIL_STYLE}"><p>{esc(line)}</p>'
        f'<p style="color:#555;font-size:13px">Everything they open is on the '
        f'<a href="{esc(admin_url)}">admin page</a>.</p></div>'
    )
    return Mail(to=settings.notify_email, subject=f"New demo sign-up: {visitor.address}", text=text, html=body)
