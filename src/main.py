from __future__ import annotations

import argparse
from pathlib import Path

if __name__ == "__main__" and (__package__ is None or __package__ == ""):
    import sys
    from pathlib import Path as _Path

    sys.path.append(str(_Path(__file__).resolve().parents[1]))
    __package__ = "src"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Congress PTR pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("ingest-house", help="Scarica e ingesta PTR House (2022+)")
    sub.add_parser("ingest-senate", help="Ingesta PTR Senate (manuale)")
    sub.add_parser("ingest-all", help="Esegue ingestione House + Senate")

    export = sub.add_parser("export-csv", help="Esporta CSV dalla cache SQLite")
    export.add_argument("--out", type=Path, default=Path("data/congress_trades.csv"))

    export_fd = sub.add_parser("export-fd-csv", help="Esporta CSV dai report FD")
    export_fd.add_argument("--out", type=Path, default=Path("data/fd_filings.csv"))

    return parser


def main() -> None:
    from .export_csv import export_csv, export_fd_csv
    from .ingest_house import ingest_house
    from .ingest_senate import ingest_senate

    parser = build_parser()
    args = parser.parse_args()

    if args.command == "ingest-house":
        ingest_house()
    elif args.command == "ingest-senate":
        ingest_senate()
    elif args.command == "ingest-all":
        ingest_house()
        ingest_senate()
    elif args.command == "export-csv":
        export_csv(args.out)
    elif args.command == "export-fd-csv":
        export_fd_csv(args.out)


if __name__ == "__main__":
    main()
