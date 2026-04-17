# RS-threshold — IDX RS Score Threshold Calculator

Python pipeline that scores the full Indonesia Stock Exchange (IDX) equity universe against the IDX Composite (`^JKSE`), computes **seven percentile thresholds** for manual input into a TradingView **RS Rating** indicator, and writes **rankings**, **diagnostics**, and **threshold** CSVs under `outputs/`.

---

## What it does

1. Downloads ~500 calendar days of adjusted closes for `^JKSE` and every listed `.JK` ticker (parallel yfinance requests with rate limiting).
2. Applies data-quality filters (minimum price, stale-price ratio, outlier trimming).
3. Aligns each stock with the index and computes a **12-month composite RS score** (same weighting as the Pine Script indicator: 40% / 20% / 20% / 20% across quarterly lookbacks).
4. Derives **percentiles** and **elite** flags across the scored universe; ranks stocks for CSV export.
5. Prints the seven threshold values to the terminal (paste into TradingView) and saves timestamped CSVs.

For column-level definitions, formulas, and RS delta semantics, see **[IDX_RS_ANALYSIS_DESIGN.md](IDX_RS_ANALYSIS_DESIGN.md)**.

---

## Requirements

- Python 3.9+ (typical; not pinned in-repo)
- Packages:

```bash
pip install yfinance pandas numpy tqdm
```

---

## Usage

From the project root:

```bash
python main.py
```

**When to run:** After market close (after **16:00 WIB**) on a trading day, so the latest session is reflected in the data.

The script needs network access to Yahoo Finance via `yfinance`.

---

## Outputs

All paths are relative to `OUTPUT_ROOT_DIR` (default `outputs/`).

| Directory | Filename pattern | Contents |
|-----------|------------------|----------|
| `outputs/thresholds/` | `idx_rs_thresholds_<YYYY-MM-DD>_<HHMMSS>.csv` | Seven percentile thresholds + date + stock count |
| `outputs/diagnostics/` | `idx_rs_diagnostics_<YYYY-MM-DD>_<HHMMSS>.csv` | Coverage, reject/skip reason counts |
| `outputs/rankings/` | `idx_rs_rankings_<YYYY-MM-DD>_<HHMMSS>.csv` | Full ranked universe with RS, deltas, SMA distances, percentiles, elite flags |

The terminal also prints the **top N** stocks (`TOP_N_TERMINAL`, default 10) in a compact table (includes SMA10/SMA20 vs price; does not print `rs_delta_momentum` in the table).

---

## Configuration (`main.py`)

Tunable constants live at the top of `main.py`:

| Constant | Default | Role |
|----------|---------|------|
| `OUTPUT_ROOT_DIR` | `outputs` | Root for all CSV output |
| `HISTORY_DAYS` | `500` | Calendar lookback for price history |
| `REQUEST_DELAY` | `0.3` | Minimum seconds between API calls (per worker) |
| `MAX_WORKERS` | `10` | Thread pool size for stock/metadata fetches |
| `MIN_TRADING_DAYS` | `274` | Minimum bars after cleaning; aligns with RS delta (253 + 21) |
| `IDX_TICKER` | `^JKSE` | Benchmark index |
| `MIN_PRICE` | `5.0` | Skip stocks below this IDR close |
| `MAX_STALE_RATIO` | `0.20` | Skip if too many unchanged closes |
| `OUTLIER_FACTOR` | `5.0` | Trim bars far from rolling median |
| `RS_SCORE_MIN` | `30.0` | Exclude names below this composite RS (rankings only; still in threshold universe handling per code paths) |
| `TOP_N_TERMINAL` | `10` | Rows in the CLI summary table |
| `FILE_RETENTION_KEEP` | `30` | Keep this many newest files **per output subdirectory**; older matching files deleted at startup |
| `WARN_COVERAGE_PCT` | `45.0` | Warn if scored % of universe falls below this |
| `WARN_MIN_SCORED` | `400` | Warn if scored count falls below this |

**File retention:** On each run, after creating output directories, `prune_old_files()` deletes older `idx_rs_*.csv` files in each folder, keeping only the `FILE_RETENTION_KEEP` most recent by sorted filename (chronological given `YYYYMMDD_HHMMSS` stamps). Pruning runs **before** new files are written so the current run’s files are never deleted. Delete failures are ignored (`OSError` swallowed).

---

## Constraints

These are intentional boundaries of the implementation and data model.

### Operational

- **Single entry point:** `main.py` is the only Python module; there is no separate CLI package or config file.
- **Data source:** Yahoo Finance only (`yfinance`). No Bloomberg, no broker API.
- **Concurrency:** Stock prices use `ThreadPoolExecutor` with a shared rate limiter; `yf.download()` is not used for stocks (per-code comment: avoids cross-ticker contamination under parallelism).
- **Index dependency:** If `^JKSE` cannot be fetched, the run exits without writing thresholds/rankings.

### Universe and scoring

- **Fixed list:** `IDX_TICKERS` is a static in-code list (~956 names as of the embedded snapshot). New listings require editing the list.
- **RS core functions:** `calc_rs_score()`, `calc_single_tf_score()`, and `assign_percentile()` are the canonical definitions; downstream features must not redefine them in parallel.
- **Rankings floor:** Stocks with composite RS below `RS_SCORE_MIN` are excluded from the rankings CSV (`stock_data`), but their raw scores still append to `all_valid_rs_scores`, so they remain in the pool used for **threshold calibration** and for building the percentile comparison array (`arr_12m` is derived from the full scored set, including names below the floor).
- **Nullable fields:** `rs_delta`, `rs_delta_momentum`, SMA distance columns, and 52-week stats can be `null` when history or alignment is insufficient; the pipeline must not raise on missing values (same spirit as `rs_delta`).

### Minimum history (aligned bars on stock ∩ index)

| Metric | Approx. minimum bars |
|--------|----------------------|
| Composite RS (`calc_rs_score`) | 253 |
| `rs_delta` | 274 |
| `rs_delta_momentum` | 316 |
| SMA200 / `price_vs_sma200` | 200 stock bars (plus validation passing `MIN_TRADING_DAYS`) |

### Outputs and retention

- **Threshold run reliability:** If fewer than **30** stocks pass scoring for thresholds, the script prints an error and returns without treating results as reliable.
- **Retention:** Only the newest `FILE_RETENTION_KEEP` files per directory are kept; older outputs are **deleted**, not archived elsewhere.

### Legal / interpretive

- **Not investment advice.** Outputs are quantitative filters for research and tooling; you are responsible for compliance and decisions.
- **Vendor limitations:** Adjusted closes and sector/industry strings may differ from professional terminals; see **Known limitations** in the design doc.

---

## Project layout

```
RS-threshold/
├── main.py                    # Full pipeline
├── IDX_RS_ANALYSIS_DESIGN.md  # Schema, formulas, limitations
├── README.md                  # This file
└── outputs/
    ├── thresholds/
    ├── diagnostics/
    └── rankings/
```

---

## License

Not specified in-repo; add a `LICENSE` file if you redistribute.
