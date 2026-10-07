"""CLI for data-profiler: profile a CSV file and emit an HTML or JSON report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from profiler import load_csv, profile_dataset
from report import render_html, render_json

SAMPLE_CSV = """city,population,area_km2,unemployment_pct,year,region
Mumbai,20411000,603,6.1,2024,West
Delhi,16788000,1484,7.4,2024,North
Kolkata,4500000,205,5.2,2024,East
Chennai,7088000,426,6.6,2024,South
Pune,3124459,331,5.0,2024,West
Bengaluru,8443675,709,5.5,2024,South
Hyderabad,6809970,650,4.9,2024,South
Ahmedabad,5633927,505,5.8,2024,West
Jaipur,3073350,485,6.9,2024,North
Lucknow,2845000,349,6.4,2024,North
Surat,5907000,326,4.5,2024,West
Kanpur,3052000,403,7.1,2024,North
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="data-profiler",
        description="Profile a CSV dataset and generate an HTML/JSON report.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python cli.py data.csv\n"
            "  python cli.py data.csv -o report.html --title 'Sales 2026'\n"
            "  python cli.py data.csv -f json\n"
            "  python cli.py --sample > sample_report.html"
        ),
    )
    p.add_argument("input", nargs="?", help="path to a CSV file")
    p.add_argument("-o", "--output", help="output file (default: <input>_profile.html / .json)")
    p.add_argument(
        "-f",
        "--format",
        choices=["html", "json"],
        help="report format (default: inferred from output extension, else html)",
    )
    p.add_argument("--title", default="Dataset Profile", help="report title")
    p.add_argument("--top", type=int, default=5, help="top categories per column (default 5)")
    p.add_argument("--sep", default=",", help="CSV separator (default ',')")
    p.add_argument(
        "--sample",
        action="store_true",
        help="profile a built-in sample dataset instead of a file",
    )
    p.add_argument("-q", "--quiet", action="store_true", help="suppress the stdout summary")
    return p


def infer_format(args: argparse.Namespace) -> str:
    if args.format:
        return args.format
    if args.output:
        return "json" if Path(args.output).suffix.lower() == ".json" else "html"
    return "html"


def default_output(input_path: str | None, fmt: str) -> str:
    stem = Path(input_path).stem if input_path else "sample"
    return f"{stem}_profile.{fmt}"


def print_summary(profile: dict, stream=sys.stdout) -> None:
    ov = profile["overview"]
    stream.write(
        f"Profile: {ov['rows']} rows x {ov['columns']} cols, "
        f"{ov['total_missing']} missing cells ({ov['missing_pct']}%), "
        f"{ov['duplicate_rows']} duplicate rows\n"
    )
    alerts = profile["alerts"]
    if alerts:
        stream.write(f"Alerts ({len(alerts)}):\n")
        for a in alerts:
            stream.write(f"  [{a['level']:6}] {a['column']}: {a['message']}\n")
    else:
        stream.write("Alerts: none\n")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.input and not args.sample:
        build_parser().print_help()
        return 2

    try:
        if args.sample:
            import io

            df = load_csv(io.StringIO(SAMPLE_CSV), sep=",")
            src_label = "sample dataset"
        else:
            df = load_csv(args.input, sep=args.sep)
            src_label = args.input
    except FileNotFoundError:
        print(f"error: file not found: {args.input}", file=sys.stderr)
        return 1
    except Exception as err:  # pandas raises many parser errors
        print(f"error: could not read CSV: {err}", file=sys.stderr)
        return 1

    if df.empty or df.shape[1] == 0:
        print("error: input has no rows or no columns", file=sys.stderr)
        return 1

    fmt = infer_format(args)
    out_path = args.output or default_output(args.input, fmt)
    profile = profile_dataset(df, top_n=args.top)

    try:
        if fmt == "json":
            Path(out_path).write_text(render_json(profile), encoding="utf-8")
        else:
            title = args.title if args.title != "Dataset Profile" else f"Dataset Profile — {Path(src_label).name}"
            Path(out_path).write_text(render_html(profile, title=title), encoding="utf-8")
    except OSError as err:
        print(f"error: cannot write output: {err}", file=sys.stderr)
        return 1

    if not args.quiet:
        print_summary(profile)
        print(f"Wrote {fmt.upper()} report to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())