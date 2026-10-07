"""Core dataset profiling: summary stats, per-column analysis, correlations, alerts.

Pure pandas/numpy logic with no rendering concerns, so it is easy to test and
reuse from the CLI, the HTML report, or a Python API.
"""

from __future__ import annotations

import math
import re

import numpy as np
import pandas as pd

MISSING_ALERT_PCT = 40.0
HIGH_CARDINALITY_RATIO = 0.95
SKEW_ALERT = 1.0
ID_UNIQUE_RATIO = 0.98
ID_MIN_UNIQUE = 50
ID_NAME_RE = re.compile(r"(^|_)(id|uuid|guid|key|slug|hash|token|index)($|_)", re.I)


def _kind_of(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    if pd.api.types.is_numeric_dtype(series):
        return "number"
    if pd.api.types.is_timedelta64_dtype(series):
        return "timedelta"
    return "categorical"


def _numeric_summary(series: pd.Series) -> dict:
    s = series.dropna().astype(float)
    if s.empty:
        return {"count": 0}
    desc = s.describe()
    q1 = float(desc["25%"])
    q3 = float(desc["75%"])
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    outliers = int(((s < lower) | (s > upper)).sum())
    skew = float(s.skew()) if len(s) >= 3 and s.std() != 0 else 0.0
    return {
        "count": int(desc["count"]),
        "mean": float(desc["mean"]),
        "median": float(s.median()),
        "std": float(desc["std"]) if not math.isnan(desc["std"]) else 0.0,
        "min": float(desc["min"]),
        "max": float(desc["max"]),
        "q1": q1,
        "q3": q3,
        "iqr": iqr,
        "zeros": int((s == 0).sum()),
        "negatives": int((s < 0).sum()),
        "outliers": outliers,
        "skew": round(skew, 3),
    }


def _categorical_summary(series: pd.Series, top_n: int = 5) -> dict:
    s = series.dropna()
    if s.empty:
        return {"count": 0, "unique": 0, "top": []}
    vc = s.astype(str).value_counts()
    total = int(vc.sum())
    top = [
        {"value": str(k), "count": int(v), "pct": round(100.0 * v / total, 1)}
        for k, v in vc.head(top_n).items()
    ]
    return {
        "count": int(len(s)),
        "unique": int(vc.size),
        "top": top,
        "entropy": round(float(_entropy(vc.to_numpy(), total)), 3),
    }


def _entropy(counts: np.ndarray, total: int) -> float:
    if total <= 0 or len(counts) <= 1:
        return 0.0
    p = counts / total
    p = p[p > 0]
    return float(-(p * np.log2(p)).sum())


def column_profile(series: pd.Series, top_n: int = 5) -> dict:
    kind = _kind_of(series)
    missing = int(series.isna().sum())
    n = int(len(series))
    prof = {
        "name": str(series.name),
        "kind": kind,
        "dtype": str(series.dtype),
        "count": n,
        "missing": missing,
        "missing_pct": round(100.0 * missing / n, 2) if n else 0.0,
        "unique": int(series.nunique(dropna=True)),
    }
    if n:
        prof["unique_pct"] = round(100.0 * prof["unique"] / n, 2)
        prof["constant"] = prof["unique"] <= 1
        name_looks_like_id = bool(ID_NAME_RE.search(str(series.name)))
        high_cardinality = (
            prof["unique"] >= ID_UNIQUE_RATIO * n and n > 10 and prof["unique"] >= ID_MIN_UNIQUE
        )
        prof["id_like"] = kind in ("number", "categorical") and (
            high_cardinality or (name_looks_like_id and prof["unique"] >= 0.5 * n)
        )
    else:
        prof["unique_pct"] = 0.0
        prof["constant"] = True
        prof["id_like"] = False

    if kind == "number":
        prof["numeric"] = _numeric_summary(series)
    elif kind == "categorical":
        prof["categorical"] = _categorical_summary(series, top_n)
    elif kind == "datetime":
        s = series.dropna()
        if not s.empty:
            prof["datetime"] = {
                "min": str(s.min()),
                "max": str(s.max()),
                "span_days": int((s.max() - s.min()).days)
                if isinstance(s.max() - s.min(), pd.Timedelta)
                else None,
            }
    return prof


def dataset_overview(df: pd.DataFrame) -> dict:
    n_rows, n_cols = df.shape
    kinds: dict[str, int] = {}
    for c in df.columns:
        k = _kind_of(df[c])
        kinds[k] = kinds.get(k, 0) + 1
    mem = int(df.memory_usage(deep=True).sum())
    return {
        "rows": int(n_rows),
        "columns": int(n_cols),
        "kinds": kinds,
        "memory_bytes": mem,
        "memory_mb": round(mem / (1024 * 1024), 2),
        "duplicate_rows": int(df.duplicated().sum()),
        "total_missing": int(df.isna().sum().sum()),
        "missing_pct": round(100.0 * df.isna().sum().sum() / (n_rows * n_cols), 2)
        if n_rows and n_cols
        else 0.0,
        "numeric_columns": int(sum(1 for c in df.columns if _kind_of(df[c]) == "number")),
    }


def correlation_matrix(df: pd.DataFrame) -> dict:
    numeric = df.select_dtypes(include=[np.number])
    if numeric.shape[1] < 2:
        return {"labels": list(numeric.columns), "pairs": []}
    corr = numeric.corr().round(3)
    labels = [str(c) for c in corr.columns]
    pairs = []
    cols = list(corr.columns)
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            v = corr.iloc[i, j]
            if pd.isna(v):
                continue
            pairs.append(
                {
                    "a": str(cols[i]),
                    "b": str(cols[j]),
                    "r": float(v),
                    "strength": _strength(float(v)),
                }
            )
    pairs.sort(key=lambda p: abs(p["r"]), reverse=True)
    return {"labels": labels, "matrix": corr.fillna(0).to_numpy().tolist(), "pairs": pairs}


def _strength(r: float) -> str:
    a = abs(r)
    if a >= 0.9:
        return "very strong"
    if a >= 0.7:
        return "strong"
    if a >= 0.4:
        return "moderate"
    if a >= 0.2:
        return "weak"
    return "negligible"


def find_alerts(df: pd.DataFrame, profiles: list[dict]) -> list[dict]:
    alerts: list[dict] = []
    n_rows = len(df)

    for p in profiles:
        name = p["name"]
        if p["constant"]:
            alerts.append(
                {
                    "level": "high",
                    "column": name,
                    "code": "constant",
                    "message": f"'{name}' has a single constant value.",
                }
            )
        if p["missing_pct"] >= MISSING_ALERT_PCT and p["missing"] > 0:
            alerts.append(
                {
                    "level": "high",
                    "column": name,
                    "code": "missing",
                    "message": (
                        f"'{name}' is {p['missing_pct']}% missing "
                        f"({p['missing']} of {p['count']})."
                    ),
                }
            )
        if p["id_like"]:
            alerts.append(
                {
                    "level": "medium",
                    "column": name,
                    "code": "id_like",
                    "message": (
                        f"'{name}' looks like an identifier "
                        f"({p['unique_pct']}% unique values)."
                    ),
                }
            )
        num = p.get("numeric")
        if num and num.get("count", 0) >= 8:
            if abs(num.get("skew", 0.0)) >= SKEW_ALERT:
                direction = "right" if num["skew"] > 0 else "left"
                alerts.append(
                    {
                        "level": "medium",
                        "column": name,
                        "code": "skewed",
                        "message": (
                            f"'{name}' is heavily {direction}-skewed "
                            f"(skew={num['skew']}); consider a log/box-cox transform."
                        ),
                    }
                )
            if num.get("outliers", 0) > 0 and num["count"] >= 8:
                alerts.append(
                    {
                        "level": "low",
                        "column": name,
                        "code": "outliers",
                        "message": (
                            f"'{name}' has {num['outliers']} IQR outlier(s) "
                            f"outside [{num['q1']:.2f}, {num['q3']:.2f}]."
                        ),
                    }
                )

    corr = correlation_matrix(df)
    for pair in corr["pairs"]:
        if abs(pair["r"]) >= 0.9:
            alerts.append(
                {
                    "level": "medium",
                    "column": f"{pair['a']} / {pair['b']}",
                    "code": "multicollinearity",
                    "message": (
                        f"'{pair['a']}' and '{pair['b']}' are {pair['strength']}ly "
                        f"correlated (r={pair['r']}); watch for multicollinearity."
                    ),
                }
            )

    dupes = int(df.duplicated().sum())
    if dupes:
        alerts.append(
            {
                "level": "medium",
                "column": "(dataset)",
                "code": "duplicate_rows",
                "message": f"{dupes} duplicate row(s) detected ({round(100 * dupes / max(n_rows, 1), 1)}%).",
            }
        )

    order = {"high": 0, "medium": 1, "low": 2}
    alerts.sort(key=lambda a: order.get(a["level"], 3))
    return alerts


def profile_dataset(df: pd.DataFrame, top_n: int = 5) -> dict:
    profiles = [column_profile(df[c], top_n) for c in df.columns]
    return {
        "overview": dataset_overview(df),
        "columns": profiles,
        "correlations": correlation_matrix(df),
        "alerts": find_alerts(df, profiles),
    }


def load_csv(path: str, **read_kwargs) -> pd.DataFrame:
    return pd.read_csv(path, **read_kwargs)