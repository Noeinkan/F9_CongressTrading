from __future__ import annotations

import argparse
from pathlib import Path
import platform
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
    sub.add_parser(
        "verify-house-coverage",
        help="Verifica metadata FD House su disco e freshness fd_filings (anni da HOUSE_COVERAGE_MIN_YEAR)",
    )
    sub.add_parser("ingest-senate", help="Ingesta PTR Senate (manuale)")
    sub.add_parser("ingest-all", help="Esegue ingestione House + Senate")

    dl = sub.add_parser(
        "download-house-fd",
        help="Scarica bulk FD annuali (.zip) dal Clerk della House in data/raw/house/",
    )
    dl.add_argument(
        "--years",
        type=int,
        nargs="*",
        default=None,
        metavar="YEAR",
        help="Anni (default: da START_YEAR config fino all'anno corrente)",
    )
    dl.add_argument("--overwrite", action="store_true", help="Riscarica anche se .txt già presente")
    dl.add_argument(
        "--zip-only",
        action="store_true",
        help="Solo zip; l'estrazione avviene al prossimo ingest-house",
    )

    export = sub.add_parser("export-csv", help="Esporta CSV normalizzato da SQLite")
    export.add_argument("--out", type=Path, default=Path("data/congress_trades.csv"))

    export_fd = sub.add_parser("export-fd-csv", help="Esporta CSV dai report FD")
    export_fd.add_argument("--out", type=Path, default=Path("data/fd_filings.csv"))

    export_review = sub.add_parser("export-review-csv", help="Esporta CSV delle transazioni da revisionare")
    export_review.add_argument("--out", type=Path, default=Path("data/review_queue.csv"))

    dashboard = sub.add_parser("dashboard", help="Avvia la dashboard Streamlit")
    dashboard.add_argument("--server-port", type=int, default=8501)
    dashboard.add_argument("--server-address", default="127.0.0.1")

    refresh_dashboard = sub.add_parser(
        "refresh-dashboard",
        help="Aggiorna ingest/export e riavvia la dashboard Streamlit",
    )
    refresh_dashboard.add_argument("--server-port", type=int, default=8501)
    refresh_dashboard.add_argument("--server-address", default="127.0.0.1")

    sub.add_parser(
        "re-resolve-tickers",
        help="Ricalcola ticker/issuer su tutte le transazioni SQLite (no re-parse PDF; usa testo disclosure + cache/API)",
    )

    return parser


def _run_dashboard(*, server_port: int, server_address: str) -> int:
    app_path = Path(__file__).resolve().parents[1] / "streamlit_app.py"
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--server.port",
        str(server_port),
        "--server.address",
        server_address,
    ]
    return subprocess.call(command)


def _find_pids_listening_on_port(port: int) -> list[int]:
    system = platform.system().lower()
    if system == "windows":
        result = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            capture_output=True,
            text=True,
            check=False,
        )
        pids: list[int] = []
        target = f":{port}"
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) < 5:
                continue
            if parts[0].upper() != "TCP":
                continue
            local_address = parts[1]
            state = parts[3].upper()
            pid_text = parts[4]
            if not local_address.endswith(target):
                continue
            if state != "LISTENING":
                continue
            if pid_text.isdigit():
                pids.append(int(pid_text))
        return sorted(set(pids))

    result = subprocess.run(
        ["lsof", "-ti", f"tcp:{port}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return sorted({int(line.strip()) for line in result.stdout.splitlines() if line.strip().isdigit()})


def _stop_processes_on_port(port: int) -> None:
    pids = _find_pids_listening_on_port(port)
    for pid in pids:
        if platform.system().lower() == "windows":
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=False)
        else:
            subprocess.run(["kill", "-9", str(pid)], check=False)


def _refresh_dashboard(*, server_port: int, server_address: str) -> int:
    from .export_csv import export_csv, export_fd_csv, export_review_csv
    from .ingest_house import ingest_house
    from .ingest_senate import ingest_senate

    ingest_house()
    ingest_senate()
    export_csv(Path("data/congress_trades.csv"))
    export_fd_csv(Path("data/fd_filings.csv"))
    export_review_csv(Path("data/review_queue.csv"))
    _stop_processes_on_port(server_port)
    return _run_dashboard(server_port=server_port, server_address=server_address)


def main() -> None:
    from datetime import datetime

    from .config import START_YEAR
    from .export_csv import export_csv, export_fd_csv, export_review_csv
    from .ingest_house import ingest_house
    from .ingest_senate import ingest_senate

    parser = build_parser()
    args = parser.parse_args()

    if args.command == "download-house-fd":
        from .download_house_fd import download_house_fd_bulk

        if args.years is None:
            years = list(range(START_YEAR, datetime.now().year + 1))
        else:
            years = list(args.years)
        download_house_fd_bulk(years, overwrite=args.overwrite, extract=not args.zip_only)
        return

    if args.command == "ingest-house":
        ingest_house()
    elif args.command == "verify-house-coverage":
        from .db import get_connection, init_db
        from .house_coverage import print_house_coverage_report

        conn = get_connection()
        init_db(conn)
        print_house_coverage_report(conn)
        conn.close()
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
        raise SystemExit(_run_dashboard(server_port=args.server_port, server_address=args.server_address))
    elif args.command == "refresh-dashboard":
        raise SystemExit(_refresh_dashboard(server_port=args.server_port, server_address=args.server_address))
    elif args.command == "re-resolve-tickers":
        from .db import get_connection, init_db
        from .ingest_house import re_resolve_all_transaction_tickers

        conn = get_connection()
        init_db(conn)
        processed = re_resolve_all_transaction_tickers(conn)
        print(f"Processed {processed:,} transactions.")
        conn.close()


if __name__ == "__main__":
    main()
