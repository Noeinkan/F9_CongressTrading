from __future__ import annotations

import csv
from pathlib import Path

from .db import get_connection


def export_csv(out_path: Path) -> None:
    conn = get_connection()
    cursor = conn.execute(
        """
        SELECT member, chamber, filing_date, transaction_date, asset,
               ticker, transaction_type, amount_range, source_url
        FROM trades
        ORDER BY transaction_date DESC
        """
    )
    rows = cursor.fetchall()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "member",
                "chamber",
                "filing_date",
                "transaction_date",
                "asset",
                "ticker",
                "transaction_type",
                "amount_range",
                "source_url",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row["member"],
                    row["chamber"],
                    row["filing_date"],
                    row["transaction_date"],
                    row["asset"],
                    row["ticker"],
                    row["transaction_type"],
                    row["amount_range"],
                    row["source_url"],
                ]
            )
    conn.close()
    print(f"CSV export completato: {out_path}")


def export_fd_csv(out_path: Path) -> None:
    conn = get_connection()
    cursor = conn.execute(
        """
        SELECT
            member,
            chamber,
            filing_type,
            state_district,
            year,
            filing_date,
            doc_id,
            MIN(source_file) AS source_file
        FROM fd_filings
        GROUP BY
            member, chamber, filing_type, state_district,
            year, filing_date, doc_id
        ORDER BY filing_date DESC
        """
    )
    rows = cursor.fetchall()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "member",
                "chamber",
                "filing_type",
                "state_district",
                "year",
                "filing_date",
                "doc_id",
                "source_file",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row["member"],
                    row["chamber"],
                    row["filing_type"],
                    row["state_district"],
                    row["year"],
                    row["filing_date"],
                    row["doc_id"],
                    row["source_file"],
                ]
            )
    conn.close()
    print(f"CSV FD export completato: {out_path}")


if __name__ == "__main__":
    export_csv(Path("data/congress_trades.csv"))
