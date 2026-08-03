"""Cross-check financial calculation invariants against the live SQLite DB.

Writes NDJSON findings to ``debug-ce707b.log`` (debug session) and prints a
compact summary to stdout. Not part of the CLI — run as:

    .venv\\Scripts\\python.exe scripts/audit_financial_calcs.py
    .venv\\Scripts\\python.exe scripts/audit_financial_calcs.py --run-id post-fix
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import pandas as pd

from src.api._home_analytics import (
    _dedupe_cumulative_trades,
    aggregate_net_trade_amount,
)
from src.api._patterns_analytics import (
    signed_trade_ceiling,
    signed_trade_floor,
    signed_trade_notional,
)
from src.api._tickers_analytics import (
    _signed_return,
    ticker_cumulative_exposure_payload,
    trade_return_metrics,
)
from src.api.repository import (
    is_buy_transaction_type,
    is_exchange_transaction_type,
    is_sell_transaction_type,
    load_transactions,
)
from src.polygon_prices import _signed_return_and_pnl

LOG_PATH = _REPO / "debug-ce707b.log"
SESSION_ID = "ce707b"
EPS = 0.51  # slightly above _RANGE_EPS / float noise
RUN_ID = "audit1"


def _log(hypothesis_id: str, location: str, message: str, data: dict) -> None:
    payload = {
        "sessionId": SESSION_ID,
        "runId": RUN_ID,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, default=str) + "\n")


def _row_sample(frame: pd.DataFrame, n: int = 5) -> list[dict]:
    if frame.empty:
        return []
    cols = [
        c
        for c in (
            "member",
            "ticker",
            "transaction_date",
            "transaction_type",
            "amount_low",
            "amount_high",
            "_signed",
            "_floor",
            "_ceil",
            "cumulative_net",
            "cumulative_low",
            "cumulative_high",
        )
        if c in frame.columns
    ]
    out = frame[cols].head(n).copy()
    if "transaction_date" in out.columns:
        out["transaction_date"] = out["transaction_date"].astype(str)
    return out.to_dict(orient="records")


def main() -> int:
    global RUN_ID
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="audit1", help="NDJSON runId tag")
    args = parser.parse_args()
    RUN_ID = str(args.run_id)

    t0 = time.perf_counter()
    frame, source = load_transactions()
    n = len(frame)
    _log(
        "META",
        "audit_financial_calcs.py:main",
        "loaded transactions",
        {"rows": n, "source": source, "columns": list(frame.columns)[:40]},
    )
    print(f"Loaded {n:,} transactions ({source})")
    if frame.empty:
        print("EMPTY — nothing to audit")
        return 1

    work = frame.copy()
    work["_signed"] = work.apply(signed_trade_notional, axis=1)
    work["_floor"] = work.apply(signed_trade_floor, axis=1)
    work["_ceil"] = work.apply(signed_trade_ceiling, axis=1)
    work["_is_buy"] = work["transaction_type"].map(is_buy_transaction_type)
    work["_is_sell"] = work["transaction_type"].map(is_sell_transaction_type)
    work["_is_exch"] = work["transaction_type"].map(is_exchange_transaction_type)

    # ---- H-A: CSV export PnL vs API for classified types --------------------
    type_counts = Counter(work["transaction_type"].astype(str))
    csv_api_mismatches: list[dict] = []
    for tt, count in type_counts.items():
        csv = _signed_return_and_pnl(tt, 100.0, 110.0, 8_000.0)
        api = _signed_return(tt, 100.0, 110.0, 8_000.0)
        if csv != api:
            csv_api_mismatches.append(
                {"transaction_type": tt, "count": count, "csv": csv, "api": api}
            )
    _log(
        "A",
        "audit_financial_calcs.py:H-A",
        "csv_vs_api_signed_return",
        {
            "type_counts": dict(type_counts.most_common(20)),
            "mismatch_count": len(csv_api_mismatches),
            "mismatches": csv_api_mismatches,
        },
    )
    print(f"[A] CSV vs API PnL type mismatches: {len(csv_api_mismatches)}")
    for m in csv_api_mismatches:
        print(f"    {m}")

    # ---- H-B: cumulative band invariant low <= net <= high ------------------
    band_violations = work.loc[
        (work["_floor"] - work["_signed"] > EPS) | (work["_signed"] - work["_ceil"] > EPS)
    ]
    _log(
        "B",
        "audit_financial_calcs.py:H-B",
        "per_trade_band_invariant",
        {
            "violation_count": int(len(band_violations)),
            "samples": _row_sample(band_violations),
        },
    )
    print(f"[B] Per-trade floor/net/ceil violations: {len(band_violations):,}")

    # Per ticker×member cumulative after the same pipeline as the API
    cum_violations = 0
    cum_samples: list[dict] = []
    tickers = (
        work.loc[work["ticker"].astype(str).str.strip() != "", "ticker"]
        .astype(str)
        .str.upper()
        .value_counts()
        .head(80)
        .index.tolist()
    )
    for t in tickers:
        payload = ticker_cumulative_exposure_payload(work, t, top_n=16)
        for row in payload.get("rows") or []:
            lo = float(row["cumulative_low"])
            net = float(row["cumulative_net"])
            hi = float(row["cumulative_high"])
            if lo - net > EPS or net - hi > EPS:
                cum_violations += 1
                if len(cum_samples) < 8:
                    cum_samples.append(
                        {
                            "ticker": t,
                            "member": row.get("member"),
                            "date": row.get("transaction_date"),
                            "low": lo,
                            "net": net,
                            "high": hi,
                            "label": row.get("cumulative_label"),
                        }
                    )
    _log(
        "B",
        "audit_financial_calcs.py:H-B-cum",
        "cumulative_band_invariant",
        {
            "tickers_checked": len(tickers),
            "violation_count": cum_violations,
            "samples": cum_samples,
        },
    )
    print(
        f"[B] Cumulative low/net/high violations "
        f"(top {len(tickers)} tickers): {cum_violations:,}"
    )

    # ---- H-C: net trade identity buy - sell == net; exchanges == 0 ---------
    exch_nonzero = work.loc[work["_is_exch"] & (work["_signed"].abs() > EPS)]
    unknown_nonzero = work.loc[
        ~work["_is_buy"]
        & ~work["_is_sell"]
        & ~work["_is_exch"]
        & (work["_signed"].abs() > EPS)
    ]
    buy_neg = work.loc[work["_is_buy"] & (work["_signed"] < -EPS)]
    sell_pos = work.loc[work["_is_sell"] & (work["_signed"] > EPS)]

    agg = aggregate_net_trade_amount(work, top_n=500)
    net_identity_bad: list[dict] = []
    if agg is not None and not agg.empty:
        for _, r in agg.iterrows():
            expected = float(r["buy_amount"]) - float(r["sell_amount"])
            got = float(r["net_amount"])
            if abs(expected - got) > EPS:
                net_identity_bad.append(
                    {
                        "ticker": r.get("ticker"),
                        "buy": float(r["buy_amount"]),
                        "sell": float(r["sell_amount"]),
                        "net": got,
                        "expected": expected,
                    }
                )
    _log(
        "C",
        "audit_financial_calcs.py:H-C",
        "net_trade_sign_and_identity",
        {
            "exchange_nonzero": int(len(exch_nonzero)),
            "unknown_nonzero": int(len(unknown_nonzero)),
            "buy_negative": int(len(buy_neg)),
            "sell_positive": int(len(sell_pos)),
            "net_identity_bad": len(net_identity_bad),
            "net_identity_samples": net_identity_bad[:8],
            "exchange_samples": _row_sample(exch_nonzero),
            "buy_neg_samples": _row_sample(buy_neg),
            "sell_pos_samples": _row_sample(sell_pos),
        },
    )
    print(
        f"[C] Sign/identity: exch_nz={len(exch_nonzero)} unknown_nz={len(unknown_nonzero)} "
        f"buy_neg={len(buy_neg)} sell_pos={len(sell_pos)} "
        f"net_identity_bad={len(net_identity_bad)}"
    )

    # ---- H-D: raw amount_low > amount_high (pre-swap source data) ----------
    lo = pd.to_numeric(work["amount_low"], errors="coerce")
    hi = pd.to_numeric(work["amount_high"], errors="coerce")
    swapped = work.loc[lo.notna() & hi.notna() & (lo > hi)]
    missing_both = work.loc[lo.isna() & hi.isna()]
    missing_one = work.loc[lo.isna() ^ hi.isna()]
    _log(
        "D",
        "audit_financial_calcs.py:H-D",
        "amount_bound_quality",
        {
            "swapped_low_gt_high": int(len(swapped)),
            "missing_both": int(len(missing_both)),
            "missing_one_side": int(len(missing_one)),
            "swapped_samples": _row_sample(swapped),
        },
    )
    print(
        f"[D] Bounds: swapped={len(swapped):,} missing_both={len(missing_both):,} "
        f"missing_one={len(missing_one):,}"
    )

    # ---- H-E: KPI sum vs signed sum; dedupe impact on cumulative ------------
    amount_low_sum = float(lo.fillna(0).sum())
    amount_high_sum = float(hi.fillna(0).sum())
    signed_sum = float(work["_signed"].sum())
    buy_signed = float(work.loc[work["_is_buy"], "_signed"].sum())
    sell_signed = float(work.loc[work["_is_sell"], "_signed"].sum())

    with_ticker = work.loc[work["ticker"].astype(str).str.strip() != ""].copy()
    before_dedupe = len(with_ticker)
    after_dedupe = len(_dedupe_cumulative_trades(with_ticker))
    dedupe_dropped = before_dedupe - after_dedupe

    # Home net-trade does NOT dedupe; cumulative DOES — quantify gap on top tickers
    dedupe_gap_samples: list[dict] = []
    for t in tickers[:25]:
        sub = with_ticker.loc[with_ticker["ticker"].astype(str).str.upper() == t]
        raw_net = float(sub.apply(signed_trade_notional, axis=1).sum())
        deduped = _dedupe_cumulative_trades(sub)
        dedupe_net = float(deduped.apply(signed_trade_notional, axis=1).sum())
        if abs(raw_net - dedupe_net) > EPS:
            dedupe_gap_samples.append(
                {
                    "ticker": t,
                    "rows_raw": int(len(sub)),
                    "rows_deduped": int(len(deduped)),
                    "net_raw": raw_net,
                    "net_deduped": dedupe_net,
                    "delta": raw_net - dedupe_net,
                }
            )
    dedupe_gap_samples.sort(key=lambda x: abs(x["delta"]), reverse=True)
    _log(
        "E",
        "audit_financial_calcs.py:H-E",
        "kpi_sums_and_dedupe_gap",
        {
            "amount_low_sum": amount_low_sum,
            "amount_high_sum": amount_high_sum,
            "signed_sum": signed_sum,
            "buy_signed_sum": buy_signed,
            "sell_signed_sum": sell_signed,
            "dedupe_dropped_rows": int(dedupe_dropped),
            "dedupe_gap_ticker_count": len(dedupe_gap_samples),
            "dedupe_gap_top": dedupe_gap_samples[:10],
        },
    )
    print(
        f"[E] KPI sums: low={amount_low_sum:,.0f} high={amount_high_sum:,.0f} "
        f"signed={signed_sum:,.0f} | dedupe dropped={dedupe_dropped:,} "
        f"tickers_with_gap={len(dedupe_gap_samples)}"
    )
    for g in dedupe_gap_samples[:5]:
        print(
            f"    dedupe gap {g['ticker']}: raw={g['net_raw']:,.0f} "
            f"deduped={g['net_deduped']:,.0f} delta={g['delta']:,.0f} "
            f"({g['rows_raw']}->{g['rows_deduped']} rows)"
        )

    # ---- H-F: return_pct vs est_pnl sign for sells with cache prices --------
    # Sample equity tickers that have enough trades; check sell sign convention
    sell_sign_issues: list[dict] = []
    returns_checked = 0
    for t in tickers[:30]:
        sub = work.loc[work["ticker"].astype(str).str.upper() == t].head(40)
        if sub.empty:
            continue
        metrics = trade_return_metrics(sub)
        for row, m in zip(sub.to_dict("records"), metrics, strict=True):
            if m.get("return_pct") is None or m.get("est_pnl_usd") is None:
                continue
            if m.get("is_non_equity"):
                continue
            returns_checked += 1
            tt = str(row.get("transaction_type") or "")
            ret = float(m["return_pct"])
            pnl = float(m["est_pnl_usd"])
            # For sells, pnl should oppose the market return direction:
            # price up ⇒ mkt_ret>0 ⇒ sell pnl < 0
            if is_sell_transaction_type(tt):
                if ret > 0.5 and pnl > EPS:
                    sell_sign_issues.append(
                        {
                            "ticker": t,
                            "type": tt,
                            "return_pct": ret,
                            "est_pnl_usd": pnl,
                            "note": "sell with +return and +pnl (unexpected)",
                        }
                    )
                if ret < -0.5 and pnl < -EPS:
                    sell_sign_issues.append(
                        {
                            "ticker": t,
                            "type": tt,
                            "return_pct": ret,
                            "est_pnl_usd": pnl,
                            "note": "sell with -return and -pnl (unexpected)",
                        }
                    )
            elif is_buy_transaction_type(tt):
                # buy: pnl and return should share sign
                if ret > 0.5 and pnl < -EPS:
                    sell_sign_issues.append(
                        {
                            "ticker": t,
                            "type": tt,
                            "return_pct": ret,
                            "est_pnl_usd": pnl,
                            "note": "buy with +return and -pnl",
                        }
                    )
                if ret < -0.5 and pnl > EPS:
                    sell_sign_issues.append(
                        {
                            "ticker": t,
                            "type": tt,
                            "return_pct": ret,
                            "est_pnl_usd": pnl,
                            "note": "buy with -return and +pnl",
                        }
                    )
    _log(
        "F",
        "audit_financial_calcs.py:H-F",
        "return_vs_pnl_sign_convention",
        {
            "returns_checked": returns_checked,
            "issue_count": len(sell_sign_issues),
            "samples": sell_sign_issues[:12],
        },
    )
    print(
        f"[F] Return/PnL sign checks: {returns_checked:,} priced trades, "
        f"issues={len(sell_sign_issues)}"
    )

    elapsed = time.perf_counter() - t0
    summary = {
        "elapsed_s": round(elapsed, 2),
        "rows": n,
        "A_csv_api_mismatches": len(csv_api_mismatches),
        "B_per_trade_band_violations": int(len(band_violations)),
        "B_cumulative_band_violations": cum_violations,
        "C_net_identity_bad": len(net_identity_bad),
        "C_sign_anomalies": int(
            len(exch_nonzero) + len(unknown_nonzero) + len(buy_neg) + len(sell_pos)
        ),
        "D_swapped_bounds": int(len(swapped)),
        "E_dedupe_gap_tickers": len(dedupe_gap_samples),
        "F_return_pnl_issues": len(sell_sign_issues),
    }
    _log("META", "audit_financial_calcs.py:summary", "audit_complete", summary)
    print(f"\nDone in {elapsed:.1f}s - log: {LOG_PATH.name}")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
