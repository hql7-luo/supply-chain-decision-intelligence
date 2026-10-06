# Data rights and attribution

Data and derived data are **not covered by the code's MIT license**.

FreshRetailNet-50K, developed and released by **Dingdong-Inc**, is licensed
under [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/legalcode).
The original [dataset card](https://huggingface.co/datasets/Dingdong-Inc/FreshRetailNet-50K)
governs source metadata. Redistribution and adaptation are permitted with attribution.

Citation: Wang, Y., Gu, J., Long, L., Li, X., Shen, L., Fu, Z., Zhou, X., and Jiang, X.
(2025). *FreshRetailNet-50K: A Stockout-Annotated Censored Demand Dataset for Latent
Demand Recovery and Forecasting in Fresh Retail.* [arXiv:2505.16319](https://arxiv.org/abs/2505.16319).

The compact database in `data/demo/` contains an explicitly selected subset of
original observations, a projection/renaming of fields, and project-calculated
forecasts, descriptive classifications, and recommendations. Original normalized
sales and stockout-hour values are unchanged. Model outputs are estimates, not
source observations. This adaptation does not imply Dingdong-Inc endorsement.

Full original Parquet files are downloaded locally and excluded from Git for size.
Their pinned revision, URLs, dates and hashes appear in `docs/evidence/download_manifest.json`.
Source data has no customer names, customer IDs, addresses or personal records in its schema.
Encoded stores/products/categories are retained without invented names.
