"""Audit all pinned observations, create SQLite, forecast, and export decision evidence."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from pathlib import Path

import pandas as pd

from scdi.data import load_and_audit
from scdi.database import query_file, write_database
from scdi.forecasting import forecast_metrics, forecast_sales
from scdi.inventory import summarize_inventory

ROOT = Path(__file__).resolve().parents[1]


def save_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def select_demo(summary: pd.DataFrame, size: int = 200) -> list[str]:
    """Deterministic stratified illustration; never used to estimate population rates."""
    chosen = []
    for risk in ["Critical", "High Risk", "Watch", "Healthy"]:
        group = summary.loc[summary.availability_risk.eq(risk)].sort_values("series_id")
        if len(group):
            step = max(1, len(group) // (size // 4))
            chosen.extend(group.iloc[::step].head(size // 4).series_id.tolist())
    remainder = summary.loc[~summary.series_id.isin(chosen)].sort_values("series_id")
    chosen.extend(remainder.head(size - len(chosen)).series_id.tolist())
    return sorted(chosen)


def build_metadata(daily, summary, holdout, scope):
    metrics = forecast_metrics(holdout.actual, holdout.prediction)
    return {
        "scope": scope,
        "dataset": "FreshRetailNet-50K",
        "rows": len(daily),
        "source_url": "https://huggingface.co/datasets/Dingdong-Inc/FreshRetailNet-50K",
        "series": len(summary),
        "stores": daily.store_id.nunique(),
        "products": daily.product_id.nunique(),
        "date_min": daily.date.min(),
        "date_max": daily.date.max(),
        "exposure_hours": 16,
        "holdout_wape": metrics["wape"],
        "holdout_mae": metrics["mae"],
        "holdout_bias": metrics["bias"],
        "risk_window_days": 28,
        "source_revision": "08c1fab7f9257bc73679d415d65d644165d351d4",
    }


def run(raw: Path, output: Path, evidence: Path, build_demo: bool = True) -> dict:
    print("Auditing every original row and hourly annotation", flush=True)
    daily, quality = load_and_audit(raw)
    save_json(evidence / "data_quality.json", quality)
    if (raw / "download_manifest.json").exists():
        shutil.copyfile(raw / "download_manifest.json", evidence / "download_manifest.json")
    print(f"Verified {len(daily):,} records; fitting four interpretable baselines", flush=True)
    forecast = forecast_sales(daily)
    summary = summarize_inventory(daily)
    summary = summary.merge(forecast.selections, on="series_id", validate="one_to_one")
    future = (
        forecast.future_predictions.groupby("series_id")
        .prediction.agg(["sum", "mean"])
        .rename(columns={"sum": "forecast_next7_sales", "mean": "forecast_daily_sales"})
        .reset_index()
    )
    summary = summary.merge(future, on="series_id", validate="one_to_one")
    scores = forecast.holdout_by_series.merge(
        forecast.selections[["series_id", "validation_mae"]], on="series_id"
    )
    values = pd.concat(
        [
            forecast.holdout_predictions.assign(split="holdout"),
            forecast.future_predictions.assign(
                split="future", actual=float("nan"), stockout_hours=float("nan")
            ),
        ],
        ignore_index=True,
    )
    output.mkdir(parents=True, exist_ok=True)
    summary.to_csv(output / "management_recommendations.csv", index=False)
    forecast.validation.to_csv(output / "forecast_validation.csv", index=False)
    db_path = output / "decision_intelligence.sqlite"
    print("Building constrained SQLite star schema and business SQL outputs", flush=True)
    write_database(
        db_path,
        daily,
        summary,
        values,
        scores,
        build_metadata(daily, summary, forecast.holdout_predictions, "full"),
    )
    query_outputs = {}
    with sqlite3.connect(db_path) as connection:
        for sql in sorted((ROOT / "sql").glob("*.sql")):
            result = query_file(connection, sql)
            result.to_csv(output / f"{sql.stem}.csv", index=False)
            query_outputs[sql.stem] = result
    product = query_outputs["03_product_concentration"]
    eighty = int(product.cumulative_share.lt(0.8).sum() + 1)
    risk_counts = {str(k): int(v) for k, v in summary.availability_risk.value_counts().items()}
    recent_sales = float(summary.recent_sales_total.sum())
    critical_high = summary[summary.availability_risk.isin(["Critical", "High Risk"])]
    findings = {
        "scope": "full dataset; all 50,000 store-product series",
        "data": {
            k: quality[k]
            for k in [
                "rows",
                "series",
                "stores",
                "products",
                "cities",
                "categories",
                "date_min",
                "date_max",
                "days_per_series",
                "stockout_days",
                "stockout_day_rate",
                "stockout_hour_rate",
                "zero_sales_days",
                "zero_sales_with_stockout",
            ]
        },
        "risk_window": {
            "start": summary.window_start.iloc[0],
            "end": summary.window_end.iloc[0],
            "days": 28,
            "counts": risk_counts,
            "high_priority_series": len(critical_high),
            "high_priority_series_share": len(critical_high) / len(summary),
            "high_priority_recent_sales_share": float(
                critical_high.recent_sales_total.sum() / recent_sales if recent_sales > 0 else 0.0
            ),
        },
        "product_concentration": {
            "products_for_80pct_observed_sales": eighty,
            "product_share_for_80pct": eighty / len(product),
        },
        "forecast": {
            "protocol": forecast.protocol,
            "holdout_metrics": forecast.holdout_metrics,
            "model_selection_counts": {
                str(k): int(v) for k, v in summary.selected_model.value_counts().items()
            },
        },
        "top_priority_examples": summary.head(10)
        .astype(object)
        .where(pd.notna(summary.head(10)), None)
        .to_dict(orient="records"),
        "category_availability": query_outputs["01_category_availability"].to_dict(
            orient="records"
        ),
        "synthetic_source_fields": [],
        "planning_assumptions": "Interactive only; no fabricated operational records",
    }
    save_json(evidence / "findings.json", findings)
    if build_demo:
        chosen = select_demo(summary)
        demo_daily = daily[daily.series_id.isin(chosen)]
        # Recalculate classifications within the demo scope; preserve full-scope risk rules.
        demo_summary = (
            summarize_inventory(demo_daily)
            .merge(forecast.selections, on="series_id")
            .merge(future, on="series_id")
        )
        demo_values = values[values.series_id.isin(chosen)]
        demo_holdout = forecast.holdout_predictions[
            forecast.holdout_predictions.series_id.isin(chosen)
        ]
        demo_scores = scores[scores.series_id.isin(chosen)]
        demo_path = ROOT / "data/demo/decision_intelligence.sqlite"
        write_database(
            demo_path,
            demo_daily,
            demo_summary,
            demo_values,
            demo_scores,
            build_metadata(demo_daily, demo_summary, demo_holdout, "demo"),
        )
        save_json(
            ROOT / "data/demo/manifest.json",
            {
                "scope": "deterministic stratified illustration, not representative",
                "selection_rule": "Up to 50 equally spaced sorted series IDs per availability status; fill to 200 by ID",
                "series_ids": chosen,
                "rows": len(demo_daily),
                "source_revision": "08c1fab7f9257bc73679d415d65d644165d351d4",
                "adaptation": "Original sales/stockout values unchanged; projections, forecasts, and rules added",
            },
        )
    print(f"Complete: {db_path}\nHigh priority series: {len(critical_high):,}", flush=True)
    return findings


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=ROOT / "data/raw")
    parser.add_argument("--output", type=Path, default=ROOT / "data/processed")
    parser.add_argument("--evidence", type=Path, default=ROOT / "docs/evidence")
    parser.add_argument("--no-demo", action="store_true")
    args = parser.parse_args()
    run(args.raw, args.output, args.evidence, not args.no_demo)
