"""Guardrail: no credential ever reaches a commit.

This repo is public. Its sibling F8_F13Screener leaked a live Telegram bot
token for three and a half months because `config_secret.py` was committed once
and `.gitignore` never listed it, and a committed
`__pycache__/13f_alert.cpython-313.pyc` carried the same token compiled in.
`.gitignore` already listed `__pycache__/`, which does nothing for a file that
is already tracked.

This repo survived the same mistake by accident of a better design: thirteen
`src/__pycache__/*.pyc` files were committed and later removed in 2fe3307, but
`src/config.py` reads every credential through `os.getenv()`, so the bytecode
held only variable names. Keep it that way. A literal in a module is one
`git add` away from being permanent.

The scan covers the tracked working tree, not history: history is immutable, so
failing on it forever would only teach people to skip the test. What matters is
that no *new* credential gets committed.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# Split so this file is not itself a match: "<digits>:<35 token chars>".
TELEGRAM_TOKEN = re.compile(r"[0-9]{8,10}" + ":" + r"[A-Za-z0-9_-]{35}")

# A literal of real length bound to a credential-shaped name, as a mapping key
# (`"password": "..."`) or an assignment (`API_KEY = "..."`). Reading a
# credential from the environment never matches, which is the point.
#
# The name must be a bare identifier or a fully quoted key. Without that, a
# containment check like `if "apiKey=" not in url` matches across the string
# boundary and reports src/polygon_prices.py as a leak.
_SECRET_NAME = (
    r"(?:TOKEN|SECRET|PASSWORD|PASSWD|API_?KEY|ACCESS_KEY|PRIVATE_KEY|CHAT_ID|BEARER)"
)
_VALUE = r"[\"']([^\"'\n]{8,})[\"']"
SECRET_LITERAL = re.compile(
    rf"[\"']\w*{_SECRET_NAME}\w*[\"']\s*:\s*{_VALUE}"
    rf"|(?<![\"'])\b\w*{_SECRET_NAME}\w*\b\s*=\s*{_VALUE}",
    re.IGNORECASE,
)

# Literal values accepted as non-credentials. Paths are deliberately NOT
# allowlisted: a real secret pasted into a test file must still fail. Like the
# sibling repo's UNSTYLED_CLASSES, this list is only ever allowed to shrink.
ALLOWED_LITERALS = frozenset(
    {
        # Shared fixture password for the /api/login round-trip in tests/.
        "secret123",
    }
)

# Names that must never be tracked. `.env.example` is deliberately absent: it
# is the template and carries only empty values and comments.
SECRET_FILENAMES = (".env", ".env.local")

# Files that show the shape of a secret without holding one.
ALLOWED_PATHS = frozenset({"tests/test_no_committed_secrets.py", ".env.example"})

requires_git = pytest.mark.skipif(
    shutil.which("git") is None or not (REPO_ROOT / ".git").exists(),
    reason="not a git checkout",
)


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ("git", "-C", str(REPO_ROOT), "ls-files", "-z"),
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [name for name in out.split("\0") if name]


def _is_ignored(name: str) -> bool:
    return (
        subprocess.run(
            ("git", "-C", str(REPO_ROOT), "check-ignore", "-q", name),
            capture_output=True,
        ).returncode
        == 0
    )


def _scannable_files() -> list[tuple[str, str]]:
    files: list[tuple[str, str]] = []
    for name in _tracked_files():
        if name in ALLOWED_PATHS:
            continue
        path = REPO_ROOT / name
        if not path.is_file():
            continue
        try:
            files.append((name, path.read_text(encoding="utf-8", errors="ignore")))
        except OSError:
            continue
    return files


@requires_git
def test_env_files_are_not_tracked() -> None:
    tracked = set(_tracked_files())
    committed = sorted(name for name in SECRET_FILENAMES if name in tracked)
    assert committed == [], (
        f"{committed} is tracked by git. Run `git rm --cached <file>`, confirm it "
        "is in .gitignore, and rotate every credential it held."
    )


@requires_git
def test_env_files_are_gitignored() -> None:
    unignored = sorted(name for name in SECRET_FILENAMES if not _is_ignored(name))
    assert unignored == [], f"not covered by .gitignore: {unignored}"


@requires_git
def test_no_compiled_python_is_tracked() -> None:
    # .gitignore listing __pycache__/ does nothing for a file already tracked,
    # which is how thirteen .pyc files lived in this repo's history.
    compiled = sorted(
        name
        for name in _tracked_files()
        if name.endswith((".pyc", ".pyo")) or "__pycache__/" in name
    )
    assert compiled == [], (
        f"compiled Python is tracked: {compiled}. Run `git rm --cached` on each. "
        "A .pyc carries any literal its source module held."
    )


@requires_git
def test_no_telegram_token_in_tracked_files() -> None:
    offenders = [name for name, text in _scannable_files() if TELEGRAM_TOKEN.search(text)]
    assert offenders == [], (
        f"Telegram bot token found in tracked files: {offenders}. "
        "Revoke it in BotFather before doing anything else."
    )


@requires_git
def test_no_credential_literals_in_tracked_files() -> None:
    offenders: list[str] = []
    for name, text in _scannable_files():
        for line_no, line in enumerate(text.splitlines(), start=1):
            # os.getenv("API_KEY") and friends are the correct pattern, not a hit.
            if re.search(r"getenv|environ|process\.env|import\.meta\.env", line):
                continue
            for match in SECRET_LITERAL.finditer(line):
                value = next(group for group in match.groups() if group is not None)
                if value in ALLOWED_LITERALS:
                    continue
                offenders.append(f"{name}:{line_no}")
    assert offenders == [], (
        "credential literals in tracked files:\n"
        + "\n".join(offenders)
        + "\nRead the value from the environment instead."
    )
