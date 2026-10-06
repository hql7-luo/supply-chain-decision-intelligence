# Data quality and cleaning report

The original pinned Parquet files were fully audited before publication.
All 4,850,000 records, all 19 source columns and every 24-element hourly
sales/status array were inspected. The analytical key is `(store_id, product_id, date)`.

| File | Rows | Date coverage | Missing source values | Daily/hourly sales disagreements | Stockout count disagreements |
| --- | ---: | --- | ---: | ---: | ---: |
| train.parquet | 4,500,000 | 2024-03-28–2024-06-25 | 0 | 0 | 0 |
| eval.parquet | 350,000 | 2024-06-26–2024-07-02 | 0 | 0 | 0 |

- 50,000 complete series, each with 97 consecutive dates; no missing series-days.
- Official train/eval split preserved: 90 train days and 7 later evaluation days for every series.
- 0 duplicate primary keys; hence no exact duplicate rows at this grain.
- 865 real encoded products, 898 stores, 18 cities, 32 first-category IDs. The source card's 865 products matches the actual files.
- Hourly flags are binary and reconcile exactly over indexes `[6:22]`: 16 one-hour bins, 06:00 through 21:59. Daily and hourly sales sums agree at the configured NumPy tolerances: absolute 1e-6 and relative 1e-5.
- Sales range 0.0–49.9 on the globally normalized scale. Extreme valid values remain in the data.

## Exception: discount factors above one

**Medium severity for promotion analysis; low impact on this project's core results.**
34 original train records have discount factors above 1,
up to 1.088. No source values were capped, deleted or overwritten.
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
