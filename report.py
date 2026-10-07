"""Render a profiling dict into a self-contained HTML report (no CDN/assets)."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone

_CSS = """
:root { --bg:#0f1115; --card:#171a21; --ink:#e6e8ee; --muted:#9aa0ad;
  --accent:#4f8cff; --good:#3fb950; --warn:#f0b429; --bad:#f85149; --line:#262b36; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI",sans-serif; padding:32px; }
main { max-width:1000px; margin:0 auto; }
h1 { font-size:1.7rem; margin:0; }
h2 { font-size:1.15rem; border-bottom:1px solid var(--line); padding-bottom:6px; margin-top:36px; }
.muted { color:var(--muted); font-size:.9rem; }
.cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin-top:16px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:12px; }
.card .n { font-size:1.5rem; font-weight:700; }
table { width:100%; border-collapse:collapse; margin-top:10px; font-size:.88rem; }
th,td { text-align:left; padding:7px 9px; border-bottom:1px solid var(--line); vertical-align:top; }
th { color:var(--muted); font-weight:500; }
.badge { display:inline-block; padding:1px 7px; border-radius:999px; font-size:.75rem;
  border:1px solid var(--line); }
.k-number { color:#79c0ff; } .k-categorical { color:#d2a8ff; } .k-boolean { color:#7ee787; }
.k-datetime { color:#ffa657; } .k-timedelta { color:#ff7b72; }
.alert { border-left:3px solid var(--line); padding:8px 12px; margin-top:8px; background:var(--card); border-radius:0 8px 8px 0; }
.alert.high { border-color:var(--bad); }
.alert.medium { border-color:var(--warn); }
.alert.low { border-color:var(--accent); }
.badge.high { color:var(--bad); border-color:var(--bad); }
.badge.medium { color:var(--warn); border-color:var(--warn); }
.badge.low { color:var(--accent); border-color:var(--accent); }
.bar { display:inline-block; height:9px; background:var(--accent); border-radius:4px; vertical-align:middle; }
code { font-family:ui-monospace,Consolas,monospace; background:var(--card); padding:1px 5px; border-radius:4px; }
.corr-r-strong { color:var(--bad); font-weight:600; }
.corr-r-mid { color:var(--warn); }
.corr-r-low { color:var(--muted); }
"""

_LEVEL_LABEL = {"high": "HIGH", "medium": "MED", "low": "LOW"}


def _e(v) -> str:
    return html.escape(str(v))


def _fmt(v) -> str:
    if isinstance(v, float):
        if abs(v) >= 1000:
            return f"{v:,.1f}"
        return f"{v:.3f}".rstrip("0").rstrip(".")
    if isinstance(v, int):
        return f"{v:,}"
    return _e(v)


def _render_overview(ov: dict) -> str:
    items = [
        ("Rows", _fmt(ov["rows"])),
        ("Columns", _fmt(ov["columns"])),
        ("Numeric cols", _fmt(ov["numeric_columns"])),
        ("Missing cells", f"{_fmt(ov['total_missing'])} ({ov['missing_pct']}%)"),
        ("Duplicate rows", _fmt(ov["duplicate_rows"])),
        ("Memory", f"{ov['memory_mb']} MB"),
    ]
    cards = "".join(f'<div class="card"><div class="muted">{k}</div><div class="n">{v}</div></div>' for k, v in items)
    kinds = ", ".join(f"{k}: {v}" for k, v in sorted(ov["kinds"].items()))
    return f'<div class="cards">{cards}</div><p class="muted">Column kinds — {kinds}</p>'


def _render_alerts(alerts: list[dict]) -> str:
    if not alerts:
        return '<p class="muted">No data-quality alerts. Nice.</p>'
    out = []
    for a in alerts:
        out.append(
            f'<div class="alert {a["level"]}">'
            f'<span class="badge {a["level"]}">{_LEVEL_LABEL[a["level"]]}</span> '
            f'<strong>{_e(a["column"])}</strong> — {_e(a["message"])}</div>'
        )
    return "".join(out)


def _render_columns(columns: list[dict]) -> str:
    rows = []
    for c in columns:
        kind = c["kind"]
        detail_parts = []
        num = c.get("numeric")
        if num and num.get("count"):
            detail_parts.append(
                f"mean {_fmt(num['mean'])} · med {_fmt(num['median'])} · "
                f"std {_fmt(num['std'])} · min {_fmt(num['min'])} · max {_fmt(num['max'])}"
            )
        cat = c.get("categorical")
        if cat and cat.get("top"):
            tops = ", ".join(f"{_e(t['value'])} ({t['pct']}%)" for t in cat["top"][:3])
            detail_parts.append(f"top: {tops}")
        dt = c.get("datetime")
        if dt:
            detail_parts.append(f"{_e(dt['min'])} → {_e(dt['max'])}")
        detail = "<br>".join(detail_parts) or "<span class='muted'>—</span>"

        flags = []
        if c.get("constant"):
            flags.append('<span class="badge high">constant</span>')
        if c.get("id_like"):
            flags.append('<span class="badge medium">id-like</span>')
        if c["missing_pct"] >= 40:
            flags.append('<span class="badge high">missing</span>')
        flag_html = " ".join(flags)

        mpct = c["missing_pct"]
        bar = f'<span class="bar" style="width:{max(2, mpct / 4):.0f}px"></span> ' if mpct else ""
        rows.append(
            f"<tr><td><strong>{_e(c['name'])}</strong><br>{flag_html}</td>"
            f"<td><span class='badge k-{kind}'>{kind}</span><br><span class='muted'>{_e(c['dtype'])}</span></td>"
            f"<td>{_fmt(c['missing'])} ({mpct}%){bar}</td>"
            f"<td>{_fmt(c['unique'])} ({c.get('unique_pct', 0)}%)</td>"
            f"<td>{detail}</td></tr>"
        )
    head = (
        "<tr><th>Column</th><th>Kind</th><th>Missing</th><th>Unique</th><th>Details</th></tr>"
    )
    return f"<table>{head}{''.join(rows)}</table>"


def _corr_class(r: float) -> str:
    a = abs(r)
    if a >= 0.7:
        return "corr-r-strong"
    if a >= 0.4:
        return "corr-r-mid"
    return "corr-r-low"


def _render_correlations(corr: dict) -> str:
    pairs = corr.get("pairs", [])
    if not pairs:
        return '<p class="muted">Not enough numeric columns to correlate.</p>'
    rows = []
    for p in pairs[:15]:
        rows.append(
            f"<tr><td>{_e(p['a'])}</td><td>{_e(p['b'])}</td>"
            f"<td class='{_corr_class(p['r'])}'>{p['r']}</td>"
            f"<td>{_e(p['strength'])}</td></tr>"
        )
    head = "<tr><th>Column A</th><th>Column B</th><th>r</th><th>Strength</th></tr>"
    return f"<table>{head}{''.join(rows)}</table>"


def render_html(profile: dict, title: str = "Dataset Profile") -> str:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(title)}</title>
<style>{_CSS}</style>
</head>
<body>
<main>
<h1>{_e(title)}</h1>
<p class="muted">Generated by <a href="https://github.com/HSJplayz/data-profiler" style="color:var(--accent)">data-profiler</a> · {_e(generated)}</p>
<h2>Overview</h2>
{_render_overview(profile["overview"])}
<h2>Alerts ({len(profile["alerts"])})</h2>
{_render_alerts(profile["alerts"])}
<h2>Columns ({len(profile["columns"])})</h2>
{_render_columns(profile["columns"])}
<h2>Correlations</h2>
{_render_correlations(profile["correlations"])}
</main>
</body>
</html>"""


def render_json(profile: dict, indent: int = 2) -> str:
    return json.dumps(profile, indent=indent, ensure_ascii=False, default=str)