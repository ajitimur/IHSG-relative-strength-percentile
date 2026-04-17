"""
extract_template.py
===================
Run this after Claude produces an updated dashboard HTML to refresh
the template files used by build_dashboard.py.

Usage:
    python extract_template.py outputs/idx_rs_dashboard_20260417.html

Writes:
    dashboard_template_a.html   HTML + CSS + modal (before data injection)
    dashboard_template_b.js     JS engine (after data, before </script>)
    dashboard_template_c.html   Closing tags
"""

import sys
import os


def extract(source_path):
    with open(source_path, encoding="utf-8") as f:
        html = f.read()

    marker     = "const EMBEDDED ="
    start      = html.find(marker)
    data_end   = html.find(";\n", start) + 2
    script_end = html.rfind("</script>")

    if start == -1:
        raise ValueError(f"Marker '{marker}' not found in {source_path}. "
                         "Is this a valid IDX RS dashboard HTML?")

    tmpl_a = html[:start]
    tmpl_b = html[data_end:script_end]
    tmpl_c = html[script_end:]

    here = os.path.dirname(os.path.abspath(__file__))
    paths = {
        "dashboard_template_a.html": tmpl_a,
        "dashboard_template_b.js":   tmpl_b,
        "dashboard_template_c.html": tmpl_c,
    }
    for fname, content in paths.items():
        out = os.path.join(here, fname)
        with open(out, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  Wrote {fname} ({len(content):,} bytes)")

    print(f"\nTemplate updated from: {source_path}")
    print("build_dashboard.py will use these files on next run.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        print("Error: provide the path to a built dashboard HTML file.")
        sys.exit(1)
    extract(sys.argv[1])
