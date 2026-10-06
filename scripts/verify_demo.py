"""Recompute real-demo forecasts, priorities and SQL; compare with saved outputs."""

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from scdi.data import validate_daily
from scdi.forecasting import forecast_sales
from scdi.inventory import summarize_inventory

ROOT = Path(__file__).resolve().parents[1]


def verify() -> None:
    with sqlite3.connect(ROOT / "data/demo/decision_intelligence.sqlite") as db:
        daily = pd.read_sql_query("SELECT * FROM daily_sales ORDER BY series_id,date", db)
        saved = pd.read_sql_query("SELECT * FROM series_summary ORDER BY series_id", db)
        predictions = pd.read_sql_query(
            "SELECT * FROM forecast_values WHERE split='holdout' ORDER BY series_id,date", db
        )
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        for query in (ROOT / "sql").glob("*.sql"):
            assert not pd.read_sql_query(query.read_text(), db).empty
    validate_daily(daily)
    forecast = forecast_sales(daily)
    recomputed = forecast.holdout_predictions.sort_values(["series_id", "date"])
    assert np.allclose(predictions.prediction, recomputed.prediction, atol=1e-12)
    assert predictions.selected_model.tolist() == recomputed.selected_model.tolist()
    summary = summarize_inventory(daily).sort_values("series_id")
    for column in [
        "availability_risk",
        "volume_abc_class",
        "xyz_class",
        "recommendation",
        "reason",
    ]:
        assert summary[column].tolist() == saved[column].tolist(), column
    for column in [
        "stockout_hour_rate",
        "stockout_day_fraction",
        "sales_cv",
        "observed_mean_sales",
    ]:
        assert np.allclose(summary[column], saved[column], atol=1e-12), column
    print(
        f"Reproduced {len(summary)} real series, {len(daily):,} daily observations, all SQL and saved forecasts"
    )


if __name__ == "__main__":
    verify()
