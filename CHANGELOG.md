# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.0.0] - 2026-10-07

### Added
- `profiler.py` — pandas-based core: dataset overview (shape, dtypes, memory, missing, duplicates), per-column profiles (kind inference, missing %, cardinality, numeric stats with IQR/skew/outliers, categorical top values + entropy, datetime ranges), Pearson correlation matrix with strength labels, and a rule-based alert engine.
- `report.py` — self-contained HTML report (inline CSS, dark theme, no CDN/network) plus JSON serialization of the full profile.
- `cli.py` — argparse CLI: `input.csv`, `-o` output, `-f {html,json}`, `--title`, `--top`, `--sep`, `--sample` demo dataset, `-q` quiet mode, non-zero exits on missing/empty/unreadable input.
- Alert rules: constant columns, high missingness (>=40%), id-like columns (name heuristic or >=98% unique with >=50 values), heavy skew (|skew|>=1), IQR outliers, strong correlations (|r|>=0.9), duplicate rows — sorted high → medium → low.
- `examples/sample_report.html` and `examples/sample_report.json` — pre-generated reports for the built-in sample dataset.
- 33 unit tests (`test_profiler.py`, stdlib `unittest`) covering profiling, correlations, alerts, HTML escaping, JSON round-trips, and CLI exit codes.
- GitHub Actions CI (Python 3.11 / 3.13 matrix).

[1.0.0]: https://github.com/HSJplayz/data-profiler/releases/tag/v1.0.0