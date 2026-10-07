"""Tests for the data-profiler (stdlib unittest, no network, tiny fixtures)."""

import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from profiler import (
    column_profile,
    correlation_matrix,
    dataset_overview,
    find_alerts,
    load_csv,
    profile_dataset,
)
from report import render_html, render_json
from cli import build_parser, infer_format, default_output, main, SAMPLE_CSV


def sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "id": [101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112],
            "age": [25, 31, 45, 22, 67, 54, 38, 29, 41, 33, 58, 47],
            "income": [40000, 52000, 61000, 38000, 90000, 72000, 55000, 44000, 66000, 49000, 81000, 70000],
            "score": [1, 2, 2, 3, 1, 2, 3, 1, 2, 3, 1, 2],
            "city": ["a", "b", "a", "c", "b", "a", "c", "b", "a", "c", "b", "a"],
            "note": [None, "x", None, None, None, None, None, None, None, None, None, None],
            "constant": ["z"] * 12,
        }
    )


class TestColumnProfile(unittest.TestCase):
    def test_numeric_kind(self):
        p = column_profile(sample_df()["age"])
        self.assertEqual(p["kind"], "number")
        self.assertIn("numeric", p)
        self.assertEqual(p["numeric"]["count"], 12)
        self.assertAlmostEqual(p["numeric"]["mean"], 40.833333, places=5)

    def test_numeric_min_max_median(self):
        n = column_profile(sample_df()["age"])["numeric"]
        self.assertEqual(n["min"], 22)
        self.assertEqual(n["max"], 67)
        self.assertEqual(n["median"], 39.5)

    def test_categorical_kind_and_top(self):
        p = column_profile(sample_df()["city"])
        self.assertEqual(p["kind"], "categorical")
        top = p["categorical"]["top"]
        self.assertEqual(top[0]["value"], "a")
        self.assertEqual(top[0]["count"], 5)

    def test_missing_pct(self):
        p = column_profile(sample_df()["note"])
        self.assertEqual(p["missing"], 11)
        self.assertAlmostEqual(p["missing_pct"], 91.67, places=1)

    def test_constant_flag(self):
        p = column_profile(sample_df()["constant"])
        self.assertTrue(p["constant"])

    def test_id_like_flag(self):
        p = column_profile(sample_df()["id"])
        self.assertTrue(p["id_like"])

    def test_boolean_kind(self):
        p = column_profile(pd.Series([True, False, True], name="flag"))
        self.assertEqual(p["kind"], "boolean")

    def test_datetime_kind(self):
        s = pd.Series(pd.to_datetime(["2024-01-01", "2024-06-01", "2024-12-31"]), name="d")
        p = column_profile(s)
        self.assertEqual(p["kind"], "datetime")
        self.assertEqual(p["datetime"]["span_days"], 365)

    def test_all_null_column(self):
        p = column_profile(pd.Series([None, None, None], name="empty"))
        self.assertEqual(p["unique"], 0)
        self.assertEqual(p["missing_pct"], 100.0)


class TestOverview(unittest.TestCase):
    def test_counts(self):
        ov = dataset_overview(sample_df())
        self.assertEqual(ov["rows"], 12)
        self.assertEqual(ov["columns"], 7)
        self.assertEqual(ov["numeric_columns"], 4)  # id, age, income, score
        self.assertEqual(ov["total_missing"], 11)

    def test_duplicate_rows(self):
        df = pd.DataFrame({"a": [1, 1, 2], "b": ["x", "x", "y"]})
        self.assertEqual(dataset_overview(df)["duplicate_rows"], 1)


class TestCorrelations(unittest.TestCase):
    def test_perfect_correlation(self):
        df = pd.DataFrame({"x": [1, 2, 3, 4, 5], "y": [2, 4, 6, 8, 10]})
        c = correlation_matrix(df)
        self.assertEqual(c["pairs"][0]["r"], 1.0)
        self.assertEqual(c["pairs"][0]["strength"], "very strong")

    def test_pair_ordering_and_labels(self):
        c = correlation_matrix(sample_df())
        self.assertIn("age", c["labels"])
        rs = [abs(p["r"]) for p in c["pairs"]]
        self.assertEqual(rs, sorted(rs, reverse=True))

    def test_too_few_numeric(self):
        df = pd.DataFrame({"only": [1, 2, 3]})
        self.assertEqual(correlation_matrix(df)["pairs"], [])


class TestAlerts(unittest.TestCase):
    def test_constant_alert(self):
        alerts = find_alerts(sample_df(), [column_profile(sample_df()["constant"])])
        codes = [a["code"] for a in alerts]
        self.assertIn("constant", codes)

    def test_missing_alert(self):
        alerts = find_alerts(sample_df(), [column_profile(sample_df()["note"])])
        self.assertIn("missing", [a["code"] for a in alerts])

    def test_id_like_alert(self):
        alerts = find_alerts(sample_df(), [column_profile(sample_df()["id"])])
        self.assertIn("id_like", [a["code"] for a in alerts])

    def test_duplicate_alert(self):
        df = pd.DataFrame({"a": [1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10], "b": [1] * 12})
        alerts = find_alerts(df, [column_profile(df[c]) for c in df.columns])
        self.assertIn("duplicate_rows", [a["code"] for a in alerts])

    def test_alert_sorting_high_first(self):
        alerts = find_alerts(sample_df(), [column_profile(sample_df()[c]) for c in sample_df().columns])
        levels = [a["level"] for a in alerts]
        order = {"high": 0, "medium": 1, "low": 2}
        self.assertEqual(levels, sorted(levels, key=lambda x: order[x]))

    def test_clean_frame_has_no_alerts(self):
        df = pd.DataFrame({"x": [1.0, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5], "y": [1, 2, 3, 4, 5, 6, 7, 9]})
        alerts = find_alerts(df, [column_profile(df[c]) for c in df.columns])
        self.assertEqual([a for a in alerts if a["code"] == "constant"], [])


class TestReport(unittest.TestCase):
    def test_html_contains_sections(self):
        p = profile_dataset(sample_df())
        html_out = render_html(p, title="Test Report")
        self.assertIn("Test Report", html_out)
        self.assertIn("Alerts", html_out)
        self.assertIn("Correlations", html_out)
        self.assertIn("income", html_out)
        self.assertIn("</html>", html_out)

    def test_html_escapes_titles(self):
        p = profile_dataset(sample_df())
        html_out = render_html(p, title="<script>alert(1)</script>")
        self.assertNotIn("<script>alert(1)</script>", html_out)
        self.assertIn("&lt;script&gt;", html_out)

    def test_json_is_serializable_and_round_trips(self):
        p = profile_dataset(sample_df())
        text = render_json(p)
        back = json.loads(text)
        self.assertEqual(back["overview"]["rows"], 12)
        self.assertEqual(len(back["columns"]), len(p["columns"]))


class TestCLI(unittest.TestCase):
    def test_parser_defaults(self):
        args = build_parser().parse_args(["data.csv"])
        self.assertEqual(args.top, 5)
        self.assertEqual(args.sep, ",")

    def test_infer_format(self):
        args = build_parser().parse_args(["a.csv", "-o", "out.json"])
        self.assertEqual(infer_format(args), "json")
        args = build_parser().parse_args(["a.csv", "-o", "out.html"])
        self.assertEqual(infer_format(args), "html")
        args = build_parser().parse_args(["a.csv"])
        self.assertEqual(infer_format(args), "html")
        args = build_parser().parse_args(["a.csv", "-f", "json"])
        self.assertEqual(infer_format(args), "json")

    def test_default_output(self):
        self.assertEqual(default_output("sales.csv", "html"), "sales_profile.html")
        self.assertEqual(default_output(None, "json"), "sample_profile.json")

    def test_sample_mode_writes_html(self):
        with TemporaryDirectory() as d:
            out = Path(d) / "s.html"
            rc = main(["--sample", "-o", str(out), "-q"])
            self.assertEqual(rc, 0)
            content = out.read_text(encoding="utf-8")
            self.assertIn("Dataset Profile", content)
            self.assertIn("Mumbai", content)

    def test_sample_mode_writes_json(self):
        with TemporaryDirectory() as d:
            out = Path(d) / "s.json"
            rc = main(["--sample", "-o", str(out), "-f", "json", "-q"])
            self.assertEqual(rc, 0)
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertIn("overview", data)
            self.assertGreaterEqual(len(data["columns"]), 6)

    def test_missing_file_returns_1(self):
        rc = main(["does_not_exist_xyz.csv", "-q"])
        self.assertEqual(rc, 1)

    def test_no_input_no_sample_prints_help(self):
        rc = main([])
        self.assertEqual(rc, 2)

    def test_empty_csv_returns_1(self):
        with TemporaryDirectory() as d:
            bad = Path(d) / "empty.csv"
            bad.write_text("", encoding="utf-8")
            rc = main([str(bad), "-q"])
            self.assertEqual(rc, 1)

    def test_real_csv_round_trip(self):
        with TemporaryDirectory() as d:
            csv_path = Path(d) / "sample.csv"
            csv_path.write_text(SAMPLE_CSV, encoding="utf-8")
            out = Path(d) / "report.html"
            rc = main([str(csv_path), "-o", str(out), "-q"])
            self.assertEqual(rc, 0)
            self.assertTrue(out.exists())
            self.assertIn("population", out.read_text(encoding="utf-8"))

    def test_load_csv_stringio(self):
        df = load_csv(io.StringIO(SAMPLE_CSV))
        self.assertEqual(df.shape[1], 6)


if __name__ == "__main__":
    unittest.main()