"""
build_dashboard.py
==================
Converts an idx_rs_rankings_*.csv into a fully self-contained
interactive HTML dashboard.

Usage:
    python build_dashboard.py                            # auto-detects latest CSV in outputs/rankings/
    python build_dashboard.py path/to/rankings.csv      # explicit CSV path
    python build_dashboard.py --output path/to/out.html # explicit output path

Called by GitHub Actions after main.py runs.
Also usable locally as a standalone rebuild step.
"""

import sys
import os
import json
import argparse
import glob
import datetime
import numpy as np
import pandas as pd


# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

OUTPUT_ROOT  = "outputs"
RANKINGS_DIR = os.path.join(OUTPUT_ROOT, "rankings")
DOCS_DIR     = "docs"          # GitHub Pages output directory
MIN_VOL      = 1_000_000
MIN_SECTOR_SIZE = 3


# ─────────────────────────────────────────────
# DATA PIPELINE
# ─────────────────────────────────────────────

def find_latest_csv():
    """Find the most recently modified rankings CSV."""
    pattern = os.path.join(RANKINGS_DIR, "idx_rs_rankings_*.csv")
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(
            f"No rankings CSV found in {RANKINGS_DIR}/. "
            "Run main.py first or pass an explicit CSV path."
        )
    return files[-1]


def load_and_filter(csv_path):
    """Load CSV and apply liquidity filter."""
    df = pd.read_csv(csv_path)
    liq = df[df["avg_vol_30d"] >= MIN_VOL].copy()
    print(f"   Loaded : {len(df)} rows total, {len(liq)} liquid (vol >= {MIN_VOL:,})")
    return df, liq


def compute_cross_tf(liq):
    """Add tf_count_10, avg_pct, shape_score columns in-place."""
    tf_cols = ["pct_1m", "pct_3m", "pct_6m", "pct_12m"]

    liq["tf_count_10"] = liq[tf_cols].apply(
        lambda r: sum(1 for c in tf_cols if pd.notna(r[c]) and r[c] >= 90), axis=1
    )
    liq["avg_pct"] = liq[tf_cols].mean(axis=1).round(1)
    liq["shape_score"] = (
        (liq["pct_1m"] - liq["pct_12m"]) * 0.5
        + (liq["pct_1m"] - liq["pct_3m"]) * 0.3
        + (liq["pct_3m"] - liq["pct_6m"]) * 0.2
    ).round(1)


def compute_momentum_gainers(liq):
    """Return momentum gainers sorted by accel descending."""
    mask = (
        (liq["pct_1m"] > liq["pct_3m"])
        & (liq["pct_3m"] > liq["pct_12m"])
        & (liq["pct_1m"] >= 60)
        & (liq["pct_1m"] - liq["pct_3m"] >= 10)
    )
    mg = liq[mask].copy()
    mg["accel"] = mg["pct_1m"] - mg["pct_3m"]
    return mg.sort_values("accel", ascending=False)


def compute_sector_composite(liq):
    """Return sector composite DataFrame sorted by composite desc."""

    def _sector_stats(grp):
        def breadth(col):
            return round((grp[col] >= 70).mean() * 100, 1)

        b1 = breadth("pct_1m")
        b3 = breadth("pct_3m")
        b6 = breadth("pct_6m")
        mb = b1 * 0.5 + b3 * 0.3 + b6 * 0.2

        top5     = grp.nlargest(5, "pct_1m")
        ceiling  = round(float(top5["pct_1m"].median()), 1)
        avg      = round(float(grp["pct_1m"].mean()), 1)
        composite = round(mb * 0.4 + ceiling * 0.4 + avg * 0.2, 1)

        return pd.Series({
            "composite":    composite,
            "multi_breadth": round(mb, 1),
            "breadth_1m":   b1,
            "breadth_3m":   b3,
            "breadth_6m":   b6,
            "ceiling":      ceiling,
            "avg":          avg,
            "count":        len(grp),
            "top5":         top5["ticker"].tolist(),
        })

    valid = liq.groupby("sector").filter(lambda x: len(x) >= MIN_SECTOR_SIZE)
    sc    = (
        valid.groupby("sector")
        .apply(_sector_stats)
        .sort_values("composite", ascending=False)
        .reset_index()
    )
    return sc


def detect_columns(df):
    """Return meta flags based on which columns are present."""
    cols = set(df.columns)
    return {
        "has_rs_delta":          "rs_delta"          in cols,
        "has_rs_delta_momentum": "rs_delta_momentum" in cols,
        "has_pct_52w":           "pct_from_52w_high" in cols,
        "has_sma10":             "price_vs_sma10"    in cols,
        "has_sma20":             "price_vs_sma20"    in cols,
    }


def clean_value(v):
    """Convert numpy scalars and NaN/Inf to JSON-safe Python types."""
    if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
        return None
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        return float(v)
    if isinstance(v, list):
        return [clean_value(x) for x in v]
    return v


def clean_row(row_dict):
    return {k: clean_value(v) for k, v in row_dict.items()}


def build_payload(csv_path):
    """Full pipeline: CSV -> JSON payload dict."""
    df, liq = load_and_filter(csv_path)

    compute_cross_tf(liq)
    momentum = compute_momentum_gainers(liq)
    sectors  = compute_sector_composite(liq)
    cross    = liq[liq["tf_count_10"] >= 2].sort_values(
        ["tf_count_10", "avg_pct"], ascending=[False, False]
    )

    col_flags = detect_columns(df)
    run_date  = str(liq["date"].iloc[0]) if "date" in liq.columns else datetime.date.today().isoformat()

    # Sector records — convert top5 list correctly
    sector_records = []
    for _, row in sectors.iterrows():
        d = {}
        for k, v in row.items():
            d[k] = clean_value(v)
        sector_records.append(d)

    payload = {
        "stocks":   [clean_row(r) for r in liq.to_dict("records")],
        "momentum": [clean_row(r) for r in momentum.to_dict("records")],
        "cross":    [clean_row(r) for r in cross.to_dict("records")],
        "sectors":  sector_records,
        "meta": {
            "date":        run_date,
            "liquid_count": int(len(liq)),
            "total_count":  int(len(df)),
            **col_flags,
        },
    }

    print(f"   Stocks  : {len(payload['stocks'])}")
    print(f"   Momentum: {len(payload['momentum'])}")
    print(f"   Cross-TF: {len(payload['cross'])}")
    print(f"   Sectors : {len(payload['sectors'])}")
    return payload, run_date


# ─────────────────────────────────────────────
# HTML TEMPLATE
# ─────────────────────────────────────────────

# The template is split at the data injection point.
# TMPL_A  = everything before `const EMBEDDED =`
# TMPL_B  = JS engine (after data, before </script>)
# TMPL_C  = </script></body></html>
#
# The strings below were extracted directly from the dashboard
# produced by Claude and are reproduced here verbatim.
# To update the template, re-run Claude's dashboard build and
# replace these strings.

def get_template():
    """Return (tmpl_a, tmpl_b, tmpl_c) tuple."""
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Check for external template files first (easier to update)
    a_path = os.path.join(script_dir, "dashboard_template_a.html")
    b_path = os.path.join(script_dir, "dashboard_template_b.js")
    c_path = os.path.join(script_dir, "dashboard_template_c.html")

    if os.path.exists(a_path) and os.path.exists(b_path) and os.path.exists(c_path):
        with open(a_path) as f: tmpl_a = f.read()
        with open(b_path) as f: tmpl_b = f.read()
        with open(c_path) as f: tmpl_c = f.read()
        print("   Template: loaded from external files")
        return tmpl_a, tmpl_b, tmpl_c

    # Fall back to inline template extracted from the latest dashboard build.
    # Update by running: python extract_template.py
    inline_path = os.path.join(script_dir, "dashboard_inline_template.py")
    if os.path.exists(inline_path):
        ns = {}
        with open(inline_path) as f:
            exec(f.read(), ns)
        print("   Template: loaded from inline template module")
        return ns["TMPL_A"], ns["TMPL_B"], ns["TMPL_C"]

    raise FileNotFoundError(
        "No dashboard template found. Run extract_template.py first to generate "
        "dashboard_template_a.html, dashboard_template_b.js, dashboard_template_c.html"
    )


# ─────────────────────────────────────────────
# TEMPLATE EXTRACTOR (run once after Claude rebuilds dashboard)
# ─────────────────────────────────────────────

def extract_template(source_html_path):
    """
    Extract template parts from a fully built dashboard HTML.
    Call this after Claude produces a new dashboard to update the template.

    Writes:
        dashboard_template_a.html  — HTML/CSS/modal (before data)
        dashboard_template_b.js    — JS engine (after data, before </script>)
        dashboard_template_c.html  — closing tags
    """
    with open(source_html_path) as f:
        html = f.read()

    marker      = "const EMBEDDED ="
    start       = html.find(marker)
    end         = html.find(";\n", start) + 2
    script_end  = html.rfind("</script>")

    if start == -1 or end < 2 or script_end == -1:
        raise ValueError(f"Could not find template markers in {source_html_path}")

    tmpl_a = html[:start]
    tmpl_b = html[end:script_end]
    tmpl_c = html[script_end:]

    script_dir = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(script_dir, "dashboard_template_a.html"), "w") as f: f.write(tmpl_a)
    with open(os.path.join(script_dir, "dashboard_template_b.js"),   "w") as f: f.write(tmpl_b)
    with open(os.path.join(script_dir, "dashboard_template_c.html"), "w") as f: f.write(tmpl_c)

    print(f"Template extracted from {source_html_path}:")
    print(f"  A (HTML/CSS): {len(tmpl_a):,} bytes")
    print(f"  B (JS engine): {len(tmpl_b):,} bytes")
    print(f"  C (closing): {len(tmpl_c):,} bytes")


# ─────────────────────────────────────────────
# DASHBOARD BUILDER
# ─────────────────────────────────────────────

def build_html(payload, run_date, output_path):
    """Assemble and write the final HTML dashboard."""
    tmpl_a, tmpl_b, tmpl_c = get_template()

    data_json = json.dumps(payload, separators=(",", ":"))

    html = (
        tmpl_a
        + "const EMBEDDED ="
        + data_json
        + ";\n"
        + tmpl_b
        + "</script>\n</body>\n</html>\n"
    )

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    size_kb = len(html) / 1024
    print(f"   Output  : {output_path} ({size_kb:.0f} KB)")
    return output_path


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Build IDX RS HTML dashboard from rankings CSV")
    parser.add_argument("csv", nargs="?", default=None,
                        help="Path to idx_rs_rankings_*.csv (default: latest in outputs/rankings/)")
    parser.add_argument("--output", "-o", default=None,
                        help="Output HTML path (default: docs/index.html and outputs/idx_rs_dashboard_DATE.html)")
    parser.add_argument("--extract-template", metavar="HTML_PATH",
                        help="Extract template parts from a built dashboard HTML and exit")
    args = parser.parse_args()

    # Template extraction mode
    if args.extract_template:
        extract_template(args.extract_template)
        return

    # Resolve CSV path
    csv_path = args.csv or find_latest_csv()
    print(f"\n📊 IDX RS Dashboard Builder")
    print(f"   CSV     : {csv_path}")

    # Build data payload
    payload, run_date = build_payload(csv_path)

    # Resolve output paths
    date_slug    = run_date.replace("-", "")
    dated_output = os.path.join(OUTPUT_ROOT, f"idx_rs_dashboard_{date_slug}.html")
    pages_output = os.path.join(DOCS_DIR, "index.html")

    targets = [dated_output, pages_output]
    if args.output:
        targets = [args.output]

    for path in targets:
        build_html(payload, run_date, path)

    print(f"\n✅ Done — dashboard built for {run_date}\n")


if __name__ == "__main__":
    main()
