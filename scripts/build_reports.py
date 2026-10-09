"""Render recruiter and management documentation directly from saved full-data evidence."""

from __future__ import annotations

import json
import re
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
    deployment_path = evidence / "deployment.json"
    deployment = json.loads(deployment_path.read_text()) if deployment_path.is_file() else {}
    online_link = (
        f"**[Open the real-data interactive Demo]({deployment['url']})** · "
        "200 series / 19,400 real observations · no installation or sign-in. "
        "This GitHub Pages explorer shows subset trends, priorities and forecasts; "
        "its metrics are separate from the full-data findings below. "
        "[Bilingual case study](https://hql7-luo.github.io/projects/supply-chain-decision-intelligence.html)\n"
        if deployment.get("status") == "verified_public"
        else ""
    )
    online_details = (
        f"The verified [online Demo]({deployment['url']}) is a public static Plotly explorer "
        "on GitHub Pages. The complete **six-tab Streamlit app**, including planning scenarios, "
        "runs locally with the same real demo database. See "
        "[deployment scope and platform assessment](docs/online_demo.md)."
        if deployment.get("status") == "verified_public"
        else "The complete six-tab Streamlit app runs locally with the real demo database."
    )
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

## Original exposure-order examples

These are the first five original severity-priority examples, not a highest-sales
or optimal-replenishment list. For the two management investigation purposes,
see the [editorial management brief](management_brief.md).

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
    technical_report = f"""# Generated technical analysis

This report is regenerated from the saved machine-readable evidence. The
[business overview](../README.md) and [management brief](management_brief.md)
are maintained separately; rebuilding this report does not overwrite them.

An end-to-end supply-chain analytics project using real public retail data to prioritize availability risk, evaluate sales forecasts and support transparent replenishment planning.

[![Analytics CI](https://github.com/hql7-luo/supply-chain-decision-intelligence/actions/workflows/ci.yml/badge.svg)](https://github.com/hql7-luo/supply-chain-decision-intelligence/actions/workflows/ci.yml)

**Real data:** [FreshRetailNet-50K · Dingdong-Inc](https://huggingface.co/datasets/Dingdong-Inc/FreshRetailNet-50K) · CC BY 4.0 · **4.85M observations / 50,000 store-product series / 865 products**.

{online_link}
## The project in 30 seconds

**Question:** which store-product series need availability review, and which observed-sales forecast is a credible planning baseline?

| Evidence from the full dataset | Business recommendation |
| --- | --- |
| **{data["stockout_day_rate"]:.1%} of daily records had stockouts**; {data["stockout_hour_rate"]:.1%} of operating hours were unavailable | Investigate repeated exposure before treating low recorded sales as low demand |
| **{eighty} / {data["products"]} products ({product_share:.1%}) contribute ≥80% of observed sales** | Focus review capacity on high-contribution products with recurring availability issues |
| **SES: {best_score["wape"]:.1%} WAPE · per-series selection: {selected["wape"]:.1%}** | Keep the stronger simple baseline visible; validate prospectively before adopting a model policy |

Scope: **97 historical days, {data["date_min"]}–{data["date_max"]}**. Sales use a globally normalized scale, not physical units or revenue. This independent public-data project does not claim realized commercial savings.

### 1. Historical Demand & Stockout Trends

![97-day full-data observed sales and unavailable operating-hour trends](docs/assets/historical-demand-stockouts.png)

The aligned panels separate **recorded sales** from **availability exposure** across all 50,000 series. They show timing, not a causal estimate of lost sales. Review stockout patterns alongside demand before changing replenishment.

### 2. ABC / Pareto Analysis

![All 865 product IDs ranked by observed sales with cumulative contribution](docs/assets/product-pareto.png)

**{eighty} products reach 80% of full-period observed sales.** Use concentration to focus investigation; this descriptive ABC adaptation measures normalized sales contribution, not revenue, margin or inventory value.

### 3. Forecast Model Comparison

![Untouched seven-day pooled WAPE for four fixed baselines and per-series selection](docs/assets/forecast-comparison.png)

All five methods use the same **June 26–July 2 holdout / 350,000 observations**. The selector was chosen using three earlier rolling validation folds. Fixed SES performs **{pp_gap:.2f} percentage points better** on this holdout; the negative result is retained. Forecasts target observed sales, not recovered demand.

[Original exposure-order examples and benchmark](docs/executive_summary.md) · [Data quality](docs/data_quality_report.md) · [Methods](docs/methodology.md) · [Dataset comparison](docs/dataset_selection.md)

## Visualization Gallery

### Stockout Risk Matrix

![Recent sales contribution and stockout operating-hour exposure for all 50000 series](docs/assets/stockout-risk-matrix.png)

**{risks["high_priority_series"]:,} series ({risks["high_priority_series_share"]:.1%}) are Critical or High Risk** under unchanged latest-28-day rules. They represent {risks["high_priority_recent_sales_share"]:.1%} of recent observed sales. Both axes use **June 5–July 2**; the matrix relates contribution to exposure. Dashboard Top 20 / Top 50 views make this broad review queue manageable, with selectable sales/exposure sorting. They do not authorize automatic orders.

### Availability & Zero-Sales Analysis

![Zero-sales frequency by stockout exposure and zero-sales-day composition](docs/assets/availability-zero-sales.png)

**{data["zero_sales_with_stockout"]:,} / {data["zero_sales_days"]:,} zero-sales days ({zero_share:.1%}) also had stockout exposure.** Zero sales alone are not proof of no demand. Group rates use each group's own denominator; coexistence does not establish the cause or amount of lost demand.

All five charts are generated from the full SQLite analysis and reconciled with saved evidence. [Chart data and checks](docs/evidence/visualizations.json) · [Generator](scripts/build_visualizations.py). No hand-entered chart values.

## Dashboard experience

![Actual full-data Streamlit executive dashboard](docs/assets/dashboard.png)

Six existing tabs retain demand, risk, forecasts, scenario planning and source-quality checks. Review **Top 20 / Top 50**, filter status, sort by business contribution or exposure, inspect a series' action and reason, compare actuals with scored predictions, and download chart HTML / CSV data / PNG. City and category filters retain the original analytical definitions.

## Analytics and dashboard

| Area | What it demonstrates |
| --- | --- |
| Python + data modeling | Full raw audit, immutable originals, store-product-date grain and constrained SQLite star schema |
| Visible SQL | Category availability, monthly sales, product Pareto concentration, recent risk queue and store benchmarks in [sql/](sql/) |
| Demand forecasting | Naive, weekly seasonal naive, 28-day mean and exponential smoothing; three expanding validation folds inside 90 train days, then untouched 7-day holdout |
| Inventory decision support | Real stockout-hour/day metrics; descriptive sales-contribution ABC and observed-sales XYZ; deterministic action/reason table |
| Planning scenarios | Demand shocks, lead-time disruptions, service targets, safety-stock/reorder-point sensitivity and gap to a user-assumed inventory position |
| Streamlit + Plotly | Six tabs, scoped KPIs, aligned sales/stockout trends, Top 20/50 priorities, scored forecast detail and chart/data downloads |
| Testing + reproducibility | Analytical edge cases, leakage safeguards, source validation, SQL reconciliation, app interaction checks and real-demo recomputation |

No supplier table, current stock balance, procurement history, realized savings or LLM is fabricated.

## Try the dashboard

{online_details}

CI is configured for Python **3.11 and 3.12**. Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```bash
git clone https://github.com/hql7-luo/supply-chain-decision-intelligence.git
cd supply-chain-decision-intelligence
uv sync --frozen --python 3.11 --extra dev --extra viz
uv run streamlit run app/dashboard.py
```

The committed **200-series / 19,400-row real-data demo** starts immediately. It is a deterministic stratified illustration across availability statuses, not a representative population sample. The app labels demo scope and computes its KPIs only on those records.

## Reproduce the full analysis

```bash
uv run python scripts/download_data.py
uv run python scripts/run_pipeline.py
uv run python scripts/build_reports.py
uv run --extra viz python scripts/build_visualizations.py
uv run pytest -q
uv run python scripts/verify_demo.py
uv run streamlit run app/dashboard.py
```

The downloader needs no credentials. It fetches the original 106.4 MB train + 8.4 MB eval files from a pinned public revision and verifies SHA-256. For manual download, use the exact URLs in [download_manifest.json](docs/evidence/download_manifest.json), place both files in `data/raw/`, and run the same processing command. Keep roughly 1 GB of free disk space and allow several minutes for the full audit and database build.

The full database takes precedence over the demo. To force a reviewed demo run:

```bash
SCDI_DATABASE=data/demo/decision_intelligence.sqlite uv run streamlit run app/dashboard.py
```

To rebuild the credential-free static explorer from the same real 200-series cohort: `uv run python scripts/build_web_demo.py --output /path/to/static/site/demos/supply-chain`. It provides trends, priorities and actual-versus-forecast inspection; the six-tab Streamlit app also includes interactive planning scenarios.

Lint and syntax checks: `uv run ruff check .`, `uv run ruff format --check .`, and `uv run python -m compileall -q src scripts app`. CI also recomputes saved demo forecasts, priorities and all SQL queries, without a network data download. Chart rebuilding additionally requires the `viz` extra and the full processed database.

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
"""
    # This report lives one directory below the editorial README. Adjust only
    # repository-relative Markdown links; evidence values and prose stay intact.
    technical_report = re.sub(
        r"(?<=\]\()(docs|sql|scripts|notebooks|data)/",
        lambda match: "" if match.group(1) == "docs" else f"../{match.group(1)}/",
        technical_report,
    )
    (ROOT / "docs/generated_analysis.md").write_text(technical_report)
    print(
        "Generated technical analysis, executive summary and data-quality report from verified evidence"
    )


if __name__ == "__main__":
    build_reports()
