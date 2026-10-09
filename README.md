# Supply Chain Decision Intelligence

[English](README.md) · [中文](README.zh-CN.md)

Retailers can miss sales opportunities when products are unavailable, but recorded sales alone do not show which products need attention. I led an AI-assisted analysis of real retail history to focus stockout investigations and compare sales forecasts.

**My role:** business requirements and final-output review; AI assisted implementation.

**[Try the real-data Demo](https://hql7-luo.github.io/demos/supply-chain/)** · 200 real series / 19,400 observations · no sign-in. [Management brief](docs/management_brief.md) · [Bilingual case study](https://hql7-luo.github.io/projects/supply-chain-decision-intelligence.html)

![From retail data to management action: real observations, saved findings, complementary investigation views and operational checks](docs/assets/management-action-overview.png)

The overview summarizes **full-data evidence** and suggested investigation steps. The public Demo is a separate 200-series illustration. [Figure sources and scope](docs/evidence/management-action-overview.json)

## What the evidence changes

**Why it is useful:** managers can narrow a broad availability problem into a manageable investigation, see why an item was selected, and keep a simple forecast benchmark visible before changing planning decisions.

| Evidence from the full dataset | Business recommendation |
| --- | --- |
| **40,591 series (81.2%) are Critical / High Risk** in the latest 28 days | Choose a limited investigation workload; a flag does not authorize an order |
| **122 / 865 products (14.1%) contribute ≥80% of observed sales** | Focus review capacity on high-contribution products with recurring availability issues |
| **SES: 36.0% forecast error · per-series selection: 37.4%** | Keep the stronger simple baseline visible; lower WAPE is better, and adoption still needs new-period validation |

**Data scope:** [Dingdong-Inc / FreshRetailNet-50K](https://huggingface.co/datasets/Dingdong-Inc/FreshRetailNet-50K), CC BY 4.0; **4.85M observations / 50,000 store–product series / 865 products / 97 days**, March 28–July 2, 2024. Sales are globally normalized, not physical units or revenue. The availability window is June 5–July 2; all forecast comparisons share the June 26–July 2 holdout.

**My contribution:** I led this personal, AI-assisted project, defined the inventory-risk, forecasting and management-report requirements, and reviewed the final outputs. AI assisted the data processing, forecast analysis, dashboard implementation and engineering tests.

**Skills demonstrated:** business problem framing, analytical evidence review, forecasting and inventory-risk concepts, and management communication. The implementation uses Python, SQL and Streamlit.

## Two management investigation purposes

1. **Availability investigation:** keep Critical / High Risk and use the **original severity priority**. Start with the most severe recorded exposure, then verify active assortment, recording and operating causes. Suggested owner: store operations, with replenishment planning.
2. **A-tier sales-contribution review:** inspect Critical / High Risk items using the **existing sales sort** and their saved store–product A tier. An A-only worklist filters that saved class and uses the existing 97-day sales order. Suggested owner: replenishment planning, with store operations. Prices, margins, real stock, open orders, lead times and shelf life are needed before turning this investigation into a replenishment decision.

Top 20 / Top 50 expresses review capacity. Both purposes retain the original risk labels and ranks. The A-only filter is a documented worklist definition using existing fields; it is not a new static Demo control, optimization score or automatically improved policy. [Finding → why → owner/action → needed inputs](docs/management_brief.md)

**Try the existing view switch:** in the online Demo, keep **Critical + High Risk**, choose **Top 20 / Top 50**, and compare **Pipeline priority** with **Recent observed sales**. Click Review for the item's evidence and forecast. The Demo sales sort uses 28 days; local Streamlit's **Highest observed sales** uses all 97 days and shows the saved ABC column. Demo metrics and ABC belong to its 200-series cohort. [Exact view definitions and scoped comparison](docs/management_brief.md#two-complementary-investigation-views)

## Detailed analytical evidence

<details>
<summary>Open the five original analysis charts and the full-data dashboard screenshot</summary>

### 1. Historical Demand & Stockout Trends

![97-day full-data observed sales and unavailable operating-hour trends](docs/assets/historical-demand-stockouts.png)

The aligned panels separate **recorded sales** from **availability exposure** across all 50,000 series. They show timing, not a causal estimate of lost sales. Review stockout patterns alongside demand before changing replenishment.

### 2. ABC / Pareto Analysis

![All 865 product IDs ranked by observed sales with cumulative contribution](docs/assets/product-pareto.png)

**122 products reach 80% of full-period observed sales.** Use concentration to focus investigation; this descriptive ABC adaptation measures normalized sales contribution, not revenue, margin or inventory value.

### 3. Forecast Model Comparison

![Untouched seven-day pooled WAPE for four fixed baselines and per-series selection](docs/assets/forecast-comparison.png)

All five methods use the same **June 26–July 2 holdout / 350,000 observations**. The selector was chosen using three earlier rolling validation folds. Fixed SES performs **1.42 percentage points better** on this holdout; the negative result is retained. Forecasts target observed sales, not recovered demand.

[Original exposure-order examples and benchmark](docs/executive_summary.md) · [Data quality](docs/data_quality_report.md) · [Methods](docs/methodology.md) · [Dataset comparison](docs/dataset_selection.md)

## Visualization Gallery

### Stockout Risk Matrix

![Recent sales contribution and stockout operating-hour exposure for all 50000 series](docs/assets/stockout-risk-matrix.png)

**40,591 series (81.2%) are Critical or High Risk** under unchanged latest-28-day rules. They represent 75.8% of recent observed sales. Both axes use **June 5–July 2**; the matrix relates contribution to exposure. Highlighted original Top 20 items are severity-priority examples, not the highest-sales list. Existing sales/exposure sorting provides complementary investigation views; it does not authorize automatic orders.

### Availability & Zero-Sales Analysis

![Zero-sales frequency by stockout exposure and zero-sales-day composition](docs/assets/availability-zero-sales.png)

**164,587 / 215,323 zero-sales days (76.4%) also had stockout exposure.** Zero sales alone are not proof of no demand. Group rates use each group's own denominator; coexistence does not establish the cause or amount of lost demand.

All five charts are generated from the full SQLite analysis and reconciled with saved evidence. [Chart data and checks](docs/evidence/visualizations.json) · [Generator](scripts/build_visualizations.py). No hand-entered chart values.

## Dashboard experience

![Actual full-data Streamlit executive dashboard](docs/assets/dashboard.png)

Six existing tabs retain demand, risk, forecasts, scenario planning and source-quality checks. Review **Top 20 / Top 50**, filter status, compare original priority with observed-sales/exposure sorting, inspect a series' action and reason, compare actuals with scored predictions, and download chart HTML / CSV data / PNG. City and category filters retain the original analytical definitions. This saved screenshot shows the full-data overview, not a new operational deployment.

</details>

## Analytics and dashboard

[![Analytics CI](https://github.com/hql7-luo/supply-chain-decision-intelligence/actions/workflows/ci.yml/badge.svg)](https://github.com/hql7-luo/supply-chain-decision-intelligence/actions/workflows/ci.yml)

[Generated technical analysis](docs/generated_analysis.md) contains the machine-evidence report and original chart explanations. This business README and the [management brief](docs/management_brief.md) are maintained separately; rebuilding reports preserves them.

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

The verified [online Demo](https://hql7-luo.github.io/demos/supply-chain/) is a public static Plotly explorer on GitHub Pages. The complete **six-tab Streamlit app**, including planning scenarios, runs locally with the same real demo database. See [deployment scope and platform assessment](docs/online_demo.md).

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

**Dataset:** FreshRetailNet-50K, developed by Dingdong-Inc. Original [dataset card](https://huggingface.co/datasets/Dingdong-Inc/FreshRetailNet-50K) and [research paper](https://arxiv.org/abs/2505.16319). License: [CC BY 4.0](data/LICENSE.md). Downloaded **2026-10-06 UTC**; pinned revision `08c1fab7f9257bc73679d415d65d644165d351d4`. Full raw files are not stored on GitHub for size; the attributed real demo and derived evidence are stored.

**Real fields:** dates, globally normalized daily/hourly sales, encoded product/category/store/city IDs, hourly stockout flags, discount, holidays, activities and weather. **Synthetic source fields: none.** Renaming, aggregation, forecasts and classifications are analytical transformations. Lead-time distribution, service target and inventory position are separate, visible scenario assumptions.

The data covers **2024-03-28–2024-07-02**, not current inventory. It contains no on-hand quantity, unit price/cost, supplier, purchase order, shelf life or spoilage cost. Consequently there are no actual inventory values, turnover, EOQ, supplier rankings, realized service levels or executable replenishment orders. All monetary or physical-unit conclusions would need additional data. The normal-approximation planning formula assumes independent stationary demand and lead time; it is particularly limited for perishable/intermittent and stockout-censored demand. Annual seasonality and lost demand are not estimated.

Code is MIT licensed; source and derived data retain their separate CC BY 4.0 attribution. See [data rights](data/LICENSE.md).
