import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from scdi.data import validate_daily
from scdi.database import write_database

ROOT = Path(__file__).resolve().parents[1]


def daily_fixture():
    return pd.DataFrame(
        {
            "series_id": ["1:9", "1:9"],
            "date": ["2024-06-01", "2024-06-02"],
            "sales": [2.0, 0.0],
            "stockout_hours": [0, 8],
            "city_id": [1, 1],
            "store_id": [1, 1],
            "product_id": [9, 9],
            "category_id": [2, 2],
            "discount": [1.0, 0.9],
            "holiday_flag": [0, 0],
            "activity_flag": [0, 1],
            "source_split": ["train", "eval"],
        }
    )


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("sales", -1, "nonnegative"),
        ("sales", float("nan"), "missing"),
        ("stockout_hours", 17, "0 to 16"),
        ("stockout_hours", 0.5, "integer"),
        ("date", "invalid", "Invalid date"),
        ("series_id", "", "identifier"),
        ("product_id", -2, "nonnegative integer"),
    ],
)
def test_reject_bad_daily_fields(field, value, message):
    frame = daily_fixture()
    frame[field] = frame[field].astype(object)
    frame.loc[0, field] = value
    with pytest.raises(ValueError, match=message):
        validate_daily(frame)


def test_duplicate_keys_are_not_silently_dropped():
    frame = pd.concat([daily_fixture(), daily_fixture().iloc[[0]]])
    with pytest.raises(ValueError, match="Duplicate"):
        validate_daily(frame)


def test_dimension_drift_rejected():
    frame = daily_fixture()
    frame.loc[1, "category_id"] = 7
    with pytest.raises(ValueError, match="dimension changes"):
        validate_daily(frame)


def test_star_schema_reconciliation_and_visible_sql(tmp_path):
    path = tmp_path / "test.sqlite"
    frame = daily_fixture()
    summary = pd.DataFrame({"series_id": ["1:9"], "status": ["High Risk"], "sales_cv": [0.0]})
    forecasts = pd.DataFrame({"series_id": ["1:9"], "date": ["2024-06-03"], "prediction": [1.0]})
    scores = pd.DataFrame({"series_id": ["1:9"], "MAE": [1.0]})
    write_database(path, frame, summary, forecasts, scores, {"scope": "test"})
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys=ON")
        assert db.execute("SELECT COUNT(*) FROM daily_sales").fetchone()[0] == 2
        assert db.execute("SELECT SUM(sales) FROM daily_sales").fetchone()[0] == 2
        result = pd.read_sql_query((ROOT / "sql/01_category_availability.sql").read_text(), db)
        assert result.iloc[0].stockout_hour_rate == 0.25
        assert result.iloc[0].stockout_day_rate == 0.5
        queue = pd.read_sql_query((ROOT / "sql/04_management_queue.sql").read_text(), db)
        assert queue.iloc[0].availability_status == "Critical"
        for query in (ROOT / "sql").glob("*.sql"):
            assert not pd.read_sql_query(query.read_text(), db).empty
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO fact_daily_sales VALUES ('missing','2024-06-01',1,0,1,0,0,'train')"
            )
