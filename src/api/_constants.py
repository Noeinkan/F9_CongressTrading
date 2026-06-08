"""Data constants for the API layer (column lists, SQL queries, paths, sector map)."""
from __future__ import annotations

from ..config import DATA_DIR

NORMALIZED_EXPORT_PATH = DATA_DIR / "congress_trades.csv"
REVIEW_EXPORT_PATH = DATA_DIR / "review_queue.csv"
COMMITTEES_JSON_PATH = DATA_DIR / "committees.json"

MEMBERS_VIEW_COMMITTEE_RELEVANCE = "committee_relevance"

TRANSACTION_COLUMNS = [
    "member",
    "chamber",
    "party",
    "state",
    "filing_type",
    "filing_date",
    "transaction_date",
    "owner_type",
    "asset_name_raw",
    "asset_name_normalized",
    "asset_type",
    "issuer_name",
    "ticker",
    "sector",
    "industry",
    "transaction_type",
    "amount_low",
    "amount_high",
    "amount_range_raw",
    "confidence_score",
    "review_status",
    "source_url",
    "raw_document_path",
    "doc_id",
]

REVIEW_COLUMNS = [
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
    "ticker",
    "transaction_type_label",
    "transaction_type",
    "amount_range_raw",
    "confidence_score",
    "review_status",
    "raw_document_path",
    "source_page",
    "source_row",
]

# Committee jurisdiction → sector buckets (labels match issuer_enrichment.SECTOR_RULES).
COMMITTEE_SECTOR_MAP: dict[str, list[str]] = {
    "Agriculture": ["Consumer Staples", "Materials", "Energy"],
    "Appropriations": ["Industrials", "Healthcare", "Energy", "Financials"],
    "Armed Services": ["Industrials", "Technology"],
    "Budget": ["Financials", "Healthcare", "Energy"],
    "Education and Workforce": ["Consumer Discretionary", "Healthcare"],
    "Energy and Commerce": [
        "Energy",
        "Utilities",
        "Healthcare",
        "Communication Services",
        "Technology",
        "Consumer Staples",
    ],
    "Financial Services": ["Financials", "Real Estate"],
    "Foreign Affairs": ["Industrials", "Energy", "Technology"],
    "Homeland Security": ["Technology", "Industrials", "Communication Services"],
    "Judiciary": ["Communication Services", "Technology", "Consumer Discretionary"],
    "Natural Resources": ["Energy", "Materials", "Utilities"],
    "Oversight and Accountability": ["Technology", "Financials", "Healthcare", "Industrials"],
    "Science, Space, and Technology": ["Technology", "Industrials", "Communication Services"],
    "Small Business": ["Consumer Discretionary", "Consumer Staples", "Financials"],
    "Transportation and Infrastructure": ["Industrials", "Energy", "Materials", "Utilities"],
    "Veterans' Affairs": ["Healthcare"],
    "Ways and Means": ["Financials", "Healthcare", "Real Estate"],
    "Permanent Select Committee on Intelligence": ["Technology", "Communication Services", "Industrials"],
    "Intelligence": ["Technology", "Communication Services", "Industrials"],
    "Select Committee on China": ["Technology", "Industrials", "Materials", "Consumer Discretionary"],
}

SQLITE_TRANSACTION_QUERY = """
SELECT
    m.full_name AS member,
    f.chamber AS chamber,
    m.party AS party,
    m.state AS state,
    f.filing_type AS filing_type,
    f.filing_date AS filing_date,
    t.transaction_date AS transaction_date,
    t.owner_type AS owner_type,
    t.asset_name_raw AS asset_name_raw,
    t.asset_name_normalized AS asset_name_normalized,
    t.asset_type AS asset_type,
    COALESCE(i.issuer_name, '') AS issuer_name,
    t.ticker AS ticker,
    COALESCE(i.sector, '') AS sector,
    COALESCE(i.industry, '') AS industry,
    t.transaction_type AS transaction_type,
    t.amount_low AS amount_low,
    t.amount_high AS amount_high,
    t.amount_range_raw AS amount_range_raw,
    t.confidence_score AS confidence_score,
    t.review_status AS review_status,
    f.source_url AS source_url,
    f.raw_document_path AS raw_document_path,
    f.doc_id AS doc_id
FROM transactions t
JOIN filings f ON f.id = t.filing_id
JOIN members m ON m.id = f.member_id
LEFT JOIN issuers i ON i.id = t.issuer_id
ORDER BY t.transaction_date DESC, f.filing_date DESC, m.full_name ASC
"""

SQLITE_REVIEW_QUERY = """
SELECT
    rq.reason AS reason,
    rq.status AS status,
    rq.notes AS notes,
    m.full_name AS member,
    f.chamber AS chamber,
    f.filing_type AS filing_type,
    f.filing_date AS filing_date,
    t.transaction_date AS transaction_date,
    t.asset_name_raw AS asset_name_raw,
    t.asset_name_normalized AS asset_name_normalized,
    t.asset_type AS asset_type,
    t.ticker AS ticker,
    t.transaction_type AS transaction_type,
    t.amount_range_raw AS amount_range_raw,
    t.confidence_score AS confidence_score,
    t.review_status AS review_status,
    f.raw_document_path AS raw_document_path,
    t.source_page AS source_page,
    t.source_row AS source_row
FROM review_queue rq
JOIN transactions t ON t.id = rq.transaction_id
JOIN filings f ON f.id = t.filing_id
JOIN members m ON m.id = f.member_id
ORDER BY rq.updated_at DESC, f.filing_date DESC
"""
