# IDX RS Analysis — Design Document

## Overview

Calculates Relative Strength (RS) scores for the full IDX stock universe, produces
percentile-based threshold values for the TradingView RS Rating indicator, and
outputs a ranked CSV of all scored stocks.

## Pipeline

1. Fetch IDX Composite (`^JKSE`) price history
2. Pre-cache sector/industry metadata for all tickers
3. For each stock: fetch prices → validate → align with index → compute RS scores
4. Assign percentiles & elite flags across the scored universe
5. Output thresholds CSV, diagnostics CSV, and full rankings CSV

## CSV Schema — Rankings (`idx_rs_rankings_*.csv`)

| Column | Type | Description |
|---|---|---|
| `rank` | int | Rank by composite percentile (desc), then RS score (desc) |
| `ticker` | str | IDX ticker without `.JK` suffix |
| `sector` | str | GICS sector from yfinance |
| `industry` | str | GICS industry from yfinance |
| `avg_vol_30d` | int\|null | 30-day average daily volume |
| `price` | float | Last closing price (IDR), rounded to 0 decimals |
| `rs_score` | float | 12M composite RS score (weighted: 40/20/20/20 quarterly) |
| `rs_delta` | float\|null | `rs_score[t] − rs_score[t−21]`; 4-week RS momentum; null if fewer than 274 aligned bars |
| `rs_delta_momentum` | float\|null | `rs_delta[t] − rs_delta[t−21]`; second derivative of RS momentum; positive = RS acceleration itself accelerating; null if fewer than 316 aligned bars |
| `pct_from_52w_high` | float\|null | `(price − 52W high) / 52W high × 100` |
| `pct_from_52w_low` | float\|null | `(price − 52W low) / 52W low × 100` |
| `range_position` | float\|null | `(price − 52W low) / (52W high − 52W low) × 100`; 0 = at low, 100 = at high |
| `price_vs_sma10` | float\|null | `(price − SMA10) / SMA10 × 100`; Qullamaggie entry timing signal |
| `price_vs_sma20` | float\|null | `(price − SMA20) / SMA20 × 100`; secondary trend pulse |
| `price_vs_sma50` | float\|null | `(price − SMA50) / SMA50 × 100` |
| `price_vs_sma200` | float\|null | `(price − SMA200) / SMA200 × 100` |
| `percentile` | int\|null | Percentile rank (0–99) of `rs_score` within the full RS universe |
| `pct_1m` | int\|null | Percentile rank of 1-month (21-day) single-timeframe RS |
| `pct_3m` | int\|null | Percentile rank of 3-month (63-day) single-timeframe RS |
| `pct_6m` | int\|null | Percentile rank of 6-month (126-day) single-timeframe RS |
| `pct_12m` | int\|null | Percentile rank of 12-month (252-day) single-timeframe RS |
| `elite_rs` | str\|null | `top1` / `top2` / null — based on 99th/98th percentile of `percentile` |
| `elite_1m` | str\|null | `top1` / `top2` / null — based on 99th/98th percentile of `pct_1m` |
| `elite_3m` | str\|null | `top1` / `top2` / null — based on 99th/98th percentile of `pct_3m` |
| `elite_6m` | str\|null | `top1` / `top2` / null — based on 99th/98th percentile of `pct_6m` |
| `elite_12m` | str\|null | `top1` / `top2` / null — based on 99th/98th percentile of `pct_12m` |
| `elite_count` | int | Number of elite flags (0–5) across all dimensions |
| `date` | str | Run date (`YYYY-MM-DD`) |

## RS Score Formula

Mirrors the TradingView Pine Script indicator:

```
RS Score = weighted_perf_stock / weighted_perf_idx × 100
Weights: Q1 (most recent 63d) = 40%, Q2 (126d) = 20%, Q3 (189d) = 20%, Q4 (252d) = 20%
```

## RS Delta & RS Delta Momentum

- **`rs_delta`** = `RS_score(today) − RS_score(21 bars ago)` — first derivative; whether RS is improving or deteriorating over the last 4 weeks.
- **`rs_delta_momentum`** = `rs_delta(today) − rs_delta(21 bars ago)` — second derivative; whether RS momentum itself is accelerating or decelerating. Positive values mean RS improvement is speeding up.

## Data Quality Filters

| Filter | Threshold | Effect |
|---|---|---|
| Minimum price | `MIN_PRICE = 5.0` IDR | Skips penny stocks / data artifacts |
| Stale ratio | `MAX_STALE_RATIO = 0.20` | Skips if >20% bars unchanged (suspended/illiquid) |
| Outlier factor | `OUTLIER_FACTOR = 5.0` | Removes bars >5× from 20-day rolling median |
| RS floor | `RS_SCORE_MIN = 30.0` | Excludes stocks that lost 70%+ vs IHSG |
| Minimum bars | `MIN_TRADING_DAYS = 274` | Ensures sufficient history for RS delta |

## Known Limitations

### Infrastructure

#### File Retention

Rolling retention: `FILE_RETENTION_KEEP = 30` most recent files are kept per output
directory. Pruning runs at startup via `prune_old_files()`. Oldest files are deleted
first by filename sort (which is equivalent to chronological sort given the
`YYYYMMDD_HHMMSS` naming convention).

### Data

- yfinance adjusted close may differ from Bloomberg/Reuters for stocks with
  corporate actions (splits, rights issues)
- Sector/industry metadata depends on yfinance's upstream provider; some IDX
  stocks return empty values
- Coverage warnings fire when fewer than 45% of the universe is scored or fewer
  than 400 stocks pass quality filters
