# Architecture and analytical grain

```mermaid
flowchart TD
  A[Public FreshRetailNet files pinned by revision and SHA-256] --> B[Raw schema, key, date and hourly reconciliation checks]
  B --> C[SQLite star schema: dim_series + fact_daily_sales]
  C --> D[Visible SQL: category availability, monthly sales, concentration, management queue]
  B --> E[Vectorized Python: rolling forecast validation and final holdout]
  D --> F[Observed stockout priorities + sales contribution ABC + XYZ]
  E --> F
  F --> G[Streamlit management dashboard]
  H[Explicit user planning assumptions: lead time, service target, inventory position] --> I[Safety-stock and reorder-point sensitivity]
  E --> I
  I --> G
```

The analytical grain is one **store-product-date**, not one SKU across all stores.
`series_id = store_id:product_id`. The fact table has a composite primary key
`(series_id, date)` and a foreign key to `dim_series`. Encoded category/store
attributes are stored once per series. `daily_sales` is a convenience join view.

Raw data and the full SQLite database are local generated files. A small, real-data
demo is committed so a recruiter can launch the app without a 115 MB download.
The demo is selected deterministically across priority groups and cannot represent
population prevalence. Full-data findings have their own scope in the evidence files.

Forecast results, quality evidence and management outputs are saved by the pipeline;
the dashboard reads SQLite and recomputes only user-driven planning scenarios.
Operational assumptions never overwrite source data and are never turned into
invented supplier, inventory or procurement tables.
