"""Export only the verified 200-series SQLite demo to a credential-free static explorer."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

import pandas as pd
import plotly
from plotly.offline import get_plotlyjs

ROOT = Path(__file__).resolve().parents[1]


def build_demo(destination: Path) -> dict:
    database = ROOT / "data/demo/decision_intelligence.sqlite"
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        metadata = dict(connection.execute("SELECT key,value FROM metadata"))
        if metadata.get("scope") != "demo":
            raise ValueError("Only the explicitly scoped real-data demo can be published here")
        summary = pd.read_sql_query(
            "SELECT * FROM series_summary ORDER BY priority_rank", connection
        )
        daily = pd.read_sql_query(
            "SELECT series_id,date,sales,stockout_hours FROM daily_sales ORDER BY series_id,date",
            connection,
        )
        forecast = pd.read_sql_query(
            "SELECT series_id,date,actual,prediction,split FROM forecast_values ORDER BY series_id,date",
            connection,
        )
    manifest = json.loads((ROOT / "data/demo/manifest.json").read_text())
    if len(summary) != 200 or len(daily) != 19400:
        raise ValueError("The published explorer contract requires 200 series and 19,400 real rows")
    if set(summary.series_id) != set(manifest["series_ids"]):
        raise ValueError("Demo cohort differs from the reviewed source-data manifest")
    dates = sorted(daily.date.unique().tolist())
    if len(dates) != 97 or not daily.groupby("series_id").size().eq(97).all():
        raise ValueError("Incomplete historical coverage")
    holdout = forecast.loc[forecast.split == "holdout"]
    wape = float((holdout.prediction - holdout.actual).abs().sum() / holdout.actual.abs().sum())
    trend = daily.groupby("date").agg(sales=("sales", "sum"), hours=("stockout_hours", "sum"))
    recent_total = float(summary.recent_sales_total.sum())
    items = []
    for row in summary.to_dict("records"):
        history = daily.loc[daily.series_id == row["series_id"]]
        predictions = forecast.loc[forecast.series_id == row["series_id"]]
        row["recent_sales_share"] = float(row["recent_sales_total"] / recent_total)
        row["history"] = history[["sales", "stockout_hours"]].to_numpy().tolist()
        values = predictions[["date", "actual", "prediction", "split"]].astype(object)
        row["forecasts"] = values.where(pd.notna(values), None).to_numpy().tolist()
        items.append(row)
    payload = {
        "scope": "demo",
        "rows": len(daily),
        "series_count": len(summary),
        "dates": dates,
        "source_revision": manifest["source_revision"],
        "selection_rule": manifest["selection_rule"],
        "kpis": {
            "stockout_day_rate": float(daily.stockout_hours.gt(0).mean()),
            "stockout_hour_rate": float(daily.stockout_hours.sum() / (len(daily) * 16)),
            "wape": wape,
            "review_series": int(summary.availability_risk.isin(["Critical", "High Risk"]).sum()),
        },
        "trend": {
            "sales": trend.sales.tolist(),
            "exposure": (trend.hours / (len(summary) * 16)).tolist(),
        },
        "items": items,
    }
    # JSON round-trip normalizes nullable values and rejects non-finite scalar data.
    text = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    destination.mkdir(parents=True, exist_ok=True)
    for filename in ["index.html", "demo.js", "demo.css"]:
        shutil.copyfile(ROOT / "app/web" / filename, destination / filename)
    (destination / "data.json").write_text(text)
    (destination / "plotly.min.js").write_text(get_plotlyjs())
    build = {
        "scope": "demo",
        "rows": len(daily),
        "series": len(summary),
        "days": len(dates),
        "source_revision": manifest["source_revision"],
        "database_sha256": hashlib.sha256(database.read_bytes()).hexdigest(),
        "data_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "plotly_python_version": plotly.__version__,
        "kpis": payload["kpis"],
    }
    (destination / "manifest.json").write_text(json.dumps(build, indent=2) + "\n")
    return build


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/demo")
    print(json.dumps(build_demo(parser.parse_args().output), indent=2))
