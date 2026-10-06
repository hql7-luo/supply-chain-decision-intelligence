"""Audit original records before projecting a smaller analytical schema."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

SOURCE_SHA256 = {
    "train.parquet": "6706832db892bbae4969c19d87e07975d2543d2ba7d7d4756360654785de5a3d",
    "eval.parquet": "1b118840664280c6b88bffc84c80ee1f54c05d911e354b7599e5da10995e960e",
}


def verify_source_file(path: Path) -> None:
    """Enforce pinned provenance for automated and manual downloads alike."""
    if path.name not in SOURCE_SHA256:
        raise ValueError(f"Unexpected source filename: {path.name}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != SOURCE_SHA256[path.name]:
        raise ValueError(f"SHA-256 mismatch for {path.name}; obtain the documented pinned source")


SOURCE_COLUMNS = [
    "city_id",
    "store_id",
    "management_group_id",
    "first_category_id",
    "second_category_id",
    "third_category_id",
    "product_id",
    "dt",
    "sale_amount",
    "hours_sale",
    "stock_hour6_22_cnt",
    "hours_stock_status",
    "discount",
    "holiday_flag",
    "activity_flag",
    "precpt",
    "avg_temperature",
    "avg_humidity",
    "avg_wind_level",
]
SCALARS = [
    "city_id",
    "store_id",
    "first_category_id",
    "product_id",
    "dt",
    "sale_amount",
    "stock_hour6_22_cnt",
    "discount",
    "holiday_flag",
    "activity_flag",
]


def validate_daily(daily: pd.DataFrame) -> None:
    required = {
        "series_id",
        "date",
        "sales",
        "stockout_hours",
        "store_id",
        "product_id",
        "city_id",
        "category_id",
    }
    missing = required - set(daily.columns)
    if missing:
        raise ValueError(f"Missing analytical fields: {sorted(missing)}")
    if daily[list(required)].isna().any().any():
        raise ValueError("Required analytical fields contain missing values")
    if daily["series_id"].astype(str).str.strip().eq("").any():
        raise ValueError("Missing store-product identifier")
    if pd.to_datetime(daily.date, format="%Y-%m-%d", errors="coerce").isna().any():
        raise ValueError("Invalid date; expected YYYY-MM-DD")
    if daily.duplicated(["series_id", "date"]).any():
        raise ValueError("Duplicate store-product-date primary key; records require investigation")
    for field in ["sales", "stockout_hours"]:
        values = pd.to_numeric(daily[field], errors="coerce").to_numpy()
        if not np.isfinite(values).all() or (values < 0).any():
            raise ValueError(f"{field} must be finite and nonnegative")
    hours = daily.stockout_hours.to_numpy()
    if (hours > 16).any() or (hours != np.floor(hours)).any():
        raise ValueError("stockout_hours must be an integer from 0 to 16")
    for field in ["city_id", "store_id", "product_id", "category_id"]:
        values = pd.to_numeric(daily[field], errors="coerce").to_numpy()
        if (
            not np.isfinite(values).all()
            or (values < 0).any()
            or (values != np.floor(values)).any()
        ):
            raise ValueError(f"{field} must be a nonnegative integer")
    dims = daily.groupby("series_id")[
        ["city_id", "store_id", "product_id", "category_id"]
    ].nunique()
    if dims.gt(1).any().any():
        raise ValueError("Store-product dimension changes within history")


def load_and_audit(raw: Path) -> tuple[pd.DataFrame, dict]:
    profiles, frames = [], []
    for name, expected_rows in [("train.parquet", 4_500_000), ("eval.parquet", 350_000)]:
        verify_source_file(raw / name)
        file = pq.ParquetFile(raw / name)
        if file.schema_arrow.names != SOURCE_COLUMNS:
            raise ValueError(f"Source schema drift in {name}")
        if file.metadata.num_rows != expected_rows:
            raise ValueError(f"Unexpected source row count in {name}")
        nulls = {field: 0 for field in SOURCE_COLUMNS}
        hourly_sum_mismatches = 0
        stock_count_mismatches = 0
        invalid_arrays = 0
        for batch in file.iter_batches(batch_size=100_000):
            for field in SOURCE_COLUMNS:
                nulls[field] += batch.column(field).null_count
            hourly = batch.column("hours_sale").to_pylist()
            status = batch.column("hours_stock_status").to_pylist()
            if any(x is None or len(x) != 24 for x in hourly + status):
                raise ValueError(f"Invalid hourly array length in {name}")
            h = np.asarray(hourly, dtype=float)
            s = np.asarray(status, dtype=float)
            invalid_arrays += int((~np.isfinite(h) | (h < 0)).sum())
            invalid_arrays += int((~np.isfinite(s) | ~np.isin(s, [0, 1])).sum())
            actual = batch.column("sale_amount").to_numpy()
            counts = batch.column("stock_hour6_22_cnt").to_numpy()
            hourly_sum_mismatches += int((~np.isclose(h.sum(axis=1), actual, atol=1e-6)).sum())
            stock_count_mismatches += int((s[:, 6:22].sum(axis=1) != counts).sum())
        if invalid_arrays or stock_count_mismatches:
            raise ValueError(f"Invalid source hourly values/count reconciliation in {name}")
        scalar = pd.read_parquet(raw / name, columns=SCALARS).rename(
            columns={
                "dt": "date",
                "sale_amount": "sales",
                "stock_hour6_22_cnt": "stockout_hours",
                "first_category_id": "category_id",
            }
        )
        scalar["series_id"] = scalar.store_id.astype(str) + ":" + scalar.product_id.astype(str)
        scalar["source_split"] = name.split(".")[0]
        frames.append(scalar)
        profiles.append(
            {
                "file": name,
                "rows": len(scalar),
                "columns": len(SOURCE_COLUMNS),
                "source_types": {f.name: str(f.type) for f in file.schema_arrow},
                "missing_by_column": nulls,
                "date_min": scalar.date.min(),
                "date_max": scalar.date.max(),
                "hourly_sales_sum_mismatches": hourly_sum_mismatches,
                "stockout_count_mismatches": stock_count_mismatches,
                "invalid_hourly_values": invalid_arrays,
            }
        )
    daily = pd.concat(frames, ignore_index=True)
    validate_daily(daily)
    if not np.isfinite(daily.discount).all() or daily.discount.lt(0).any():
        raise ValueError("Source discount must be finite and nonnegative")
    # The source contains 34 factors above 1. Retain them; this unused covariate
    # does not establish a valid promotional percentage or a causal effect.
    unusual_discount = daily.discount.gt(1)
    for field in ["holiday_flag", "activity_flag"]:
        if not daily[field].isin([0, 1]).all():
            raise ValueError(f"Invalid binary source field: {field}")
    periods = daily.groupby("series_id").date.nunique()
    dates = sorted(daily.date.unique())
    calendar = pd.date_range(dates[0], dates[-1]).strftime("%Y-%m-%d").tolist()
    if dates != calendar or not periods.eq(len(calendar)).all():
        raise ValueError(
            "Incomplete series/date coverage; missing dates are not assumed zero sales"
        )
    split_counts = daily.groupby(["series_id", "source_split"]).size().unstack(fill_value=0)
    if not split_counts["train"].eq(90).all() or not split_counts["eval"].eq(7).all():
        raise ValueError(
            "Each series must preserve the official 90-day train / 7-day evaluation split"
        )
    train_dates = sorted(daily.loc[daily.source_split.eq("train"), "date"].unique())
    eval_dates = sorted(daily.loc[daily.source_split.eq("eval"), "date"].unique())
    if train_dates != dates[:90] or eval_dates != dates[90:]:
        raise ValueError("Official train/eval dates do not match chronological validation boundary")
    report = {
        "source_files": profiles,
        "rows": len(daily),
        "source_columns": 19,
        "analytical_columns": list(daily.columns),
        "series": int(daily.series_id.nunique()),
        "stores": int(daily.store_id.nunique()),
        "products": int(daily.product_id.nunique()),
        "cities": int(daily.city_id.nunique()),
        "categories": int(daily.category_id.nunique()),
        "date_min": dates[0],
        "date_max": dates[-1],
        "days_per_series": len(calendar),
        "duplicate_primary_keys": 0,
        "missing_series_days": 0,
        "zero_sales_days": int(daily.sales.eq(0).sum()),
        "zero_sales_with_stockout": int((daily.sales.eq(0) & daily.stockout_hours.gt(0)).sum()),
        "stockout_days": int(daily.stockout_hours.gt(0).sum()),
        "stockout_day_rate": float(daily.stockout_hours.gt(0).mean()),
        "stockout_hour_rate": float(daily.stockout_hours.mean() / 16),
        "sales_quantiles": {
            str(k): float(v) for k, v in daily.sales.quantile([0, 0.5, 0.9, 0.99, 1]).items()
        },
        "exposure_hours": 16,
        "discount_above_one": int(unusual_discount.sum()),
        "discount_max": float(daily.discount.max()),
        "discount_anomaly_examples": daily.loc[unusual_discount, ["series_id", "date", "discount"]]
        .head(10)
        .to_dict(orient="records"),
        "cleaning": [
            "Source originals unchanged; no rows removed, imputed, or capped.",
            "Store/product codes preserved; category labels remain encoded IDs.",
            "Hourly flags reconciled; sales-array sum disagreements counted, never overwritten.",
            "No customer or personal identifiers are present in source schema.",
            "Discount factors above 1 retained and reported; discount is not used by forecast or risk rules.",
        ],
    }
    return daily, report
