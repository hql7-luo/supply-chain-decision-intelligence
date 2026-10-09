# From retail evidence to management review

This project asks two practical questions: **which store–product pairs need an availability investigation, and which sales forecast deserves further testing?** It turns historical records into a focused, explainable review process. It supports business judgment; it does not produce executable replenishment orders.

**Project role:** I led this personal, AI-assisted project, defined the inventory-risk, forecasting and management-report requirements, and reviewed the final outputs. AI assisted the data processing, forecast analysis, dashboard implementation and engineering tests.

## Four findings and the decisions they support

The owners below are **suggested business responsibilities**, not a record of people who worked on or deployed this project. Each action requires information beyond this public dataset.

### 1. Investigate availability before deciding to replenish

**Finding.** The latest 28-day rules flag **40,591 of 50,000 series (81.18%)** as Critical or High Risk. They represent **75.79% of recent observed sales**. Across the full 97 days, 44.03% of store–product days had at least one unavailable operating hour. [Saved full-data evidence](evidence/findings.json)

**Why it matters.** A queue covering four in five series is too broad to treat as an order list. The original ranking starts with the most severe observed exposure; it does not rank sales contribution, lost sales or economic return.

**Suggested owner and action.** A store-operations lead should start with the original severity-priority view, choose a manageable review capacity, and check whether each item is still actively offered and whether its stockout records match operating conditions. A replenishment planner can then investigate verified recurring gaps.

**Needed inputs.** Active assortment, actual on-hand inventory, open orders and receipts, and the operational cause of unavailability. Historical source IDs alone cannot establish the cause.

### 2. Review high-contribution items with recurring shortages

**Finding.** **122 of 865 products (14.10%) contribute at least 80% of full-period observed sales.** The existing store–product ABC classification provides a separate, more detailed sales-contribution lens. [Product concentration](evidence/findings.json) · [ABC method](methodology.md#concentration-and-variability)

**Why it matters.** Review capacity can focus on items with substantial recorded sales as well as recurring shortages. This is a contribution-to-observed-sales measure; prices and margins are absent. The 122-product result is not the count of A-class store–product series.

**Suggested owner and action.** A replenishment planner, with store operations, should inspect Critical/High Risk items in the existing sales view and review their saved A-tier classification. An explicit A-only worklist uses that saved class and the existing 97-day sales sort; it is a management-investigation filter, not a new score or an optimized policy.

**Needed inputs.** Actual stock and in-transit quantities, measured lead times, shelf life, the normalization scale and unit-level costs before deciding quantities or financial priority. Low recorded sales during a stockout do not prove low demand.

### 3. Keep the stronger simple forecast visible

**Finding.** Fixed exponential smoothing (**SES**) has **36.00% WAPE**, compared with **37.42%** for the model selected separately for each series, on the same untouched seven-day holdout. WAPE is total absolute forecast error divided by total observed sales; lower is better. [Saved benchmark](executive_summary.md#forecasting-decision) · [Validation design](methodology.md#forecasting-and-validation)

**Why it matters.** The more flexible selector did not improve the pooled result. The holdout was not used to change the selected models, so the simpler baseline is a candidate for further evaluation rather than a newly adopted policy.

**Suggested owner and action.** A demand-planning analyst should retain the negative result and evaluate the fixed SES candidate on new periods before adopting it. Review store–product actual-versus-predicted results rather than choosing a model only from one aggregate number.

**Needed inputs.** New chronological observations, availability records and the relevant planning horizon. Three months of history do not establish annual seasonality, forecast accuracy for unconstrained demand or realized service improvements.

### 4. Do not treat zero sales as proof of no demand

**Finding.** **164,587 of 215,323 zero-sales days (76.44%)** also had recorded stockout exposure. [Full-data zero-sales evidence](evidence/findings.json) · [Data-quality interpretation](data_quality_report.md#analytical-risk-censored-sales)

**Why it matters.** Observed sales can be limited by availability. The coexistence of zero sales and a stockout does not identify the cause or quantity of lost demand.

**Suggested owner and action.** An analytics owner and store-operations lead should validate assortment and recording, compare the sales and availability histories, and investigate zero-sales series before classifying them as low demand.

**Needed inputs.** Assortment status, actual inventory and receiving events, reliable availability logs, and a separately validated demand-recovery method if latent demand is the intended target. This project forecasts observed sales.

## Two complementary investigation views

**Availability investigation.** Filter Critical / High Risk and use **Original management priority**. It orders by risk group, unavailable-hour rate, affected-day share, sales variability and ID. Use Top 20 or Top 50 as a capacity limit. The saved first-five table in the [generated technical brief](executive_summary.md#original-exposure-order-examples) is an example of this purpose, not a highest-sales list.

**A-tier sales-contribution review.** Within Critical / High Risk, retain the saved **A-class store–product series**, then use the existing **Highest observed sales** ordering: 97-day observed sales descending, followed by original priority and ID. Retain original ranks and risk labels. Saved ABC classes describe the analysis cohort; city/category filters do not recalculate them. If fewer than 20/50 items match, show the actual count; do not fill the list with another class.

The current local Streamlit app already provides status, capacity, sales/exposure sorting, the ABC column and CSV export. It does **not** have a dedicated A-only preset. The A-only filter above is a documented review-worklist definition using existing saved fields. It introduces no risk rule, weighted score, optimizer, reclassification or change to the static Demo.

## Try the existing views without confusing their scope

1. Open the [public real-data Demo](https://hql7-luo.github.io/demos/supply-chain/). Keep **Critical + High Risk**, choose **Top 20 / Top 50**, and compare **Pipeline priority** with **Recent observed sales**. Click Review to inspect an item's action, reason, history and scored forecast.
2. In the local six-tab Streamlit app, choose the same statuses and capacity, then compare **Original management priority** with **Highest observed sales**. Read the saved ABC column and export the displayed rows for a scoped review. An A-only worklist can be formed from the saved/exported fields before applying its review-capacity limit; it is not a new online control.
3. Keep the periods explicit: public Demo sales sorting uses the **latest 28 days**; local Streamlit sales sorting uses **all 97 historical days**. Availability status and exposure use **June 5–July 2, 2024** in both. The visible local mean-daily-sales column is the 28-day mean, not the 97-day sorting total.

### What a view switch changes in the real 200-series Demo

These are newly checked descriptions of the **committed 200-series / 19,400-row illustration**, not estimates for all 50,000 series. Both views retain original risks and ranks. Recent sales shares use the entire 200-series cohort's latest-28-day sales as their denominator.

| Capacity | Original severity view | Existing Streamlit 97-day sales view |
| --- | --- | --- |
| Top 20 | 20 Critical; ABC 13 A / 6 B / 1 C; **6.58%** of Demo recent observed sales | 8 Critical + 12 High Risk; 20 A; **17.77%** of Demo recent observed sales |
| Top 50 | 50 Critical; ABC 26 A / 18 B / 6 C; **20.03%** of Demo recent observed sales | 26 Critical + 24 High Risk; 50 A; **29.10%** of Demo recent observed sales |

The two Top 20 lists share only **2** items. The explicit A-only filter produces the **same** Top 20/50 rows as the existing Streamlit sales sort in this Demo; it adds a clear review criterion, not a demonstrated performance gain. Sales share is a descriptive difference, not revenue, recovered demand or savings. No new full-population Top 20/50 list is published: the repository saves ten original full-data examples, while the complete generated 50k database is a local reproduction output.

## Evidence and scope

- **Full analysis:** 4,850,000 released observations, 50,000 store–product series, 97 dates, March 28–July 2, 2024. Risk uses the latest 28 dates; the forecast holdout is June 26–July 2. [Machine-readable findings](evidence/findings.json) · [Generated technical analysis](generated_analysis.md)
- **Public Demo:** 200 real series / 19,400 observations, deterministically selected across availability groups. It is not a representative sample. Its ABC classes and KPIs belong to that cohort. [Selection manifest](../data/demo/manifest.json) · [Deployment scope](online_demo.md)
- **Data source:** Dingdong-Inc / FreshRetailNet-50K, [pinned source revision](https://huggingface.co/datasets/Dingdong-Inc/FreshRetailNet-50K/tree/08c1fab7f9257bc73679d415d65d644165d351d4), CC BY 4.0. Globally normalized sales do not identify physical units, revenue, margin or current inventory. [Source hashes](evidence/download_manifest.json) · [Data rights](../data/LICENSE.md)
- **Overview figure:** [source values and provenance](evidence/management-action-overview.json). It summarizes saved results and proposed investigation steps. All five original analysis charts remain in the README's detailed-evidence section.
- **Reproducibility:** the 200-series comparison uses the existing [management-queue function](../app/dashboard.py), saved `series_summary` fields in the committed SQLite database, Critical/High Risk filtering, capacity 20/50 and unchanged ties. The original forecast and risk results are frozen. The report builder regenerates `generated_analysis.md`, `executive_summary.md` and the quality report; this editorial brief and the business README are maintained separately.

The project contains no current stock balances, actual open orders, supplier lead times, unit prices/costs, shelf life or spoilage costs. Planning scenarios use visible assumptions. These are investigation and sensitivity tools, with no claim of formal inventory optimization, automatic orders, realized savings or operational deployment.
