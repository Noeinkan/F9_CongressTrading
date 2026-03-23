from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

if __name__ == "__main__" and (__package__ is None or __package__ == ""):
    import sys
    from pathlib import Path as _Path

    sys.path.append(str(_Path(__file__).resolve().parents[1]))
    __package__ = "src"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Congress public-disclosure tracker")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("ingest-house", help="Scarica e ingesta PTR House (2022+)")
    sub.add_parser("ingest-senate", help="Ingesta PTR Senate (manuale)")
    sub.add_parser("ingest-all", help="Esegue ingestione House + Senate")

    export = sub.add_parser("export-csv", help="Esporta CSV normalizzato da SQLite")
    export.add_argument("--out", type=Path, default=Path("data/congress_trades.csv"))

    export_fd = sub.add_parser("export-fd-csv", help="Esporta CSV dai report FD")
    export_fd.add_argument("--out", type=Path, default=Path("data/fd_filings.csv"))

    export_review = sub.add_parser("export-review-csv", help="Esporta CSV delle transazioni da revisionare")
    export_review.add_argument("--out", type=Path, default=Path("data/review_queue.csv"))

    dashboard = sub.add_parser("dashboard", help="Avvia la dashboard Streamlit")
    dashboard.add_argument("--server-port", type=int, default=8501)
    dashboard.add_argument("--server-address", default="127.0.0.1")

    return parser


def main() -> None:
    from .export_csv import export_csv, export_fd_csv, export_review_csv
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
    elif args.command == "export-review-csv":
        export_review_csv(args.out)
    elif args.command == "dashboard":
        app_path = Path(__file__).resolve().parents[1] / "streamlit_app.py"
        command = [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(app_path),
            "--server.port",
            str(args.server_port),
            "--server.address",
            args.server_address,
        ]
        raise SystemExit(subprocess.call(command))


if __name__ == "__main__":
    main()
