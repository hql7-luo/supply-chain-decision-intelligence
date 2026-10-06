"""Availability prioritization from observed sales and observed stockout hours.

No current inventory, purchase orders, supplier performance, or financial ABC
classification can be inferred from this dataset. The ABC-style column
describes only concentration of observed normalized sales volume.
"""

import numpy as np
import pandas as pd

from .forecasting import _daily_matrix, _positive_integer


def summarize_inventory(
    daily: pd.DataFrame, *, window: int = 28, exposure_hours: int = 16
) -> pd.DataFrame:
    """Return deterministic observed-risk ranks and sales-variability heuristics.

    Hour-rate thresholds: Critical >= .25, High Risk >= .10; any remaining
    stockout exposure, sales CV > 1, or zero recent mean sales is Watch. Priority sorts risk, hour rate,
    stockout-day fraction, CV, then series_id. XYZ uses CV <= .5 / <= 1 / > 1.
    Zero recent sales gives undefined CV and Unknown XYZ; verify assortment
    and recording before interpreting demand.
    ABC uses all supplied history; risk, XYZ, and demand statistics use the
    recent window. Items crossing the cumulative 80%
    and 95% thresholds stay in the preceding class. Zero portfolio sales gives
    Unknown. At least two periods are needed for sample sales variability.
    """
    window = _positive_integer(window, "window")
    matrix = _daily_matrix(daily, exposure_hours)
    days = min(window, len(matrix.dates))
    if days < 2:
        raise ValueError("At least two periods are required for sample sales variability")
    sales = matrix.sales[:, -days:]
    stockouts = matrix.stockouts[:, -days:]
    mean = sales.mean(axis=1)
    std = sales.std(axis=1, ddof=1) if days > 1 else np.zeros(len(matrix.series))
    cv = np.divide(std, mean, out=np.full_like(std, np.nan), where=mean > 0)
    hour_rate = stockouts.sum(axis=1) / (days * exposure_hours)
    day_fraction = (stockouts > 0).mean(axis=1)
    risk = np.select(
        [hour_rate >= 0.25, hour_rate >= 0.10, (hour_rate > 0) | (cv > 1) | (mean == 0)],
        ["Critical", "High Risk", "Watch"],
        default="Healthy",
    )
    xyz = np.select([mean == 0, cv <= 0.5, cv <= 1], ["Unknown", "X", "Y"], default="Z")
    result = pd.DataFrame(
        {
            "series_id": matrix.series,
            "observed_mean_sales": mean,
            "observed_std_sales": std,
            "sales_cv": cv,
            "xyz_class": xyz,
            "stockout_hour_rate": hour_rate,
            "stockout_day_fraction": day_fraction,
            "availability_risk": risk,
            "observed_sales_total": matrix.sales.sum(axis=1),
            "recent_sales_total": sales.sum(axis=1),
            "stockout_hours_total": stockouts.sum(axis=1).astype(int),
            "days_observed": days,
            "exposure_hours_per_day": exposure_hours,
            "window_start": str(matrix.dates[-days]),
            "window_end": str(matrix.dates[-1]),
        }
    )
    result = result.merge(matrix.metadata, on="series_id", validate="one_to_one")
    volume = result.sort_values(["observed_sales_total", "series_id"], ascending=[False, True])
    total = float(volume["observed_sales_total"].sum())
    volume["observed_sales_share"] = volume["observed_sales_total"] / total if total > 0 else np.nan
    previous_share = volume["observed_sales_share"].cumsum().shift(fill_value=0)
    volume["volume_abc_class"] = (
        np.select([previous_share < 0.8, previous_share < 0.95], ["A", "B"], default="C")
        if total > 0
        else "Unknown"
    )
    result = result.merge(
        volume[["series_id", "observed_sales_share", "volume_abc_class"]],
        on="series_id",
        validate="one_to_one",
    )
    recommendations = {
        "Critical": "Prioritize availability investigation and validate stockout causes.",
        "High Risk": "Review recurring availability gaps and replenishment assumptions.",
        "Watch": "Monitor availability and observed sales variability.",
        "Healthy": "Continue routine monitoring of observed availability.",
    }
    result["recommendation"] = result["availability_risk"].map(recommendations)
    no_sales = result["observed_mean_sales"].eq(0)
    result.loc[no_sales, "recommendation"] += (
        " Verify active assortment and sales recording; no recent sales observed."
    )
    result["reason"] = [
        f"{rate:.1%} of {exposure_hours}-hour daily exposure recorded out of stock; "
        f"{fraction:.1%} of recent days affected; "
        + (
            "no observed recent sales; CV is undefined; verify active assortment and recording. "
            if observed_mean == 0
            else f"observed sales CV {variability:.2f}. "
        )
        + "Current inventory and lost demand are unavailable."
        for rate, fraction, variability, observed_mean in zip(
            hour_rate, day_fraction, cv, mean, strict=True
        )
    ]
    result["_risk_order"] = result["availability_risk"].map(
        {"Critical": 0, "High Risk": 1, "Watch": 2, "Healthy": 3}
    )
    result = result.sort_values(
        ["_risk_order", "stockout_hour_rate", "stockout_day_fraction", "sales_cv", "series_id"],
        ascending=[True, False, False, False, True],
        kind="stable",
    )
    result["priority_rank"] = np.arange(1, len(result) + 1)
    return result.drop(columns="_risk_order").reset_index(drop=True)
