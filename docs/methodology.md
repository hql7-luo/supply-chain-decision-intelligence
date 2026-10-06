# Analytical methodology and decision boundaries

## Business question and grain

The project converts real sales and hourly stockout observations into an
investigation queue for management. The operational entity is a **store-product
combination**, not a product pooled across stores: a product may be available in
one store and unavailable in another. Product and store dimensions use the
publisher's encoded identifiers.

Observations belong to the historical 2024 study window. "Latest" means the end
of this dataset, **not today's inventory or sales**. All sales, forecasts and
planning targets use **normalized sales units**. The publisher does not disclose
the multiplier needed to recover physical quantities or monetary values.

## Observations, derived measures, assumptions

| Type | Examples | Interpretation |
| --- | --- | --- |
| Real source observations | Daily/hourly normalized sales; hourly out-of-stock flags; dates; category/store/city IDs; discount and weather fields | Historical released data; never overwritten with synthetic values. |
| Derived historical measures | Stockout-day frequency; operating-hour stockout exposure; demand CV; concentration class; forecast errors | Reproducible transformations of source observations, conditional on the selected cohort and dates. |
| Forecast estimates | Seven-day predicted observed sales; selected model | Model estimates, evaluated against sales observations. They do not establish the unobserved demand lost during stockouts. |
| Planning assumptions | Lead time and its standard deviation; target cycle-service probability; demand multiplier; assumed inventory position | User-visible scenario inputs, not measured Dingdong policies, supplier performance, or inventory balances. |
| Conditional planning outputs | Safety buffer; reorder target; gap to assumed inventory position | Formula outputs in normalized units under disclosed assumptions; not executable purchase orders. |

No synthetic suppliers, purchase orders, customer history, current stock balances,
or historical demand periods are generated. Scenario parameters live separately
from source observations and are documented as analytical assumptions.

## Data quality and cleaning

The preparation pipeline validates types, dates, nonnegative sales, required IDs,
binary stockout flags, 24-element hourly arrays, stockout-hour limits, and
store-product-date uniqueness. It records missing values, duplicates, date
coverage, product/store counts, and period completeness in generated quality
artifacts. The selected cohort and full source profiles must be read separately:
cohort findings cannot be described as the whole company or all 50,000 series.

Legitimate zero sales remain zero. Zero sales alone are never classified as a
stockout. Positive stockout flags are retained because they carry business
information rather than representing bad rows. Extreme sales are retained unless
a documented validation rule identifies them as invalid; an outlier is not
automatically an error. Missing dates are not silently replaced with zero demand.

Any comparison between daily sales and sums of hourly sales accounts for floating
point precision and the publisher's normalization. Stockout-vector reconciliation
is documented in the quality report. Recorded disagreement is kept visible rather
than silently rewriting a source field.

**Discount-factor exception found during the full audit:** 34 training records
have `discount > 1`, with maximum **1.088**. The source card describes a discount
factor where 1 means no discount, so these observations are treated as a documented
source anomaly. All original factors and affected records are retained; none are
capped or dropped. The quality report records their range and examples. Discounts
are not forecast inputs or risk-rule inputs, so these values do not feed the
management queue or model selection. Their meaning would need clarification
from the publisher before using them to measure promotion effectiveness.

## Availability risk

Two measures answer different questions:

$$
\text{Stockout-day frequency} =
\frac{\text{days with positive operating-window stockout count}}
     {\text{observed days}}
$$

$$
\text{Operating-hour stockout exposure} =
\frac{\text{out-of-stock operating hours}}
     {\text{observed days}\times\text{operating hours per day}}
$$

The operating window has **16 bins, 06:00 through 21:59**, corresponding to
array positions `[6:22]`. The pipeline reconciles this slice against the released
`stock_hour6_22_cnt` values. Overnight flags are not mixed into the operating
exposure denominator. Ratios for groups are calculated from summed numerators
and denominators, rather than an unweighted average of arbitrary subgroup rates.

Management risk uses recent **28 observed days** at the store-product grain,
with rules applied in this order:

| Status | Rule | Suggested management response |
| --- | --- | --- |
| Critical | Operating-hour stockout exposure at least 25% | Investigate persistent availability loss; review actual replenishment, inventory records and local demand before changing orders. |
| High Risk | Exposure at least 10%, below the Critical threshold | Prioritize replenishment and assortment review; examine recurring shortage hours. |
| Watch | Any operating-window stockout, daily-sales CV above 1, or no observed sales in the recent window | Monitor variability and stockout timing; investigate whether zero observed sales reflect demand, assortment, or availability conditions. |
| Healthy | None of the above | Maintain monitoring; this means relatively low observed risk, not guaranteed future service. |

The cutoffs are transparent prioritization heuristics, not statistically estimated
probabilities or source-company policy. The same inputs always produce the same
status and explanation. No "Overstock" status is claimed because stock balances
and spoilage are unavailable. These actions are investigation priorities, not
claims that a real purchase order must be placed immediately.

## Concentration and variability

The field `volume_abc_class` summarizes each store-product entity's contribution
to observed **normalized sales over all 97 days**, sorted from largest to smallest,
using cumulative contribution boundaries.
Class A covers approximately the first 80%, B the next 15%, and C the remaining
5%. An item is assigned using cumulative share **before** including that item:
below 80% is A, below 95% is B, otherwise C. Thus the item crossing a boundary
stays in the preceding class. Ties use the series ID. A portfolio with no observed
sales has Unknown classes and undefined shares.
The report retains the exact resulting class shares; the count of A entities is
not presumed to be 20%.

This is a sales-concentration adaptation of ABC. It is not a financial ABC based
on annual consumption value, revenue, inventory value, or margin. Global
normalization preserves relative contributions, but the short study window does
not support annual value claims.

XYZ uses daily observed-sales variability over the latest 28 days:

$$
CV=\frac{s_D}{\bar D},\qquad
s_D=\sqrt{\frac{\sum_t(D_t-\bar D)^2}{n-1}}
$$

X: CV at most 0.5; Y: greater than 0.5 and at most 1.0; Z: greater than 1.0.
For an all-zero observed-sales series, CV is mathematically undefined and is
recorded as missing; the XYZ class is **Unknown**, rather than claiming predictable
X demand. Such series receive at least Watch status unless the higher stockout
thresholds apply. At least two historical observations are required to estimate
the sample standard deviation. Because sales are censored during stockouts,
CV describes **observed sales variability**, not known unconstrained demand.

Combined ABC-XYZ segments support differentiated review: concentrate management
attention on high-contribution items with repeated shortages or volatile sales.
Segmentation alone does not establish optimal inventory policy.

## Forecasting and validation

The forecast target is **observed daily normalized sales**, including real zero
observations. Sales may understate latent demand when a product is unavailable;
the project therefore discloses censoring and reports performance both across all
holdout observations and separately on days with **zero operating-window stockout
hours**. The latter is a conditional diagnostic, not proof that unconstrained
demand is recovered or that zero-stockout days are a random sample.

Four interpretable methods compete per store-product series:

1. **Naive:** repeat the most recent observed daily value.
2. **Seasonal naive, period 7:** repeat the latest observed week.
3. **28-day moving average:** repeat the most recent 28-day mean.
4. **Simple exponential smoothing:** fixed alpha 0.3, constant multi-step forecast.

Each model is trained only on data preceding the forecast origin. Predictions
are produced for all seven horizon days before those days' actual sales are
accessed. Model selection minimizes **pooled MAE across three expanding-window
validation folds**; ties use the fixed method order above. The official final
seven-day evaluation split is untouched by model selection.

| Stage | Training days | Prediction days | Purpose |
| --- | --- | --- | --- |
| Validation 1 | 1–69 | 70–76 | Select model using historical future errors. |
| Validation 2 | 1–76 | 77–83 | Expand the available history. |
| Validation 3 | 1–83 | 84–90 | Complete selection before final evaluation. |
| Holdout | 1–90 | 91–97 | Evaluate the selected model once on the source evaluation period. |
| Illustrative outlook | 1–97 | 98–104 | Refit the selected method for seven days after the historical study window; actuals are unavailable. |

Where the downloaded files confirm a 2024-03-28 start, the holdout is
2024-06-26–2024-07-02 and the illustrative outlook is
2024-07-03–2024-07-09. These dates are not forecasts for October 2026.

No random train/test split is used. Holdout stockout flags are used only to label
evaluation subsets after prediction, never as known future forecast inputs. The
90-day history supports weekly patterns, not credible annual seasonality or
long-horizon planning. The project makes no claim that adding a complex model
would necessarily improve business decisions.

For errors $e_t=\hat y_t-y_t$:

$$
MAE=\frac{\sum_t|e_t|}{n},\quad
RMSE=\sqrt{\frac{\sum_t e_t^2}{n}},\quad
WAPE=\frac{\sum_t|e_t|}{\sum_t y_t},\quad
Bias=\frac{\sum_t e_t}{\sum_t y_t}
$$

Positive Bias means overforecasting; negative Bias means underforecasting.
Zero total observed sales gives undefined WAPE/Bias, recorded as missing rather
than reported as zero. Portfolio WAPE and Bias use **micro totals** of errors and
actuals, rather than averaging series-level percentages. Percentage displays
multiply the ratio by 100. MAE/RMSE remain in normalized sales units.

Fixed-method holdout baselines are also reported as diagnostics. Their final
holdout scores do not change model selection. The selected method is not claimed
to beat every fixed baseline in the holdout: per-series validation selection can
still generalize poorly, and that outcome remains visible.

## Inventory planning scenarios

The dashboard can explore how explicit assumptions change a **planning target**.
It cannot infer actual inventory coverage or prove a stockout probability.

Let daily observed-sales mean be $\mu_D$, sample standard deviation
$\sigma_D$, assumed mean replenishment lead time $L$ days, assumed
lead-time standard deviation $\sigma_L$, and target cycle-service probability
$p$. The normal quantile is $z=\Phi^{-1}(p)$.

Under independent daily demand, independence between demand and lead time, and a
normal approximation to demand over replenishment lead time:

$$
SS=z\sqrt{L\sigma_D^2+\mu_D^2\sigma_L^2}
$$

$$
ROP=\mu_D L+SS
$$

These are a conditional safety buffer and reorder target in normalized units.
They are not disclosed source-company policies. A 95% input is a **target cycle
service probability under the assumed model**, not an observed 95% fill rate.
The formula does not model correlation, seasonality over the lead-time window,
substitution, batch ordering, perishability, or the censorship of demand by
stockouts. Frequent stockouts may make the observed mean/std too low; the target
should be treated as an exploratory baseline until uncensored demand and real
operational data are available.

A demand multiplier $m$ scales both $\mu_D$ and $\sigma_D$ by $m$.
For example, +20% uses $m=1.2$. This assumes proportional variability; it is not
an empirical estimate of promotion response. Changing lead time is a scenario,
not evidence of a supplier disruption. A service-level slider changes $z$
without altering the real source history.

Scenario inputs must be finite. Means, standard deviations and assumed inventory
position are nonnegative; target service lies in $[0.5,1)$; the demand shock is
at least -100%. A nonnegative quantity with zero mean cannot have a positive
standard deviation, so zero-mean/positive-variance demand or lead-time inputs are
rejected. A -100% demand scenario consistently sets both demand mean and standard
deviation to zero.

If management enters an **assumed inventory position** $I$:

$$
\text{Gap to planning target}=\max(ROP-I,0)
$$

Inventory position ordinarily includes on hand plus confirmed inbound supply
minus backorders. The source contains none of these quantities, so the dashboard
never presents the user-entered number as a real measured balance. The gap is
not an optimized order quantity, and managers would still need actual balances,
pack sizes, supplier constraints, review cycles and shelf-life information.

EOQ, inventory turnover, days of supply, inventory value, working capital,
realized lost-sales amounts, and supplier rankings are intentionally omitted:
the required source fields are not available. No assumed unit prices or
fabricated supplier histories are added to make those metrics appear possible.

## SQL and decision traceability

SQLite is the analytical model shared by the dashboard and audit notebook.
Visible SQL queries expose daily/monthly sales, encoded category trends,
stockout exposure, concentration, and risk-ranking inputs. Forecast and planning
results preserve store/product IDs and model/assumption metadata so a reviewer
can follow an output back to its input period and rule.

Headline findings are computed from the analytical population. Recommendations
state the calculated reason and identify the additional operational evidence
needed for implementation. Historical association between discounts, sales and
stockouts is not treated as causal proof. No cost savings or financial impact is
claimed without real economics and a defensible counterfactual.
