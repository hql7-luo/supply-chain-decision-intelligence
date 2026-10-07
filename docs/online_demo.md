# Public demo and deployment scope

**Verified live:** [200-series real-data explorer](https://hql7-luo.github.io/demos/supply-chain/), hosted on the existing public GitHub Pages portfolio.

The browser can display trends, a risk matrix, Top 20 / Top 50 management queues, status and sorting controls, series-specific actual-versus-forecast inspection, PNG chart exports and CSV downloads. English and Chinese interface text is available. Visitors need no Python installation, account, sign-in or paid service. The Plotly runtime and data are served from the same site; no analytics services or credentials are included.

## Data boundary

- **200 real store-product series / 19,400 source daily observations / 97 days**, March 28–July 2, 2024.
- Deterministic stratified illustration, not a representative population sample. Every live KPI and sales share uses this cohort.
- Subset stockout day rate: **40.2%**; operating-hour exposure: **20.2%**; per-series selector holdout WAPE: **36.9%**. These are not the full-population 44.0%, 19.7% or 37.4% findings.
- The case-study charts and README charts use the separately verified **full 4.85M-row / 50,000-series analysis**. The full benchmark remains **36.0% fixed SES versus 37.4% per-series selection**.
- Source: Dingdong-Inc / FreshRetailNet-50K, CC BY 4.0. Revision and data SHA-256 are in the public build manifest. Original observations are unchanged; forecasts, classifications and aggregation are analytical adaptations.
- Sales are globally normalized; no physical-unit, revenue, realized savings or executable replenishment claim is possible. Physical inventory, suppliers, purchase costs and lead-time records are absent.

## Why this platform

[GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages) supports static HTML, CSS and JavaScript in public repositories under GitHub Free. The existing portfolio already uses Pages, so this deployment requires no additional account or permission scope. It hosts a **static interactive explorer**, not a Python server.

[Streamlit Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app) can host public Streamlit applications, but requires a maintainer workspace and GitHub connection. That deployment session could not be inspected through the available authenticated browser connection in this run. No Community Cloud application or URL is claimed. The complete six-tab Streamlit dashboard retains its documented local launch and includes inventory planning scenarios that the static explorer does not implement.

## Rebuild and verify

```bash
uv run python scripts/verify_demo.py
uv run python scripts/build_web_demo.py --output /path/to/portfolio/demos/supply-chain
```

The exporter refuses any database scope other than `demo`, requires the reviewed 200-series cohort and 97 complete dates, and preserves all 19,400 observations. Python tests compare the export to SQLite. The portfolio CI independently recomputes the subset KPIs and validates forecast splits, bilingual case markup and image hashes. Real browser checks also exercised filters, selected forecasts, downloads and mobile display on the public address without a signed-in account.

[Deployment verification record](evidence/deployment.json) · [Public build manifest](https://hql7-luo.github.io/demos/supply-chain/manifest.json)
