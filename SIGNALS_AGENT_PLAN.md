# AI Signals Report — Plan

Goal: every night, after the ingest, send one Telegram report listing the
handful of tickers worth a look, each with a **long / short / watch** label, a
confidence level, the evidence behind it, and what to check next.

Status: planned, nothing built yet. Written 2026-10-22.

---

## The one design rule

**Python finds and scores the signals. The AI model only writes them up.**

- Small models (and free cloud tiers) are unreliable when they have to dig
  through raw data and reason over many steps. They are good at turning a short,
  pre-computed list of facts into readable prose.
- The scorer is plain Python: the same data always gives the same ranking, it
  can be tested, and it can be backtested. An LLM's picks can be neither.
- The model can never add a ticker or flip a direction. Its output is checked
  against the scorer's list, and a plain template is sent instead if it fails.

```
nightly ingest ──► signals scorer ──► brief (JSON, top N) ──► LLM writer ──► validator ──► Telegram
                   (src/signals/)                             (src/agent/)    │
                                                                              └─ on failure: template report
```

## Where it runs

The nightly job runs on the **VPS** (`scripts/nightly_ingest.sh`), not on your
PC. So the model choice is about the server, not your laptop:

| Provider | Where | Notes |
|---|---|---|
| **Gemini Flash (default)** | Google's cloud | Free tier is Flash-only; one call a night is far below any quota. Free-tier prompts may be used for training, which is acceptable here because the input is public disclosure data. Check current quotas in Google AI Studio → *Get API key* → *Rate limits*. |
| **Ollama (fallback / offline)** | VPS or your PC | Free local runner. A 4B model (Gemma 3 4B, Qwen 3 4B) runs on CPU in ~4–6 GB RAM; slow, but a nightly batch has time. Needs the VPS to have the RAM spare. |
| **None** (`--no-llm`) | — | Template-only report. Always works; it is also the failure fallback. |

Both Gemini and Ollama expose an **OpenAI-compatible chat endpoint** (Gemini at
`https://generativelanguage.googleapis.com/v1beta/openai/`, Ollama at
`http://localhost:11434/v1`). One small client using `httpx` (already a
dependency) covers both, so no provider SDK is added and switching is one env
var.

## What the research says (sets expectations)

- Copying congressional **buys** has a weak record. Early studies (Ziobrowski)
  found members beating the market; later ones (Eggers & Hainmueller; Belmont
  2022; a 2024 study of 5,225 House purchases) found no edge, or negative
  returns after disclosure.
- **Sales and short-type trades** look stronger: Molk & Partnoy (2025) found
  members' negative trades were followed by abnormal returns, longs were not.
- Edge survives in pockets: powerful members / leadership, committee-relevant
  trades, and it fades within about 3 months.
- Vendor backtests (Quiver and similar) are self-reported.

Consequences for the design:

1. Everything is keyed to the **filing date**: that is when the public learns of
   a trade. A backtest from the trade date shows profits nobody could have
   captured.
2. Long/short labels are **gated by our own backtest** (Phase 2). Until a score
   bucket shows a real edge, the report labels it "watch", not "long".
3. A single partial sale is not a short signal (diversification, taxes,
   divestment rules). Sales count only when they are broad, full, or backed by
   puts or committee relevance.
4. The report says "worth a look" with a confidence level, never "buy/sell".
   Every message carries one line: *not investment advice*.

---

## Phase 1 — Signal scorer (`src/signals/`)

New domain folder, pure functions over a prepared frame, the same style as
`src/notify/events.py`.

**Reuse, don't rebuild.** Most inputs already exist:

| Input | Already in |
|---|---|
| Cleaned transactions frame | `src/api/repository.py` → `_prepare_transactions` |
| Buy/sell, option side (Call/Put), debt filter | `src/api/_patterns_analytics.py` → `add_trade_categories`, `looks_like_debt_security` |
| Multi-member clusters | `_patterns_analytics.detect_coordinated_trades` |
| Committee jurisdiction overlap | `_patterns_analytics.score_committee_relevance` (`data/committees.json`) |
| Listed-security filter, late-filing days | `src/notify/events.py` → `is_listed_security`, `days_past_deadline` |
| First buy on record | `src/notify/query.py` → `prior_trade_count` |
| Prices since trade/disclosure | `src/api/_tickers_analytics.py` → `trade_return_metrics` (Polygon/Yahoo cache) |

**Files:**

- `src/signals/features.py`: one row per ticker over a lookback window
  (default: filed in the last 30 days). Columns:
  - `buyers`, `sellers`: distinct members on each side;
  - `net_floor_usd`: disclosed floors, buys minus sells;
  - `call_buys`, `put_buys`, `call_sells`;
  - `full_sales`: count of "Sale (Full)" rows;
  - `committee_hits`: trades where the member's committee covers the sector;
  - `late_rows`: rows filed past the 45-day deadline;
  - `first_buys`: members buying a name for the first time on record;
  - `move_since_filing_pct`: how far the price has already run since
    disclosure, so the report can say "already priced in".
- `src/signals/score.py`: weighted sum → `score` (signed: + long, − short),
  `direction` (`long` / `short` / `watch`), `confidence` (`low` / `medium` /
  `high`), and `reasons` (short strings, one per feature that fired). Weights
  live in one `WEIGHTS` dict so Phase 2 can calibrate them.
- `src/signals/brief.py`: the top N (default 8) as a compact JSON brief: ticker,
  sector, direction, confidence, score, reasons, the members involved
  (name, party, chamber, committee), amounts, filing dates, price move, and the
  dashboard deep link from `src/notify/links.py`.

Done when: `python -m src.main signals-brief` prints the JSON for tonight's
data, and `tests/test_signals_score.py` covers each feature on a hand-made frame
(no DB, no network).

## Phase 2 — Backtest gate (`src/signals/backtest.py`)

This phase decides whether "long" and "short" are allowed in the report at all.

1. Re-run the scorer as of each past week (walk forward, no future data).
2. Entry = first close **after the filing date**; exits at +20, +60, +90
   trading days. Benchmark = SPY over the same days (add SPY to the price-cache
   warm-up).
3. Output per score bucket and direction: number of signals, average excess
   return, hit rate, worst case. Write `data/signals_backtest.csv` and print a
   summary table.
4. A bucket is **enabled** only if it beats SPY on average with a hit rate
   above 55% over at least 30 signals. The enabled buckets are saved to
   `data/signals_calibration.json`; the scorer reads it, and anything not
   enabled is labelled "watch".

CLI: `python -m src.main signals-backtest [--since 2023-01-01]`.
This also delivers `PATTERNS_ROADMAP.md` item 2 ("Copycat Returns") on the
data side.

Done when: the backtest runs over the whole history, the calibration file is
written, and a test with synthetic prices checks there is no look-ahead (entry
never earlier than the filing date).

## Phase 3 — AI writer and delivery (`src/agent/`)

- `src/agent/settings.py`: env contract, same style as `src/notify/settings.py`:
  - `SIGNALS_LLM_PROVIDER` = `gemini` | `ollama` | `none` (default `gemini`);
  - `SIGNALS_LLM_MODEL` (e.g. `gemini-2.5-flash`, `qwen3:4b`);
  - `SIGNALS_LLM_BASE_URL` (optional override);
  - `GEMINI_API_KEY`, read with `os.getenv()` only. Add it empty to
    `.env.example`; the real value goes in `.env` on the VPS. Never a literal
    (see "Secrets" in `CLAUDE.md`).
  - `SIGNALS_TOP_N`, `SIGNALS_LOOKBACK_DAYS`, `SIGNALS_ENABLED`.
- `src/agent/llm.py`: one function, `complete(messages) -> str`, using `httpx`
  against the OpenAI-compatible endpoint. Timeout, two retries, no streaming.
- `src/agent/prompt.py`: a fixed system prompt plus the JSON brief. It asks for
  JSON back: per ticker a `headline`, a 2-line `rationale`, `watch_for`
  (what would confirm or kill the idea), and a 3-line overall summary. It tells
  the model to use only facts in the brief.
- `src/agent/validate.py`: rejects the output if it names a ticker not in the
  brief, changes a direction or confidence, or is not valid JSON. One retry,
  then the template.
- `src/agent/report.py`: renders Telegram HTML, reusing
  `src/notify/telegram.py` (`send_message`, splitting, escaping) and
  `src/notify/links.py`. Layout: summary, then one block per ticker
  (🟢 long / 🔴 short / 🟡 watch, confidence, rationale, members, link), then
  the disclaimer line.
- State: one report per day, stored with `src/notify/state.py`
  `get_state`/`set_state` (key `signals_last_report_date`). The report is
  silent when nothing scores above the floor, the same "silence is the signal"
  rule as the alerts.

CLI: `python -m src.main signals-report [--dry-run] [--no-llm]`.

Wiring:

1. `scripts/nightly_ingest.sh`: run `signals-report` after `notify-digest`,
   and collect its failure into `notify_rc` the same way, so an LLM outage never
   makes the night look like a data failure.
2. `src/post_ingest.py`: add the same step to the sidebar Refresh job so the
   two stay in step (as `CLAUDE.md` requires), with the per-day state as the
   cooldown.

Tests (`tests/test_agent_report.py`): fake LLM client returning good, bad
(invented ticker, flipped direction) and broken JSON; check the validator, the
template fallback, and that `--dry-run` writes no state. No network.

Done when: `signals-report --dry-run` prints a full report on the VPS with
Gemini, with Ollama, and with `--no-llm`.

## Phase 4 — Optional extensions

Only after Phases 1–3 have run for a few weeks.

- **Signals page on the dashboard:** a `routers/signals.py` endpoint over
  `src/signals/brief.py`, and a page following the frontend recipe
  (`PageState` + `SectionIntro` + `ChartCard`, `TickerLink`/`MemberLink`). It
  shows tonight's ranking and the backtest table.
- **"Ask the dashboard" chat:** expose selected read-only API routes as tools
  through the `fastapi-mcp` library, so an AI chat client can answer questions
  like "who bought NVDA this month?". It needs a stronger model (Gemini Flash
  or better: small local models chain tool calls poorly) and a decision on auth,
  because the API sits behind the session cookie.
- **More inputs:** behavioural anomaly score and sector rotation
  (`PATTERNS_ROADMAP.md` items 3–4), SEC Form 4 insider buys on the same
  tickers (item 8).

---

## Order of work and size

| # | Step | Size | Depends on |
|---|---|---|---|
| 1 | `src/signals/features.py` + tests | M | — |
| 2 | `src/signals/score.py` + `brief.py` + `signals-brief` CLI | M | 1 |
| 3 | SPY in price-cache warm-up | S | — |
| 4 | `src/signals/backtest.py` + `signals-backtest` CLI + calibration file | L | 2, 3 |
| 5 | `src/agent/` settings, client, prompt, validator | M | 2 |
| 6 | `src/agent/report.py` + `signals-report` CLI + tests | M | 5 |
| 7 | Wire into `nightly_ingest.sh` and `post_ingest.py`, `.env.example` | S | 6 |
| 8 | Docs: `AGENTS.md` module tables + CLI table, `CLAUDE.md` section, `PROJECT_INDEX.md` | S | 7 |
| 9 | Phase 4 items, one at a time | — | weeks of live runs |

Steps 4 and 5 can be done in parallel. Until step 4 is done, the report ships
with every pick labelled "watch".

## Setup you will do (once, after the deploy)

1. **Deploy first:** nothing below works until the new code is on the VPS
   (`.\deploy_local.ps1` from your PC, as usual).
2. **Get a Gemini key:** go to <https://aistudio.google.com> → sign in → *Get
   API key* → *Create API key* → copy it.
3. **Add it on the VPS:** SSH in, open the repo's `.env`, add
   `GEMINI_API_KEY=<the key>` and `SIGNALS_LLM_PROVIDER=gemini`, save.
4. **Test without sending:** `.venv/bin/python -m src.main signals-report --dry-run`.
   You should see the report printed. If it says the key is missing, the `.env`
   line has a typo or a stray space.
5. **Send one for real:** run it again without `--dry-run`; the message
   arrives in the same Telegram chat as the alerts.

From then on it runs every night with no further action.

## Risks

- **No edge found.** If the backtest enables no bucket, the report stays a
  "watch list". That is still useful, and better than false long/short calls.
- **Free-tier changes.** Google has cut free quotas before. The `ollama` and
  `none` providers keep the report running without a code change.
- **Thin data.** Senate history starts in 2023, so some buckets may not reach 30
  signals. The backtest reports the count, so a thin bucket is visible, not
  hidden.
- **Disclosure lag.** Trades surface up to 45 days late. `move_since_filing_pct`
  exists so the report can flag names that have already moved.

## Open decisions

- Gemini or Ollama as the first provider (plan assumes Gemini).
- If Ollama: does the VPS have ~6 GB RAM spare, or should it run on your PC
  (then the report runs only when the PC is on)?
- Top N per report (plan assumes 8) and the lookback window (30 days).
