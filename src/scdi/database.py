"""SQLite star schema, constrained facts, and visible business SQL."""

import sqlite3
from pathlib import Path

import pandas as pd

DIMENSIONS = ["series_id", "city_id", "store_id", "product_id", "category_id"]
FACTS = [
    "series_id",
    "date",
    "sales",
    "stockout_hours",
    "discount",
    "holiday_flag",
    "activity_flag",
    "source_split",
]


def write_database(
    path: Path,
    daily: pd.DataFrame,
    summary: pd.DataFrame,
    forecasts: pd.DataFrame,
    scores: pd.DataFrame,
    metadata: dict,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript("""
            CREATE TABLE dim_series (
                series_id TEXT PRIMARY KEY, city_id INTEGER NOT NULL, store_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL, category_id INTEGER NOT NULL);
            CREATE TABLE fact_daily_sales (
                series_id TEXT NOT NULL REFERENCES dim_series(series_id), date TEXT NOT NULL,
                sales REAL NOT NULL CHECK(sales>=0),
                stockout_hours INTEGER NOT NULL CHECK(stockout_hours BETWEEN 0 AND 16),
                discount REAL NOT NULL CHECK(discount >= 0),
                holiday_flag INTEGER NOT NULL CHECK(holiday_flag IN (0,1)),
                activity_flag INTEGER NOT NULL CHECK(activity_flag IN (0,1)),
                source_split TEXT NOT NULL CHECK(source_split IN ('train','eval')),
                PRIMARY KEY (series_id,date)) WITHOUT ROWID;
            CREATE VIEW daily_sales AS SELECT f.*,d.city_id,d.store_id,d.product_id,d.category_id
                FROM fact_daily_sales f JOIN dim_series d USING(series_id);
        """)
        daily[DIMENSIONS].drop_duplicates().to_sql(
            "dim_series", connection, if_exists="append", index=False, chunksize=10_000
        )
        daily[FACTS].to_sql(
            "fact_daily_sales", connection, if_exists="append", index=False, chunksize=20_000
        )
        summary.to_sql("series_summary", connection, index=False)
        forecasts.to_sql("forecast_values", connection, index=False)
        scores.to_sql("forecast_scores", connection, index=False)
        pd.DataFrame({"key": list(metadata), "value": [str(v) for v in metadata.values()]}).to_sql(
            "metadata", connection, index=False
        )
        connection.execute("CREATE INDEX idx_fact_date ON fact_daily_sales(date)")
        connection.execute("CREATE INDEX idx_forecast_series ON forecast_values(series_id)")
        connection.execute("CREATE UNIQUE INDEX idx_summary_series ON series_summary(series_id)")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("SQLite foreign key validation failed")
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("SQLite integrity check failed")


def query_file(connection: sqlite3.Connection, path: Path) -> pd.DataFrame:
    return pd.read_sql_query(path.read_text(), connection)
