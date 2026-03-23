from __future__ import annotations

import csv
from pathlib import Path

from .db import get_connection


def export_csv(out_path: Path) -> None:
    conn = get_connection()
    cursor = conn.execute(
        """
        SELECT
            m.full_name AS member,
            f.chamber AS chamber,
            f.filing_type AS filing_type,
            f.filing_date AS filing_date,
            t.transaction_date AS transaction_date,
            t.owner_type AS owner_type,
            t.asset_name_raw AS asset_name_raw,
            t.asset_name_normalized AS asset_name_normalized,
            t.asset_type AS asset_type,
            COALESCE(i.issuer_name, '') AS issuer_name,
            COALESCE(i.sector, '') AS sector,
            COALESCE(i.industry, '') AS industry,
            t.ticker AS ticker,
            t.transaction_type AS transaction_type,
            t.amount_low AS amount_low,
            t.amount_high AS amount_high,
            t.amount_range_raw AS amount_range_raw,
            t.confidence_score AS confidence_score,
            t.review_status AS review_status,
            f.source_url AS source_url,
            f.raw_document_path AS raw_document_path
        FROM transactions t
        JOIN filings f ON f.id = t.filing_id
        JOIN members m ON m.id = f.member_id
        LEFT JOIN issuers i ON i.id = t.issuer_id
        ORDER BY t.transaction_date DESC, f.filing_date DESC, m.full_name ASC
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
                "filing_date",
                "transaction_date",
                "owner_type",
                "asset_name_raw",
                "asset_name_normalized",
                "asset_type",
                "issuer_name",
                "sector",
                "industry",
                "ticker",
                "transaction_type",
                "amount_low",
                "amount_high",
                "amount_range_raw",
                "confidence_score",
                "review_status",
                "source_url",
                "raw_document_path",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row["member"],
                    row["chamber"],
                    row["filing_type"],
                    row["filing_date"],
                    row["transaction_date"],
                    row["owner_type"],
                    row["asset_name_raw"],
                    row["asset_name_normalized"],
                    row["asset_type"],
                    row["issuer_name"],
                    row["sector"],
                    row["industry"],
                    row["ticker"],
                    row["transaction_type"],
                    row["amount_low"],
                    row["amount_high"],
                    row["amount_range_raw"],
                    row["confidence_score"],
                    row["review_status"],
                    row["source_url"],
                    row["raw_document_path"],
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


def export_review_csv(out_path: Path) -> None:
    conn = get_connection()
    cursor = conn.execute(
        """
        SELECT
            rq.reason,
            rq.status,
            rq.notes,
            m.full_name AS member,
            f.chamber,
            f.filing_type,
            f.filing_date,
            t.transaction_date,
            t.asset_name_raw,
            t.asset_name_normalized,
            t.asset_type,
            COALESCE(i.sector, '') AS sector,
            COALESCE(i.industry, '') AS industry,
            t.ticker,
            t.transaction_type,
            t.amount_range_raw,
            t.confidence_score,
            t.review_status,
            f.raw_document_path,
            t.source_page,
            t.source_row
        FROM review_queue rq
        JOIN transactions t ON t.id = rq.transaction_id
        JOIN filings f ON f.id = t.filing_id
        JOIN members m ON m.id = f.member_id
        LEFT JOIN issuers i ON i.id = t.issuer_id
        ORDER BY rq.updated_at DESC, f.filing_date DESC
        """
    )
    rows = cursor.fetchall()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "reason",
                "status",
                "notes",
                "member",
                "chamber",
                "filing_type",
                "filing_date",
                "transaction_date",
                "asset_name_raw",
                "asset_name_normalized",
                "asset_type",
                "sector",
                "industry",
                "ticker",
                "transaction_type",
                "amount_range_raw",
                "confidence_score",
                "review_status",
                "raw_document_path",
                "source_page",
                "source_row",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row["reason"],
                    row["status"],
                    row["notes"],
                    row["member"],
                    row["chamber"],
                    row["filing_type"],
                    row["filing_date"],
                    row["transaction_date"],
                    row["asset_name_raw"],
                    row["asset_name_normalized"],
                    row["asset_type"],
                    row["sector"],
                    row["industry"],
                    row["ticker"],
                    row["transaction_type"],
                    row["amount_range_raw"],
                    row["confidence_score"],
                    row["review_status"],
                    row["raw_document_path"],
                    row["source_page"],
                    row["source_row"],
                ]
            )
    conn.close()
    print(f"CSV review export completato: {out_path}")


if __name__ == "__main__":
    export_csv(Path("data/congress_trades.csv"))
