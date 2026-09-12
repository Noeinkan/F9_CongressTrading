"""Unpack the committed demo snapshot into a runnable SQLite file.

The fixture is committed gzipped (9 MB instead of 42 MB); SQLite cannot read a
gzip stream, so the demo process needs it expanded once, at deploy time or
before running the demo locally. Idempotent: skips the work when the expanded
file is already newer than the archive.

    python scripts/unpack_demo_snapshot.py
    python scripts/unpack_demo_snapshot.py --out /var/lib/congress-demo/demo.sqlite --force
"""
from __future__ import annotations

import argparse
import gzip
import shutil
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE = BASE_DIR / "demo" / "fixtures" / "demo-snapshot.sqlite.gz"
DEFAULT_OUT = BASE_DIR / "data" / "db" / "demo-snapshot.sqlite"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--force", action="store_true", help="Re-expand even if up to date.")
    args = ap.parse_args(argv)

    if not args.archive.exists():
        print(f"Demo snapshot not found: {args.archive}", file=sys.stderr)
        print("Build one with: python scripts/freeze_demo_data.py", file=sys.stderr)
        return 1

    if (
        not args.force
        and args.out.exists()
        and args.out.stat().st_mtime >= args.archive.stat().st_mtime
    ):
        print(f"Up to date: {args.out} ({args.out.stat().st_size / 1048576:.1f} MB)")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_suffix(args.out.suffix + ".partial")
    with gzip.open(args.archive, "rb") as src, open(tmp, "wb") as dst:
        shutil.copyfileobj(src, dst)
    tmp.replace(args.out)
    print(f"Unpacked {args.out} ({args.out.stat().st_size / 1048576:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
