"""Phase 6 guardrail: no Streamlit imports under src/ or tests/."""

from __future__ import annotations

import re
from pathlib import Path

STREAMLIT_IMPORT = re.compile(r"^\s*(import streamlit|from streamlit\b)")


def _find_streamlit_imports(root: Path) -> list[str]:
    hits: list[str] = []
    for path in sorted(root.rglob("*.py")):
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if STREAMLIT_IMPORT.match(line):
                hits.append(f"{path}:{line_no}: {line.strip()}")
    return hits


def test_no_streamlit_imports_under_src_or_tests() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    hits = _find_streamlit_imports(repo_root / "src") + _find_streamlit_imports(
        repo_root / "tests"
    )
    assert hits == [], "Streamlit imports found:\n" + "\n".join(hits)
