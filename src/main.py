from __future__ import annotations

import argparse
import os
from pathlib import Path
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
    export.add_argument(
        "--polygon-pnl",
        action="store_true",
        help="Aggiunge colonne stima prezzi/return via Polygon (cache SQLite; richiede POLYGON_API_KEY salvo --polygon-pnl-cache-only).",
    )
    export.add_argument(
        "--polygon-pnl-cache-only",
        action="store_true",
        help="Solo lettura da polygon_daily_bar_cache (nessuna chiamata API).",
    )
    export.add_argument(
        "--polygon-pnl-refresh",
        action="store_true",
        help="Riscarica barre giornaliere da Polygon per ogni ticker anche se la cache copre l'intervallo.",
    )
    export.add_argument(
        "--as-of",
        type=str,
        default=None,
        metavar="YYYY-MM-DD",
        help="Data di riferimento per prezzo 'as of' (default: oggi). Usato con --polygon-pnl.",
    )

    warm_poly = sub.add_parser(
        "warm-polygon-price-cache",
        help="Precarica in SQLite le barre giornaliere Polygon per ticker/date dei trade (utile prima della dashboard).",
    )
    warm_poly.add_argument(
        "--as-of",
        type=str,
        default=None,
        metavar="YYYY-MM-DD",
        help="Data inclusa nel range (default: oggi).",
    )
    warm_poly.add_argument(
        "--refresh",
        action="store_true",
        help="Forza riscarico API anche se la cache copre l'intervallo.",
    )
    warm_poly.add_argument(
        "--cache-only",
        action="store_true",
        help="Non chiamare Polygon (no-op utile per test; di solito non serve).",
    )
    warm_poly.add_argument(
        "--progress-every",
        type=int,
        default=25,
        metavar="N",
        help="Stampa una riga di avanzamento ogni N ticker (0 = silenzioso, default 25).",
    )

    export_fd = sub.add_parser("export-fd-csv", help="Esporta CSV dai report FD")
    export_fd.add_argument("--out", type=Path, default=Path("data/fd_filings.csv"))

    export_review = sub.add_parser("export-review-csv", help="Esporta CSV delle transazioni da revisionare")
    export_review.add_argument("--out", type=Path, default=Path("data/review_queue.csv"))

    rr = sub.add_parser(
        "re-resolve-tickers",
        help="Ricalcola ticker/issuer su tutte le transazioni SQLite (no re-parse PDF; usa testo disclosure + cache/API)",
    )
    rr.add_argument(
        "--clear-asset-cache",
        action="store_true",
        help="Svuota asset_resolution_cache prima del ricalcolo. Di solito non serve: le voci fallite (ticker vuoto, source none/skipped) vengono ri-interrogate automaticamente.",
    )

    return parser


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
        from datetime import date as date_cls

        as_of: date_cls | None = None
        if getattr(args, "as_of", None):
            try:
                as_of = date_cls.fromisoformat(str(args.as_of).strip()[:10])
            except ValueError:
                raise SystemExit("Argomento --as-of non valido (usa YYYY-MM-DD).") from None
        export_csv(
            args.out,
            polygon_pnl=bool(getattr(args, "polygon_pnl", False)),
            polygon_pnl_cache_only=bool(getattr(args, "polygon_pnl_cache_only", False)),
            polygon_pnl_refresh=bool(getattr(args, "polygon_pnl_refresh", False)),
            as_of=as_of,
        )
    elif args.command == "export-fd-csv":
        export_fd_csv(args.out)
    elif args.command == "export-review-csv":
        export_review_csv(args.out)
    elif args.command == "warm-polygon-price-cache":
        from datetime import date as date_cls

        from .db import get_connection, init_db
        from .polygon_prices import warm_polygon_price_cache_for_db

        as_of = date_cls.today()
        if getattr(args, "as_of", None):
            try:
                as_of = date_cls.fromisoformat(str(args.as_of).strip()[:10])
            except ValueError:
                raise SystemExit("Argomento --as-of non valido (usa YYYY-MM-DD).") from None
        cache_only = bool(getattr(args, "cache_only", False))
        if not cache_only and not (os.getenv("POLYGON_API_KEY") or "").strip():
            raise SystemExit("POLYGON_API_KEY mancante (oppure usa --cache-only per non chiamare Polygon).")

        conn = get_connection()
        init_db(conn)
        n = warm_polygon_price_cache_for_db(
            conn,
            as_of=as_of,
            force_refetch=bool(getattr(args, "refresh", False)),
            cache_only=cache_only,
            progress_every=int(getattr(args, "progress_every", 25) or 0),
        )
        conn.close()
        print(f"warm-polygon-price-cache: elaborati {n:,} ticker distinti.")
        # Reach back into the module to surface skip/cache-hit counters if the
        # logger wrote them. We do this by re-querying the cache coverage after
        # the run, so the user can spot-check whether Polygon returned data.
        if not cache_only:
            from .db import get_connection as _gc
            _conn = _gc()
            try:
                cached = _conn.execute(
                    "SELECT COUNT(DISTINCT ticker) AS c FROM polygon_daily_bar_cache"
                ).fetchone()["c"]
                print(
                    f"  → {cached:,} ticker coperti da polygon_daily_bar_cache. "
                    f"({n - cached:,} senza dati — probabilmente ticker non quotati o asset non-equity.)"
                )
            finally:
                _conn.close()
    elif args.command == "re-resolve-tickers":
        from .db import get_connection, init_db
        from .ingest_house import re_resolve_all_transaction_tickers

        conn = get_connection()
        init_db(conn)
        if args.clear_asset_cache:
            conn.execute("DELETE FROM asset_resolution_cache")
            conn.commit()
            print("Cleared asset_resolution_cache (Polygon/OpenFIGI will run per distinct asset).")
        # Fail fast: without an API key every empty-ticker row would just be rewritten to
        # match_source='none', masking the real cause. Opt out with CONGRESS_RE_RESOLVE_NO_KEY_OK=1
        # for sandboxed runs (e.g. CI) that intentionally exercise the no-network path.
        if (
            not (os.getenv("POLYGON_API_KEY") or "").strip()
            and not (os.getenv("OPENFIGI_API_KEY") or "").strip()
            and (os.getenv("CONGRESS_RE_RESOLVE_NO_KEY_OK") or "").strip().lower()
            not in {"1", "true", "yes", "on"}
        ):
            raise SystemExit(
                "re-resolve-tickers needs at least one of POLYGON_API_KEY or OPENFIGI_API_KEY. "
                "Without keys, all empty-ticker rows are written back as match_source='none' "
                "and the cache silently becomes useless. Set CONGRESS_RE_RESOLVE_NO_KEY_OK=1 "
                "to run anyway (no network lookups will happen)."
            )
        processed = re_resolve_all_transaction_tickers(conn)
        print(f"Processed {processed:,} transactions.")
        conn.close()


if __name__ == "__main__":
    main()
