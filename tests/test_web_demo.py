"""Published subset metrics and observations must reconcile with the verified SQLite demo."""

import importlib.util
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("web_builder", ROOT / "scripts/build_web_demo.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test_web_export_preserves_all_real_observations_and_scoped_metrics(tmp_path):
    manifest = builder.build_demo(tmp_path)
    exported = json.loads((tmp_path / "data.json").read_text())
    with sqlite3.connect(ROOT / "data/demo/decision_intelligence.sqlite") as connection:
        daily = pd.read_sql_query(
            "SELECT series_id,date,sales,stockout_hours FROM daily_sales ORDER BY series_id,date",
            connection,
        )
        holdout = pd.read_sql_query(
            "SELECT actual,prediction FROM forecast_values WHERE split='holdout'", connection
        )
    assert exported["scope"] == manifest["scope"] == "demo"
    assert exported["rows"] == len(daily) == 19400
    assert exported["series_count"] == daily.series_id.nunique() == 200
    assert exported["dates"] == sorted(daily.date.unique().tolist())
    for item in exported["items"]:
        original = daily.loc[daily.series_id == item["series_id"], ["sales", "stockout_hours"]]
        np.testing.assert_array_equal(item["history"], original.to_numpy())
    assert exported["kpis"]["stockout_day_rate"] == pytest.approx(daily.stockout_hours.gt(0).mean())
    assert exported["kpis"]["wape"] == pytest.approx(
        (holdout.prediction - holdout.actual).abs().sum() / holdout.actual.abs().sum()
    )
    assert exported["kpis"]["stockout_hour_rate"] == pytest.approx(
        daily.stockout_hours.sum() / (19400 * 16)
    )
    assert sum(item["recent_sales_share"] for item in exported["items"]) == pytest.approx(1)
    # The subset intentionally differs from population results, preventing full KPI substitution.
    full = json.loads((ROOT / "docs/evidence/findings.json").read_text())
    assert exported["kpis"]["wape"] != full["forecast"]["holdout_metrics"]["all_days"]["wape"]
    assert "plotly.js" in (tmp_path / "plotly.min.js").read_text()[:300]
