# Dataset selection and provenance

Research date: **2026-10-06**. The search began on Kaggle using supply chain,
inventory, retail sales, fulfillment, and demand forecasting terms. Candidate
evaluation traced mirrors back to their original publishers and licenses.

## Selection

**FreshRetailNet-50K, released by Dingdong-Inc**, was selected because it pairs
real dated sales observations with explicit hourly stockout annotations. This
supports a credible question: which store-product combinations have persistent
availability problems, and which should management investigate first?

The dataset comes from Dingdong's public release. It is not the project author's
employment data, and the project is not affiliated with or endorsed by Dingdong.
Encoded store, product, and category identifiers are retained without invented
names. Alibaba is not the data publisher.

## Candidate comparison

These are **publisher metadata and public schema/preview assessments**, not four
completed raw-data audits. Only the selected FreshRetailNet files are downloaded
and fully profiled by the project pipeline. Candidate row counts are identified
as advertised counts where no local computation was performed. Unknown values
remain unknown instead of being copied from third-party notebooks.

| Candidate | Verified public scale / history | Real analytical fields | Inventory / supplier fit | License and reproducibility | Decision |
| --- | --- | --- | --- | --- | --- |
| [FreshRetailNet-50K](https://huggingface.co/datasets/Dingdong-Inc/FreshRetailNet-50K) | Publisher advertises 4,500,000 training rows and 350,000 evaluation rows; 19 fields; 50,000 store-product series; 90 training days and 7 evaluation days. Card lists 898 stores, 18 cities and 865 products. | Encoded product/category/store/city IDs, daily and hourly normalized sales, hourly stockout status, stockout-hour count, discounts, calendar and weather covariates. | Real stock availability observations; no inventory balances, supplier IDs, purchase orders, procurement lead times, unit cost, or selling price. | Original publisher's CC BY 4.0; public ungated Parquet downloads; approximately 115 MB total. Immutable revision and checksums can be pinned without Kaggle credentials. | **Selected:** best evidence for real stockout risk, interpretable forecasting, SQL dimensional modeling, and explicit planning scenarios. |
| [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) | Olist advertises approximately 100,000 real orders, 2016–2018; nine CSV files. Exact local product count and null/duplicate rates were not audited. | Product/category IDs, marketplace seller IDs and locations, order-item price and freight, purchase, shipping, delivered and estimated-delivery timestamps, order status. | Good seller/fulfillment analysis. Sellers are marketplace merchants, not observed procurement suppliers. No stock balances or replenishment orders; many products may have sparse demand histories. | Publisher's **CC BY-NC-SA 4.0**. Redistribution requires attribution and compliance with noncommercial/share-alike conditions. Kaggle setup/manual download would be needed. | Credible second choice for fulfillment, but weaker for the central inventory-risk question and less permissive for reuse. |
| [Online Retail II, Kaggle mirror](https://www.kaggle.com/datasets/lakshmi25npathi/online-retail-dataset) / [original UCI record](https://archive.ics.uci.edu/dataset/502/online+retail+ii) | UCI advertises **1,067,371** transaction lines; eight variables; **2009-12-01–2011-12-09**. The two-sheet workbook is approximately 43.5 MiB / 45.6 MB. UCI explicitly reports missing values; exact local rates and unique products were not audited. | Invoice ID, product code and description, quantity, invoice date/time, unit price in GBP, customer ID and country. Cancellation invoices are marked with a leading C. | Strong transaction demand and monetary ABC analysis, but no observed stockouts, stock on hand, suppliers, delivery timestamps, or procurement. Zero sales cannot establish a stockout. | Original UCI **CC BY 4.0**, DOI [10.24432/C5CG6D](https://doi.org/10.24432/C5CG6D), creator Daqing Chen. Kaggle's generic "Other" license label does not supersede the original release. Public direct UCI download is available. | Longer forecasting history, but would require assumptions for nearly all inventory observations. |
| [DataCo SMART Supply Chain, Kaggle mirror](https://www.kaggle.com/datasets/shashwatwork/dataco-smart-supply-chain-for-big-data-analysis) / [original Mendeley v5](https://data.mendeley.com/datasets/8gx2fvg2k6/5) | Mendeley v5 advertises a structured CSV of approximately 91.5 MiB plus a variable-description CSV and clickstream file. Exact row, structured-column, product and date counts were **not verified locally**; Kaggle's combined-file column count is not treated as the structured schema count. | Public variable descriptions include product/category, order quantity, sales/profit, shipping mode/status and actual/scheduled shipping times; customer fields also appear. | Useful fulfillment/shipping data. No verified stock-on-hand or procurement supplier fields. Customer-related fields require careful privacy review; do not redistribute them automatically. | Original authors Fabian Constante, Fernando Silva and António Pereira; Mendeley v5 **CC BY 4.0**, DOI [10.17632/8gx2fvg2k6.5](https://doi.org/10.17632/8gx2fvg2k6.5). Kaggle's CC0 label conflicts with the original and is not relied on. | Not selected: less direct availability evidence, mirror-license conflict, and unnecessary customer fields. |

No dataset was chosen just for size. No generic dataset was treated as real
because its filename contained "supply chain" or because it had many fields.

## Completed audit of the selected raw files

The [generated full-source quality evidence](evidence/data_quality.json) profiles
**every downloaded record**, including both 24-hour sales and stockout arrays.
This is a computed audit rather than a copied dataset-card summary.

| Check | Computed result |
| --- | --- |
| Rows and source columns | **4,850,000 rows; 19 columns**. |
| Operational entities | **50,000 store-product series; 865 products; 898 stores; 18 cities; 32 first-category IDs**. |
| History | **2024-03-28–2024-07-02; 97 contiguous days per series**. Training: 2024-03-28–2024-06-25. Evaluation: 2024-06-26–2024-07-02. |
| Null source fields | **0** across all 19 columns in both files. Hourly arrays also have valid lengths and values. |
| Duplicate primary keys | **0** duplicate store-product-date keys. |
| Missing series-days | **0**; no missing period was imputed as zero demand. |
| Daily/hourly sales reconciliation | **0** disagreements within the pipeline's numeric tolerance. |
| Operating-hour stockout reconciliation | **0** disagreements between source count and hourly-status positions `[6:22]`, confirming a **16-hour** denominator. |
| Source anomaly | **34 discount factors greater than 1**, maximum **1.088**, all in training. Preserved and reported; not forecast or risk inputs. |
| Observed zero sales | **215,323** store-product-days; **164,587** also contain operating-window stockout exposure. Zero sales are therefore not automatically treated as zero demand. |

Source IDs are integer fields; `dt` is a string parsed as an ISO date; daily sales,
discount and weather fields are floating point; hourly sales/status fields are
lists. Exact Arrow types and column-level null counts are retained in the quality
JSON. No records were removed, capped, or synthetically replaced.

There is sufficient history for weekly baselines and a genuine seven-day holdout.
The history is too short to establish annual seasonality. Inventory analysis is
limited to observed availability and conditional planning scenarios. Procurement
supplier analysis is unavailable because no supplier or purchase-order fields
exist in the released schema.

## Exact selected source

- Dataset: **FreshRetailNet-50K**, dataset version **1.0**.
- Data developer and original publisher: **Dingdong-Inc**.
- Official dataset card: <https://huggingface.co/datasets/Dingdong-Inc/FreshRetailNet-50K>.
- Official paper: <https://arxiv.org/abs/2505.16319>.
- Official baseline code: <https://github.com/Dingdong-Inc/frn-50k-baseline>.
- License: [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/).
- Pinned source revision: `08c1fab7f9257bc73679d415d65d644165d351d4`.
- Download date: **2026-10-06**; the generated download manifest records the actual retrieval time and file hashes.
- The downloader needs no account token. No credentials belong in this repository.

| File | Immutable download URL | SHA-256 advertised by the official file page |
| --- | --- | --- |
| Training observations | [data/train.parquet](https://huggingface.co/datasets/Dingdong-Inc/FreshRetailNet-50K/resolve/08c1fab7f9257bc73679d415d65d644165d351d4/data/train.parquet) | `6706832db892bbae4969c19d87e07975d2543d2ba7d7d4756360654785de5a3d` |
| Evaluation observations | [data/eval.parquet](https://huggingface.co/datasets/Dingdong-Inc/FreshRetailNet-50K/resolve/08c1fab7f9257bc73679d415d65d644165d351d4/data/eval.parquet) | `1b118840664280c6b88bffc84c80ee1f54c05d911e354b7599e5da10995e960e` |

Raw files are obtained through the reproducible downloader and kept outside Git
tracking. CC BY 4.0 permits sharing and adaptation with attribution; omitting the
full raw files keeps the repository manageable rather than reflecting a license
prohibition. Redistributed samples and derived analytics retain source attribution
and a notice explaining selection, aggregation, and analytical changes. The
repository's software license does not replace the source-data license.

## Source disagreements and boundaries

The released card advertises **865 products**; the paper's abstract says **863**.
The actual downloaded files contain **865 distinct products**, agreeing with the
released card. The metadata discrepancy is preserved. Similar
reported research findings are not copied into the project's findings: all
headline percentages must come from the reproducible pipeline.

`sale_amount` and `hours_sale` are **globally normalized sales amounts**. The
normalization coefficient is not released. These values are not observed GBP,
CNY, revenue, costs, or disclosed physical units. Charts and policy outputs use
**normalized sales units**. Monetary inventory value, annual consumption value,
margin, working capital, and physical purchase quantities cannot be recovered.

`hours_stock_status` identifies hourly out-of-stock status, and
`stock_hour6_22_cnt` counts out-of-stock hours in the publisher's operating window.
These are availability indicators, not stock balances or service-level outcomes.
The released fields and actual count/vector reconciliation control the project's
definition; a differently encoded mathematical mask in the paper is not copied
into the data schema.

The source uses encoded IDs and does not release customer names, emails, or
addresses in its 19-column schema. The paper reports pseudonymization before
release. This project does not attempt reidentification or infer encoded city,
store, category or product names.

## Consequences for project scope

Supported: observed sales trends, category-ID comparison, weekly demand patterns,
sales-concentration ABC, demand-variability XYZ, stockout frequency and hour
exposure, a rule-based availability-risk queue, short-horizon sales forecasting,
and explicitly assumed planning targets.

Unavailable: actual current inventory, days of supply, turnover, inventory value,
fill rate, procurement supplier reliability, purchase-order delays, economic
order quantity, realized lost sales, and demonstrated cost savings. They are not
filled with fabricated operational records.

Scenario lead time, target service level, and demand multipliers are **visible
management assumptions**. They are separate from the immutable observations.
No synthetic supplier/customer/order history is generated.
