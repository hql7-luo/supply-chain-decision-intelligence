"""Render recruiter and management documentation directly from saved full-data evidence."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build_reports() -> None:
    evidence = ROOT / "docs/evidence"
    findings = json.loads((evidence / "findings.json").read_text())
    quality = json.loads((evidence / "data_quality.json").read_text())
    manifest = json.loads((evidence / "download_manifest.json").read_text())
    data = findings["data"]
    risks = findings["risk_window"]
    metrics = findings["forecast"]["holdout_metrics"]
    selected = metrics["all_days"]
    baseline_rows = "\n".join(
        f"| {name} | {score['mae']:.4f} | {score['rmse']:.4f} | {score['wape']:.2%} | {score['bias']:+.2%} |"
        for name, score in metrics["baselines"].items()
    )
    best_name, best_score = min(metrics["baselines"].items(), key=lambda item: item[1]["wape"])
    pp_gap = (selected["wape"] - best_score["wape"]) * 100
    eighty = findings["product_concentration"]["products_for_80pct_observed_sales"]
    product_share = findings["product_concentration"]["product_share_for_80pct"]
    zero_share = data["zero_sales_with_stockout"] / data["zero_sales_days"]
    download_date = manifest["retrieved_at_utc"][:10]
    examples = "\n".join(
        f"| {row['series_id']} | {row['stockout_hour_rate']:.1%} | {row['observed_mean_sales']:.3f} | {row['forecast_next7_sales']:.3f} | Investigate availability and verify active assortment |"
        for row in findings["top_priority_examples"][:5]
    )
    (ROOT / "docs/executive_summary.md").write_text(f"""# Management decision brief

**Historical scope:** {data["date_min"]}–{data["date_max"]}; all {data["rows"]:,} observations,
{data["series"]:,} store-product series, {data["stores"]:,} stores and {data["products"]:,} products.
This is a released research dataset, not a view of current company operations.

## What the evidence shows

- **Availability is a widespread review issue.** {data["stockout_day_rate"]:.2%} of store-product-days had at least one unavailable operating hour; {data["stockout_hour_rate"]:.2%} of all operating hours were unavailable. A day-rate and an hour-rate answer different questions.
- **A small product subset dominates observed sales.** {eighty} of {data["products"]} products ({product_share:.2%}) contribute at least 80% of globally normalized sales. This is a sales-concentration measure, not revenue or margin.
- **Zero sales often coincide with unavailability.** {data["zero_sales_with_stockout"]:,} of {data["zero_sales_days"]:,} zero-sales days ({zero_share:.2%}) had stockout exposure. Recorded sales therefore cannot be treated as complete demand.
- **The latest 28-day rules flag {risks["high_priority_series"]:,} series ({risks["high_priority_series_share"]:.2%}) as Critical or High Risk.** They account for {risks["high_priority_recent_sales_share"]:.2%} of recent observed sales. This broad queue needs a capacity limit and local investigation; it does not justify replenishing every flagged item.

## Where to begin

| Store:product | Unavailable hours, recent 28 days | Mean daily observed sales | Next 7-day sales estimate | Management action |
| --- | ---: | ---: | ---: | --- |
{examples}

1. Validate the active assortment and stockout records for the highest exposure series. Distinguish operational shortages from products no longer actively offered; source IDs do not establish the cause.
2. Review high-contribution A items with repeated shortages, using actual stock balances, open orders, measured lead times and shelf life before changing replenishment. Low observed sales during stockouts do not prove low demand.
3. Compare service targets and lead-time disruptions in the scenario tool. Treat its normalized targets as sensitivity outputs; convert them only after the missing physical-unit scale and operational records are obtained.

## Forecasting decision

The pre-specified per-series selector achieves **{selected["wape"]:.2%} pooled holdout WAPE**,
MAE {selected["mae"]:.4f} and bias {selected["bias"]:+.2%} on {selected["n_observations"]:,} observations.
The fixed {best_name} baseline performs better on this holdout: **{best_score["wape"]:.2%} WAPE**,
a {pp_gap:.2f} percentage-point gap. Per-series selection adds flexibility but did not improve
this aggregate benchmark. Keep that negative result visible; evaluate the simpler SES candidate
prospectively before adopting a forecasting policy. The holdout was not used to change model selections.

| Method | MAE | RMSE | Pooled WAPE | Bias |
| --- | ---: | ---: | ---: | ---: |
{baseline_rows}
| Rolling-validation per-series selector | {selected["mae"]:.4f} | {selected["rmse"]:.4f} | {selected["wape"]:.2%} | {selected["bias"]:+.2%} |

The no-stockout holdout diagnostic has {metrics["uncensored_days"]["wape"]:.2%} WAPE; it is a
selection-biased subset, not evidence of recovered lost demand. Three months support weekly
baselines, not annual seasonality. No supplier, purchase-order, excess-stock, inventory-value,
spoilage-cost or realized savings conclusion is possible from these fields.

Source: [Dingdong-Inc / FreshRetailNet-50K](https://huggingface.co/datasets/Dingdong-Inc/FreshRetailNet-50K), CC BY 4.0.
All figures are generated by `scripts/run_pipeline.py`; machine-readable evidence is in `docs/evidence/findings.json`.
""")
    profile_rows = "\n".join(
        f"| {source['file']} | {source['rows']:,} | {source['date_min']}–{source['date_max']} | {sum(source['missing_by_column'].values())} | {source['hourly_sales_sum_mismatches']} | {source['stockout_count_mismatches']} |"
        for source in quality["source_files"]
    )
    (ROOT / "docs/data_quality_report.md").write_text(f"""# Data quality and cleaning report

The original pinned Parquet files were fully audited before publication.
All {quality["rows"]:,} records, all 19 source columns and every 24-element hourly
sales/status array were inspected. The analytical key is `(store_id, product_id, date)`.

| File | Rows | Date coverage | Missing source values | Daily/hourly sales disagreements | Stockout count disagreements |
| --- | ---: | --- | ---: | ---: | ---: |
{profile_rows}

- {quality["series"]:,} complete series, each with 97 consecutive dates; no missing series-days.
- Official train/eval split preserved: 90 train days and 7 later evaluation days for every series.
- {quality["duplicate_primary_keys"]} duplicate primary keys; hence no exact duplicate rows at this grain.
- {quality["products"]} real encoded products, {quality["stores"]} stores, {quality["cities"]} cities, {quality["categories"]} first-category IDs. The source card's 865 products matches the actual files.
- Hourly flags are binary and reconcile exactly over indexes `[6:22]`: 16 one-hour bins, 06:00 through 21:59. Daily and hourly sales sums agree at the configured NumPy tolerances: absolute 1e-6 and relative 1e-5.
- Sales range {quality["sales_quantiles"]["0.0"]:.1f}–{quality["sales_quantiles"]["1.0"]:.1f} on the globally normalized scale. Extreme valid values remain in the data.

## Exception: discount factors above one

**Medium severity for promotion analysis; low impact on this project's core results.**
{quality["discount_above_one"]} original train records have discount factors above 1,
up to {quality["discount_max"]}. No source values were capped, deleted or overwritten.
The publisher describes 1 as no discount; these observations need clarification
before estimating promotion effects. Discount is not an input to forecasts, XYZ,
availability risk or planning targets. Exact examples are saved in the JSON audit.

## Analytical risk: censored sales

**High severity for demand and inventory policy.** Zero sales alone do not establish
no demand or a stockout. Positive hourly stockout flags provide direct availability
evidence; unobserved demand during those hours is unknown. Forecasts target observed
sales. Latest-window all-zero series have undefined CV and Unknown XYZ, with at least
Watch status for assortment/recording review.

## Reproducible transformations

Originals remain byte-for-byte unchanged. The pipeline validates, renames fields,
forms store-product keys, projects a daily model and computes derived outputs.
No records are removed, outliers capped, periods filled, or operational histories
generated. Source data contains encoded business entities, no customer identifiers
or personal information. Optional weather fields are profiled but not modeled.

See [machine-readable audit](evidence/data_quality.json), [download hashes](evidence/download_manifest.json),
[methods](methodology.md), [candidate selection](dataset_selection.md) and [SQL](../sql/).
""")
    (ROOT / "README.md").write_text(f"""# Supply Chain Decision Intelligence

An end-to-end supply-chain analytics project using real public retail data to prioritize availability risk, evaluate sales forecasts and support transparent replenishment planning.

[![Analytics CI](https://github.com/hql7-luo/supply-chain-decision-intelligence/actions/workflows/ci.yml/badge.svg)](https://github.com/hql7-luo/supply-chain-decision-intelligence/actions/workflows/ci.yml)

**Real data:** [FreshRetailNet-50K · Dingdong-Inc](https://huggingface.co/datasets/Dingdong-Inc/FreshRetailNet-50K) · CC BY 4.0 · **4.85M observations / 50,000 store-product series / 865 products**.

![Executive dashboard with actual full-data results](docs/assets/dashboard.png)

## Business value

Which store-product combinations need attention? Where do recurring stockouts make recorded sales an incomplete measure of demand? What inventory target follows from explicit lead-time and service assumptions?

This project connects **Supply Chain + Business Analytics + Information Systems + Decision Support**. It produces a reproducible management queue, forecasts with transparent benchmarks, and an interactive planning tool. It is an independent public-data portfolio project; the data is not from an employer, internship or customer.

## What the real data shows

- **{data["stockout_day_rate"]:.1%} of store-product-days had stockouts**; unavailable hours represent {data["stockout_hour_rate"]:.1%} of operating hours.
- **{eighty} products ({product_share:.1%}) generate at least 80% of normalized sales.** This is sales concentration, not revenue.
- **{zero_share:.1%} of zero-sales days also had stockout exposure.** Observed sales do not reveal all latent demand.
- **{risks["high_priority_series"]:,} series require review under the latest 28-day heuristic.** This broad queue is for investigation, not automatic purchase orders.
- **Forecast honesty:** the rolling-validation per-series selector scores {selected["wape"]:.1%} holdout WAPE; the simpler fixed SES baseline scores {best_score["wape"]:.1%}. Model flexibility did not improve the strongest aggregate baseline. All four baselines and this negative result are reported.

[Management brief](docs/executive_summary.md) · [Data quality](docs/data_quality_report.md) · [Methods](docs/methodology.md) · [Dataset comparison](docs/dataset_selection.md)

## Analytics and dashboard

| Area | What it demonstrates |
| --- | --- |
| Python + data modeling | Full raw audit, immutable originals, store-product-date grain and constrained SQLite star schema |
| Visible SQL | Category availability, monthly sales, product Pareto concentration, recent risk queue and store benchmarks in [sql/](sql/) |
| Demand forecasting | Naive, weekly seasonal naive, 28-day mean and exponential smoothing; three expanding validation folds inside 90 train days, then untouched 7-day holdout |
| Inventory decision support | Real stockout-hour/day metrics; descriptive sales-contribution ABC and observed-sales XYZ; deterministic action/reason table |
| Planning scenarios | Demand shocks, lead-time disruptions, service targets, safety-stock/reorder-point sensitivity and gap to a user-assumed inventory position |
| Streamlit + Plotly | Six tabs, city/category filters, sortable tables, forecast charts, downloadable recommendations and visible scope/assumption notes |
| Testing + reproducibility | Analytical edge cases, leakage safeguards, source validation, SQL reconciliation, app interaction checks and real-demo recomputation |

No supplier table, current stock balance, procurement history, realized savings or LLM is fabricated.

## Try the dashboard

CI is configured for Python **3.11 and 3.12**. Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```bash
git clone https://github.com/hql7-luo/supply-chain-decision-intelligence.git
cd supply-chain-decision-intelligence
uv sync --frozen --python 3.11 --extra dev
uv run streamlit run app/dashboard.py
```

The committed **200-series / 19,400-row real-data demo** starts immediately. It is a deterministic stratified illustration across availability statuses, not a representative population sample. The app labels demo scope and computes its KPIs only on those records.

## Reproduce the full analysis

```bash
uv run python scripts/download_data.py
uv run python scripts/run_pipeline.py
uv run python scripts/build_reports.py
uv run pytest -q
uv run python scripts/verify_demo.py
uv run streamlit run app/dashboard.py
```

The downloader needs no credentials. It fetches the original 106.4 MB train + 8.4 MB eval files from a pinned public revision and verifies SHA-256. For manual download, use the exact URLs in [download_manifest.json](docs/evidence/download_manifest.json), place both files in `data/raw/`, and run the same processing command. Keep roughly 1 GB of free disk space and allow several minutes for the full audit and database build.

The full database takes precedence over the demo. To force a reviewed demo run:

```bash
SCDI_DATABASE=data/demo/decision_intelligence.sqlite uv run streamlit run app/dashboard.py
```

Lint and syntax checks: `uv run ruff check .`, `uv run ruff format --check .`, and `uv run python -m compileall -q src scripts app`. CI also recomputes saved demo forecasts, priorities and all SQL queries, without a network data download.

## Architecture

```mermaid
flowchart LR
  A[Public source + pinned hashes] --> B[Validation and daily model]
  B --> C[SQLite + visible SQL]
  B --> D[Time-validated forecasts]
  C --> E[Availability priorities + actions]
  D --> E
  E --> F[Streamlit dashboard]
  G[Explicit user assumptions] --> H[Inventory target scenarios]
  D --> H
  H --> F
```

```text
app/                  Streamlit decision dashboard
src/scdi/             Validation, SQLite, forecasts, inventory rules, scenarios
sql/                  Five inspectable business queries
scripts/              Download, full pipeline, reports and demo verification
tests/                Meaningful analytical, data, SQL and application checks
notebooks/            Inspectable audit and SQL exploration
docs/                 Management findings, methodology, evidence and screenshot
data/raw/             Original Parquet files, excluded from Git
data/processed/       Full SQLite and analytical CSV outputs, excluded from Git
data/demo/            Small attributed real-data adaptation, committed
```

[Architecture details](docs/architecture.md) · [Audit notebook](notebooks/01_data_audit.ipynb)

## Provenance and limitations

**Dataset:** FreshRetailNet-50K, developed by Dingdong-Inc. Original [dataset card](https://huggingface.co/datasets/Dingdong-Inc/FreshRetailNet-50K) and [research paper](https://arxiv.org/abs/2505.16319). License: [CC BY 4.0](data/LICENSE.md). Downloaded **{download_date} UTC**; pinned revision `{manifest["revision"]}`. Full raw files are not stored on GitHub for size; the attributed real demo and derived evidence are stored.

**Real fields:** dates, globally normalized daily/hourly sales, encoded product/category/store/city IDs, hourly stockout flags, discount, holidays, activities and weather. **Synthetic source fields: none.** Renaming, aggregation, forecasts and classifications are analytical transformations. Lead-time distribution, service target and inventory position are separate, visible scenario assumptions.

The data covers **{data["date_min"]}–{data["date_max"]}**, not current inventory. It contains no on-hand quantity, unit price/cost, supplier, purchase order, shelf life or spoilage cost. Consequently there are no actual inventory values, turnover, EOQ, supplier rankings, realized service levels or executable replenishment orders. All monetary or physical-unit conclusions would need additional data. The normal-approximation planning formula assumes independent stationary demand and lead time; it is particularly limited for perishable/intermittent and stockout-censored demand. Annual seasonality and lost demand are not estimated.

Code is MIT licensed; source and derived data retain their separate CC BY 4.0 attribution. See [data rights](data/LICENSE.md).
""")
    print("Generated README, executive summary and data-quality report from verified evidence")


if __name__ == "__main__":
    build_reports()
