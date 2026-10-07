# data-profiler

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB.svg)](https://www.python.org/)
[![CI](https://github.com/HSJplayz/data-profiler/actions/workflows/ci.yml/badge.svg)](https://github.com/HSJplayz/data-profiler/actions/workflows/ci.yml)
[![Streak Day 15](https://img.shields.io/badge/Streak-Day%2015-green.svg)](https://github.com/HSJplayz/streak)

Profile any CSV dataset in one command: column statistics, data-quality alerts,
correlations, and a self-contained HTML or JSON report — no notebook, no CDN,
no network required.

Built with pandas on **Day 15** of the daily projects streak.

## Quick start

```bash
pip install -r requirements.txt

# HTML report (opens in any browser, fully offline)
python cli.py sales.csv

# JSON report for pipelines
python cli.py sales.csv -f json -o profile.json

# Try it without a file — a built-in sample dataset
python cli.py --sample -o sample_report.html
```

Open [`examples/sample_report.html`](examples/sample_report.html) to see a
pre-generated report.

## What you get

| Section | Details |
| --- | --- |
| **Overview** | rows × columns, column kinds, total missing cells, duplicate rows, memory usage |
| **Alerts** | constant columns, high missingness, id-like columns, heavy skew, IQR outliers, strong correlations, duplicate rows — ranked high/medium/low |
| **Columns** | per-column kind (number/categorical/boolean/datetime), missing %, unique count, mean/median/std/quartiles, top category values, datetime ranges |
| **Correlations** | Pearson matrix for numeric columns with `r` and strength labels (negligible → very strong) |

### Alerts (real output)

```
Profile: 126 rows x 8 cols, 55 missing cells (5.46%), 6 duplicate rows
Alerts (8):
  [high  ] income: 'income' is 43.65% missing (55 of 126).
  [high  ] always_zero: 'always_zero' has a single constant value.
  [medium] user_id: 'user_id' looks like an identifier (95.24% unique values).
  [medium] spend: 'spend' is heavily right-skewed (skew=7.839); consider a log/box-cox transform.
  [medium] (dataset): 6 duplicate row(s) detected (4.8%).
  [low   ] income: 'income' has 10 IQR outlier(s) outside [25800.00, 51400.00].
```

## CLI reference

```
python cli.py [input.csv] [options]

  -o, --output PATH     output file (default: <input>_profile.html / .json)
  -f, --format {html,json}   report format (inferred from extension otherwise)
  --title TEXT          report title (default: "Dataset Profile")
  --top N               top categories listed per column (default 5)
  --sep CHAR            CSV separator (default ",")
  --sample              profile the built-in sample dataset instead of a file
  -q, --quiet           suppress the stdout summary
```

Exit codes: `0` success, `1` read/write error (missing, unreadable, or empty
CSV), `2` no input given.

## Library use

```python
from pathlib import Path

from profiler import load_csv, profile_dataset
from report import render_html

profile = profile_dataset(load_csv("sales.csv"), top_n=5)
print(profile["overview"])
for alert in profile["alerts"]:
    print(alert["level"], alert["column"], alert["message"])

Path("report.html").write_text(render_html(profile, title="Sales"), encoding="utf-8")
```

## Project layout

```
profiler.py    core stats + alert engine (pure pandas/numpy)
report.py      HTML renderer (inline CSS) + JSON export
cli.py         argparse front-end, sample dataset, exit codes
test_profiler.py  33 unittest cases
examples/      pre-generated sample report (HTML + JSON)
```

## Future scope

- CSV/Excel multi-file profiling and directory mode
- Optional matplotlib charts (histograms, scatter matrix)
- Profiling for Parquet/JSON-lines inputs
- Config file for alert thresholds and ignored columns
- HTML anchors + a table of contents for wide reports

## Tests

```bash
python -m unittest test_profiler -v
```

33 tests, no network, no fixtures on disk beyond tiny in-memory frames.

## License

MIT — see [LICENSE](LICENSE).