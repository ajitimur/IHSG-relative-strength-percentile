# IDX RS Analysis

Python pipeline that scores the full Indonesia Stock Exchange (IDX) equity universe against the IDX Composite (`^JKSE`), ranks stocks by Relative Strength, and publishes an interactive HTML dashboard to GitHub Pages — updated automatically every weekday after market close via GitHub Actions.

Methodology follows [Minervini](https://www.markminervini.com/) / [Qullamaggie](https://qullamaggie.com/) momentum principles: RS percentile ranking, multi-timeframe momentum screening, sector rotation analysis, and Stage 2 uptrend confirmation.

---

## Live Dashboard

**[→ Open Dashboard](https://github.com/ajitimur/IHSG-relative-strength-percentile)**

Updates automatically every weekday at **16:30 WIB**. Open it, it's already current.

---

## What It Does

```
main.py             →   outputs/rankings/idx_rs_rankings_YYYYMMDD_HHMMSS.csv
build_dashboard.py  →   docs/index.html  (GitHub Pages)
                    →   outputs/idx_rs_dashboard_YYYYMMDD.html  (local archive)
```

**`main.py`**

1. Downloads ~500 calendar days of adjusted closes for `^JKSE` and every listed `.JK` ticker (~956 names) via parallel `yfinance` requests with rate limiting.
2. Applies data-quality filters: minimum price, stale-price ratio, outlier trimming.
3. Aligns each stock with the index and computes a **12-month composite RS score** (40/20/20/20 quarterly weighting, matching the TradingView Pine Script indicator).
4. Computes single-timeframe RS scores for 1M/3M/6M/12M and derives **RS delta** (4-week momentum) and **RS delta momentum** (second derivative).
5. Calculates SMA distances (10/20/50/200-day), 52-week high/low proximity, and range position.
6. Assigns **percentile ranks** and **elite flags** (top 1% / top 2%) across all dimensions.
7. Writes timestamped rankings, thresholds, and diagnostics CSVs. Prints top-N summary to terminal.

**`build_dashboard.py`**

Takes the latest rankings CSV and produces a fully self-contained interactive HTML dashboard with embedded data — no server required. Computes sector composite scores, cross-TF persistence metrics, and momentum gainers screen entirely from the CSV.

---

## Dashboard Features

Six tabs, all sortable with multi-column sort support:

| Tab | Description |
|---|---|
| **RS Leaders** | Full liquid universe ranked by composite RS score. TOP% pills (1%/2%/5%/10%/20%) cut to top-N computed against the full universe. |
| **1M Leaders** | Ranked by 1-month RS percentile. |
| **3M Leaders** | Ranked by 3-month RS percentile. |
| **Cross-TF** | Stocks simultaneously in the top 10% across multiple timeframes. MIN TF COUNT pills (2/3/4). Accelerating Only filter (shape\_score > 0). |
| **Momentum** | Stocks passing the acceleration screen: pct\_1m > pct\_3m > pct\_12m, pct\_1m ≥ 60, acceleration ≥ 10 percentile points. |
| **Sectors** | Sector composite scores with multi-timeframe breadth bars and top-5 ticker chips. |

All leader tabs share the same filter set: RS Δ Rising, Near 52W High (>−15%), Above SMA10/20/50/200. Filters stack independently.

**Updating the dashboard without GitHub Actions:** click **⬆ LOAD CSV** in the top right to drop in a fresh CSV — the dashboard fully rebuilds client-side in the browser.

---

## Automation — GitHub Actions

The workflow file at `.github/workflows/daily_rs.yml` runs `main.py` then `build_dashboard.py` on a schedule, commits the outputs, and pushes to the repo. GitHub Pages serves `docs/index.html`.

**Schedule:** every weekday at 16:30 WIB (09:30 UTC).

**Manual trigger:** available from the GitHub Actions UI tab — useful for ad-hoc runs or after missed sessions.

**Rate limiting in CI:** GitHub Actions runs originate from shared IP ranges that Yahoo Finance sometimes throttles more aggressively than residential connections. The workflow passes `IDX_REQUEST_DELAY=0.5` and `MAX_WORKERS=8` as environment variables. To override without touching code, set them as **repository variables** under Settings → Variables → Actions.

To make `main.py` read these overrides, add near the top of the configuration block:

```python
import os
REQUEST_DELAY = float(os.environ.get("IDX_REQUEST_DELAY", REQUEST_DELAY))
MAX_WORKERS   = int(os.environ.get("IDX_MAX_WORKERS",   MAX_WORKERS))
```

### Setup

1. Create a GitHub repo and push all files.
2. Create a `docs/` folder (can be empty on first push).
3. Go to repo **Settings → Pages → Source: Deploy from branch → `main` → `/docs`**.
4. The workflow runs automatically. Dashboard URL: `https://<username>.github.io/<repo-name>/`

---

## Requirements

- Python 3.9+

```bash
pip install yfinance pandas numpy tqdm
```

Or from the requirements file:

```bash
pip install -r requirements.txt
```

---

## Usage

**Run the full pipeline locally:**

```bash
python main.py                    # fetch prices, score universe, write CSVs
python build_dashboard.py         # auto-detect latest CSV, write dashboard HTML
```

**Explicit paths:**

```bash
python build_dashboard.py outputs/rankings/idx_rs_rankings_20260417_120146.csv
python build_dashboard.py --output /tmp/dashboard.html
```

**After Claude rebuilds the dashboard** (redesign or new features), update the template files:

```bash
python extract_template.py outputs/idx_rs_dashboard_20260417.html
```

This writes `dashboard_template_a.html`, `dashboard_template_b.js`, and `dashboard_template_c.html`. Commit them. `build_dashboard.py` picks them up automatically on next run.

**When to run `main.py`:** after market close (**after 16:00 WIB**) on a trading day, so the latest session is reflected in the data.

---

## Outputs

All paths relative to `outputs/` (default `OUTPUT_ROOT_DIR`).

| Path | Filename pattern | Contents |
|---|---|---|
| `outputs/rankings/` | `idx_rs_rankings_YYYYMMDD_HHMMSS.csv` | Full ranked universe — RS scores, deltas, SMA distances, percentiles, elite flags |
| `outputs/thresholds/` | `idx_rs_thresholds_YYYYMMDD_HHMMSS.csv` | Seven percentile thresholds for TradingView RS Rating indicator inputs |
| `outputs/diagnostics/` | `idx_rs_diagnostics_YYYYMMDD_HHMMSS.csv` | Coverage stats, reject/skip reason counts |
| `outputs/` | `idx_rs_dashboard_YYYYMMDD.html` | Dated dashboard archive |
| `docs/` | `index.html` | Latest dashboard — served by GitHub Pages |

The terminal also prints the **top N** stocks (`TOP_N_TERMINAL`, default 10) in a compact table.

**File retention:** on each run, `prune_old_files()` deletes older matching files in each output subdirectory, keeping only the `FILE_RETENTION_KEEP` (default 30) most recent by filename sort. Pruning runs before new files are written so the current run is never deleted.

---

## CSV Schema — Rankings

Output: `outputs/rankings/idx_rs_rankings_YYYYMMDD_HHMMSS.csv`

| Column | Type | Description |
|---|---|---|
| `rank` | int | Rank by composite percentile (desc), then RS score (desc) |
| `ticker` | str | IDX ticker without `.JK` suffix |
| `sector` | str | GICS sector from yfinance |
| `industry` | str | GICS industry from yfinance |
| `avg_vol_30d` | int\|null | 30-day average daily volume |
| `price` | float | Last closing price (IDR), rounded to 0 decimals |
| `rs_score` | float | 12M composite RS score vs ^JKSE × 100 |
| `rs_delta` | float\|null | `rs_score[t] − rs_score[t−21]`; 4-week RS momentum; null if <274 aligned bars |
| `rs_delta_momentum` | float\|null | `rs_delta[t] − rs_delta[t−21]`; second derivative of RS; null if <316 aligned bars |
| `pct_from_52w_high` | float\|null | `(price − 52W high) / 52W high × 100`; always ≤ 0 |
| `pct_from_52w_low` | float\|null | `(price − 52W low) / 52W low × 100`; always ≥ 0 |
| `range_position` | float\|null | `(price − 52W low) / (52W high − 52W low) × 100`; 0 = at low, 100 = at high |
| `price_vs_sma10` | float\|null | `(price − SMA10) / SMA10 × 100`; Qullamaggie entry timing signal |
| `price_vs_sma20` | float\|null | `(price − SMA20) / SMA20 × 100`; secondary trend pulse |
| `price_vs_sma50` | float\|null | `(price − SMA50) / SMA50 × 100` |
| `price_vs_sma200` | float\|null | `(price − SMA200) / SMA200 × 100`; Stage 2 proxy |
| `percentile` | int\|null | Percentile rank (0–99) of `rs_score` within the full RS universe |
| `pct_1m` | int\|null | 1-month (21-day) single-timeframe RS percentile |
| `pct_3m` | int\|null | 3-month (63-day) single-timeframe RS percentile |
| `pct_6m` | int\|null | 6-month (126-day) single-timeframe RS percentile |
| `pct_12m` | int\|null | 12-month (252-day) single-timeframe RS percentile |
| `elite_rs` | str\|null | `top1` / `top2` / null — top 1%/2% on composite RS |
| `elite_1m` | str\|null | `top1` / `top2` / null — top 1%/2% on 1M percentile |
| `elite_3m` | str\|null | `top1` / `top2` / null — top 1%/2% on 3M percentile |
| `elite_6m` | str\|null | `top1` / `top2` / null — top 1%/2% on 6M percentile |
| `elite_12m` | str\|null | `top1` / `top2` / null — top 1%/2% on 12M percentile |
| `elite_count` | int | Count of elite flags across all 5 dimensions (0–5) |
| `date` | str | Run date `YYYY-MM-DD` |

---

## RS Score Formula

Mirrors the TradingView Pine Script implementation exactly:

```
RS_stock = 0.4 × perf(63d) + 0.2 × perf(126d) + 0.2 × perf(189d) + 0.2 × perf(252d)
RS_idx   = same formula on ^JKSE
RS_score = (RS_stock / RS_idx) × 100
```

Score of 100 = equal to IHSG. Above 100 = outperforming. Scores of 300–600 are normal for strong leaders in trending markets.

**Single-timeframe percentile columns** (`pct_1m` etc.) rank each stock's window-specific RS against all liquid peers on that day's cross-section — relative performance vs IHSG on that window only, ranked against all peers today.

**`rs_delta`** = RS momentum direction over the last 4 weeks. Positive = expanding. Large negative on a high-percentile stock = stalling, not a base — use caution.

**`rs_delta_momentum`** = second derivative. Positive = the rate of RS expansion is itself accelerating (early leadership run). Negative = expansion fading (late stage or distributing). Most informative when read together with `rs_delta` and `percentile`.

---

## Configuration (`main.py`)

| Constant | Default | Role |
|---|---|---|
| `OUTPUT_ROOT_DIR` | `outputs` | Root for all CSV output |
| `HISTORY_DAYS` | `500` | Calendar lookback for price history |
| `REQUEST_DELAY` | `0.3` | Minimum seconds between API calls per worker |
| `MAX_WORKERS` | `10` | Thread pool size for concurrent fetches |
| `MIN_TRADING_DAYS` | `274` | Minimum aligned bars; gates `rs_delta` (253 + 21) |
| `IDX_TICKER` | `^JKSE` | Benchmark index |
| `MIN_PRICE` | `5.0` | Skip stocks below this IDR close |
| `MAX_STALE_RATIO` | `0.20` | Skip if >20% of bars have unchanged price |
| `OUTLIER_FACTOR` | `5.0` | Remove bars deviating >5× from 20-day rolling median |
| `RS_SCORE_MIN` | `30.0` | Exclude from rankings if RS < this (still included in threshold calibration universe) |
| `FILE_RETENTION_KEEP` | `30` | Files retained per output subdirectory |
| `TOP_N_TERMINAL` | `10` | Rows printed in terminal summary table |
| `WARN_COVERAGE_PCT` | `45.0` | Warn if coverage of universe falls below this % |
| `WARN_MIN_SCORED` | `400` | Warn if scored count falls below this |

### Minimum history (aligned bars on stock ∩ index)

| Metric | Minimum bars |
|---|---|
| Composite RS (`calc_rs_score`) | 253 |
| `rs_delta` | 274 |
| `rs_delta_momentum` | 316 |
| `price_vs_sma200` | 200 (plus `MIN_TRADING_DAYS` validation) |

---

## Project Layout

```
idx-rs/
├── main.py                        RS pipeline — scores full universe, writes CSVs
├── build_dashboard.py             CSV → interactive HTML dashboard
├── extract_template.py            Update template after dashboard redesign
├── requirements.txt
├── IDX_RS_ANALYSIS_DESIGN.md      Full design doc — formulas, schema, limitations
├── README.md
│
├── dashboard_template_a.html      HTML + CSS + help modal (before data injection)
├── dashboard_template_b.js        JS engine (after data, before </script>)
├── dashboard_template_c.html      Closing tags
│
├── docs/
│   └── index.html                 Latest dashboard — served by GitHub Pages
│
├── outputs/
│   ├── rankings/                  idx_rs_rankings_YYYYMMDD_HHMMSS.csv
│   ├── thresholds/                idx_rs_thresholds_YYYYMMDD_HHMMSS.csv
│   ├── diagnostics/               idx_rs_diagnostics_YYYYMMDD_HHMMSS.csv
│   └── idx_rs_dashboard_*.html    Dated dashboard archive
│
└── .github/
    └── workflows/
        └── daily_rs.yml           Scheduled pipeline — weekdays 16:30 WIB
```

---

## Constraints

### Operational

- **Single entry point:** `main.py` is the only pipeline module; no separate CLI package or config file.
- **Data source:** Yahoo Finance only (`yfinance`). No Bloomberg, no broker API.
- **Concurrency:** Uses `yf.Ticker().history()` inside `ThreadPoolExecutor`. `yf.download()` is explicitly avoided — it shares internal session state across threads, causing price series contamination between tickers under concurrent execution.
- **Index dependency:** If `^JKSE` cannot be fetched, the run exits without writing any output.

### Universe and scoring

- **Fixed ticker list:** `IDX_TICKERS` is a static in-code list (~956 names, sourced from IDX official list, March 2026). New listings require editing `main.py`.
- **RS core functions:** `calc_rs_score()`, `calc_single_tf_score()`, and `assign_percentile()` are the canonical definitions. Do not redefine or replace them.
- **Rankings floor vs threshold universe:** Stocks with composite RS below `RS_SCORE_MIN` are excluded from `stock_data` (rankings CSV) but their raw scores remain in `all_valid_rs_scores`, so they stay in the pool used for threshold calibration and the `arr_12m` percentile array.
- **Nullable fields:** `rs_delta`, `rs_delta_momentum`, all SMA distance columns, and 52-week stats are null when history or alignment is insufficient. The pipeline never raises on missing values.

### Outputs

- **Threshold reliability floor:** fewer than 30 stocks scored → prints error and exits without saving.
- **Retention:** only the newest `FILE_RETENTION_KEEP` files per directory are kept. Older outputs are permanently deleted, not archived.

---

## Interpreting the Dashboard

**RS is a screening tool, not an entry trigger.** Use it to build a watchlist, then confirm price structure (Stage 2 uptrend, VCP base, volume contraction) on the chart before entry.

**Highest-conviction setup profile:**
- `percentile` ≥ 90
- `rs_delta` > 0 (RS actively expanding)
- `rs_delta_momentum` > 0 (expansion accelerating)
- `pct_from_52w_high` ≥ −10% (at or near highs)
- `price_vs_sma50` and `price_vs_sma200` both positive (Stage 2 confirmed)
- Stock in a top-3 sector by composite score

**Stalling leader flags:** high `percentile` + large negative `rs_delta` + deeply negative `rs_delta_momentum` = former leader in active distribution. Historical percentile is a lagging signal; the deltas reflect the present.

For detailed signal interpretation, tab-by-tab workflow, and setup profiles, open the dashboard and click **? HOW TO USE**.

---

## Legal

Not investment advice. Outputs are quantitative filters for research purposes. You are responsible for all trading decisions and regulatory compliance.

Adjusted closes and sector/industry metadata from `yfinance` may differ from professional data terminals, particularly for stocks with recent corporate actions. Cross-check any anomalies against broker charts before acting.

---

## License

Not specified. Add a `LICENSE` file if you redistribute.