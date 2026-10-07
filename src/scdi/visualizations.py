"""Reproducible full-population figures; the demo cannot supply full-data charts."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from scdi.forecasting import MODEL_NAMES, forecast_metrics

NAVY = "#223C50"
TEAL = "#167D8D"
RUST = "#B95F3D"
GOLD = "#B08A3C"
GREY = "#667986"
LIGHT = "#E6EDF0"
RISK_COLORS = {"Healthy": TEAL, "Watch": GOLD, "High Risk": NAVY, "Critical": RUST}
MODEL_LABELS = {
    "naive": "Naive",
    "seasonal_naive7": "Seasonal Naive (7 days)",
    "mean28": "Moving Average (28 days)",
    "ses_alpha0.3": "SES (alpha = 0.3)",
    "per_series_selector": "Per-series selector",
}
FIGURES = (
    "historical-demand-stockouts",
    "product-pareto",
    "forecast-comparison",
    "stockout-risk-matrix",
    "availability-zero-sales",
)


@dataclass
class ChartData:
    metadata: dict
    daily: pd.DataFrame
    products: pd.DataFrame
    models: pd.DataFrame
    risk: pd.DataFrame
    zero_sales: pd.DataFrame
    actual_metrics: dict


def pareto_products(products: pd.DataFrame) -> pd.DataFrame:
    """Rank every product; retain the item crossing the 80% threshold."""
    ranked = products.sort_values(
        ["normalized_sales", "product_id"], ascending=[False, True]
    ).reset_index(drop=True)
    total = float(ranked["normalized_sales"].sum())
    if total <= 0:
        raise ValueError("Product Pareto requires positive observed sales")
    ranked["rank"] = np.arange(1, len(ranked) + 1)
    ranked["sales_share"] = ranked["normalized_sales"] / total
    ranked["cumulative_share"] = ranked["sales_share"].cumsum()
    return ranked


def availability_bands(hours: pd.DataFrame) -> pd.DataFrame:
    """Weighted conditional zero-sales rates; full-day exposure stays separate."""
    definitions = (
        (0, 0, "0"),
        (1, 4, "1–4"),
        (5, 8, "5–8"),
        (9, 12, "9–12"),
        (13, 15, "13–15"),
        (16, 16, "16"),
    )
    rows = []
    for low, high, label in definitions:
        subset = hours.loc[hours["stockout_hours"].between(low, high)]
        count = int(subset["observed_days"].sum())
        zeros = int(subset["zero_sales_days"].sum())
        rows.append(
            {
                "stockout_hours_band": label,
                "observed_days": count,
                "zero_sales_days": zeros,
                "zero_sales_rate": zeros / count if count else 0.0,
            }
        )
    return pd.DataFrame(rows)


def _close(actual: float, expected: float, name: str) -> None:
    if not np.isclose(actual, expected, rtol=1e-10, atol=1e-10):
        raise ValueError(f"Visualization reconciliation failed: {name}: {actual} != {expected}")


def reconcile_findings(actual: dict, findings: dict) -> None:
    """Fail closed if chart cohorts or metrics differ from original analysis."""
    data = findings["data"]
    for field in (
        "rows",
        "series",
        "products",
        "stockout_days",
        "stockout_hour_rate",
        "zero_sales_days",
        "zero_sales_with_stockout",
    ):
        _close(actual["data"][field], data[field], field)
    for field in ("date_min", "date_max"):
        if actual["data"][field] != data[field]:
            raise ValueError(f"Visualization reconciliation failed: {field}")
    _close(
        actual["concentration"]["products_for_80pct_observed_sales"],
        findings["product_concentration"]["products_for_80pct_observed_sales"],
        "80% product count",
    )
    for risk, count in findings["risk_window"]["counts"].items():
        _close(actual["risk"]["counts"][risk], count, f"{risk} count")
    _close(
        actual["risk"]["high_priority_recent_sales_share"],
        findings["risk_window"]["high_priority_recent_sales_share"],
        "high-priority sales share",
    )
    expected_models = dict(findings["forecast"]["holdout_metrics"]["baselines"])
    expected_models["per_series_selector"] = findings["forecast"]["holdout_metrics"]["all_days"]
    for name, score in expected_models.items():
        for field in ("wape", "n_observations", "actual_sum"):
            _close(actual["forecast"][name][field], score[field], f"{name} {field}")


def load_chart_data(database: Path, findings: dict) -> ChartData:
    """Read SQL facts and recompute plotted aggregates and baseline forecasts."""
    if not database.is_file():
        raise FileNotFoundError(f"Full analysis database missing: {database}")
    with sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True) as connection:
        metadata = dict(connection.execute("SELECT key, value FROM metadata"))
        if metadata.get("scope") != "full":
            raise ValueError("Published full-data figures cannot be built from the demo subset")
        daily = pd.read_sql_query(
            """SELECT date, SUM(sales) AS normalized_sales, COUNT(*) AS observed_days,
               SUM(stockout_hours > 0) AS stockout_days,
               SUM(stockout_hours) AS stockout_hours,
               SUM(sales = 0) AS zero_sales_days,
               SUM(sales = 0 AND stockout_hours > 0) AS zero_sales_with_stockout
               FROM fact_daily_sales GROUP BY date ORDER BY date""",
            connection,
        )
        daily["stockout_hour_rate"] = daily["stockout_hours"] / (daily["observed_days"] * 16)
        daily["stockout_day_rate"] = daily["stockout_days"] / daily["observed_days"]
        products = pareto_products(
            pd.read_sql_query(
                """SELECT product_id, SUM(sales) AS normalized_sales FROM daily_sales
               GROUP BY product_id ORDER BY product_id""",
                connection,
            )
        )
        risk = pd.read_sql_query("SELECT * FROM series_summary ORDER BY series_id", connection)
        risk["recent_sales_share"] = risk["recent_sales_total"] / risk["recent_sales_total"].sum()
        hours = pd.read_sql_query(
            """SELECT stockout_hours, COUNT(*) AS observed_days,
               SUM(sales = 0) AS zero_sales_days FROM fact_daily_sales
               GROUP BY stockout_hours ORDER BY stockout_hours""",
            connection,
        )
        zeros = availability_bands(hours)
        series_count, row_count = len(risk), int(daily["observed_days"].sum())
        if len(daily) != 97 or not daily["observed_days"].eq(series_count).all():
            raise ValueError("Full visualization data must contain 97 complete days per series")
        # Read primary-key order without millions of repeated identifier strings.
        cursor = connection.execute("SELECT sales FROM fact_daily_sales ORDER BY series_id, date")
        sales = np.fromiter((row[0] for row in cursor), dtype=float, count=row_count)
        sales = sales.reshape(series_count, 97)
        actual_ids = [
            row[0]
            for row in connection.execute(
                "SELECT DISTINCT series_id FROM fact_daily_sales ORDER BY series_id"
            )
        ]
        if actual_ids != risk["series_id"].tolist():
            raise ValueError("Risk cohort identifiers do not match the original sales facts")
        stockouts = np.fromiter(
            (
                row[0]
                for row in connection.execute(
                    "SELECT stockout_hours FROM fact_daily_sales ORDER BY series_id, date"
                )
            ),
            dtype=np.int8,
            count=row_count,
        ).reshape(series_count, 97)
        recent_sales = sales[:, -28:]
        recent_rate = stockouts[:, -28:].sum(axis=1) / (28 * 16)
        recent_mean = recent_sales.mean(axis=1)
        recent_cv = np.divide(
            recent_sales.std(axis=1, ddof=1),
            recent_mean,
            out=np.full_like(recent_mean, np.nan),
            where=recent_mean > 0,
        )
        expected_risk = np.select(
            [
                recent_rate >= 0.25,
                recent_rate >= 0.10,
                (recent_rate > 0) | (recent_cv > 1) | (recent_mean == 0),
            ],
            ["Critical", "High Risk", "Watch"],
            default="Healthy",
        )
        for column, values in (
            ("recent_sales_total", recent_sales.sum(axis=1)),
            ("stockout_hour_rate", recent_rate),
            ("stockout_day_fraction", (stockouts[:, -28:] > 0).mean(axis=1)),
            ("sales_cv", recent_cv),
        ):
            if not np.allclose(risk[column].to_numpy(), values, equal_nan=True):
                raise ValueError(f"Risk chart {column} does not reconcile to original daily facts")
        if not np.array_equal(risk["availability_risk"].to_numpy(), expected_risk):
            raise ValueError("Risk classifications differ from the original 10% / 25% rules")
        ranked = risk.assign(
            _order=risk["availability_risk"].map(
                {"Critical": 0, "High Risk": 1, "Watch": 2, "Healthy": 3}
            )
        ).sort_values(
            ["_order", "stockout_hour_rate", "stockout_day_fraction", "sales_cv", "series_id"],
            ascending=[True, False, False, False, True],
            kind="stable",
        )
        if not np.array_equal(ranked["priority_rank"].to_numpy(), np.arange(1, series_count + 1)):
            raise ValueError("Risk chart priority ranks differ from the original severity ordering")
        training, actual = sales[:, :90], sales[:, 90:]
        predictions = {
            "naive": np.repeat(training[:, -1:], 7, axis=1),
            "seasonal_naive7": training[:, -7:],
            "mean28": np.repeat(training[:, -28:].mean(axis=1, keepdims=True), 7, axis=1),
        }
        level = training[:, 0].copy()
        for day in range(1, 90):
            level = 0.3 * training[:, day] + 0.7 * level
        predictions["ses_alpha0.3"] = np.repeat(level[:, None], 7, axis=1)
        scores = {
            name: forecast_metrics(actual, prediction) for name, prediction in predictions.items()
        }
        holdout = pd.read_sql_query(
            """SELECT series_id, date, actual, prediction FROM forecast_values
               WHERE split = 'holdout' ORDER BY series_id, date""",
            connection,
        )
        if holdout.shape[0] != series_count * 7:
            raise ValueError("Holdout must contain seven observations for every series")
        if not np.allclose(holdout["actual"].to_numpy().reshape(series_count, 7), actual):
            raise ValueError("Forecast actuals do not reconcile to the original sales facts")
        scores["per_series_selector"] = forecast_metrics(
            actual, holdout["prediction"].to_numpy().reshape(series_count, 7)
        )
    models = pd.DataFrame(
        [
            {"model": name, "label": MODEL_LABELS[name], **scores[name]}
            for name in (*MODEL_NAMES, "per_series_selector")
        ]
    )
    crossing = int(products.loc[products["cumulative_share"].ge(0.8), "rank"].iloc[0])
    priority = risk["availability_risk"].isin(["Critical", "High Risk"])
    metrics = {
        "data": {
            "rows": row_count,
            "series": series_count,
            "products": len(products),
            "date_min": str(daily["date"].min()),
            "date_max": str(daily["date"].max()),
            "stockout_days": int(daily["stockout_days"].sum()),
            "stockout_hour_rate": float(daily["stockout_hours"].sum() / (row_count * 16)),
            "zero_sales_days": int(daily["zero_sales_days"].sum()),
            "zero_sales_with_stockout": int(daily["zero_sales_with_stockout"].sum()),
            "normalized_sales_total": float(daily["normalized_sales"].sum()),
        },
        "concentration": {
            "products_for_80pct_observed_sales": crossing,
            "product_share_for_80pct": crossing / len(products),
            "cumulative_share_at_crossing": float(products.iloc[crossing - 1]["cumulative_share"]),
        },
        "risk": {
            "counts": {
                key: int(value) for key, value in risk["availability_risk"].value_counts().items()
            },
            "high_priority_series": int(priority.sum()),
            "high_priority_recent_sales_share": float(
                risk.loc[priority, "recent_sales_share"].sum()
            ),
            "window_start": str(risk["window_start"].min()),
            "window_end": str(risk["window_end"].max()),
            "recent_normalized_sales_total": float(risk["recent_sales_total"].sum()),
        },
        "forecast": scores,
        "zero_sales": {
            "zero_sales_with_stockout_share": float(
                daily["zero_sales_with_stockout"].sum() / daily["zero_sales_days"].sum()
            ),
            "bands": zeros.to_dict(orient="records"),
        },
    }
    reconcile_findings(metrics, findings)
    return ChartData(metadata, daily, products, models, risk, zeros, metrics)


def _style():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 14,
            "text.color": NAVY,
            "axes.labelcolor": NAVY,
            "xtick.color": GREY,
            "ytick.color": GREY,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.edgecolor": "#B9C6CC",
            "axes.linewidth": 0.8,
            "grid.color": LIGHT,
            "grid.linewidth": 0.8,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "svg.fonttype": "none",
            "svg.hashsalt": "scdi-full-data-v1",
        }
    )
    return plt


def _heading(figure, title: str, subtitle: str):
    figure.text(0.065, 0.956, title, ha="left", va="top", fontsize=23, weight="bold")
    figure.text(0.065, 0.909, subtitle, ha="left", va="top", fontsize=12.5, color=GREY)


def _note(figure, note: str):
    figure.text(0.065, 0.035, note, ha="left", va="bottom", fontsize=11.5, color=GREY)


def _export(figure, output: Path, name: str) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    files = {}
    for suffix in ("png", "svg"):
        path = output / f"{name}.{suffix}"
        metadata = {"Creator": "scdi.visualizations"}
        if suffix == "svg":
            metadata["Date"] = None
        figure.savefig(path, dpi=150, metadata=metadata)
        files[suffix] = {
            "filename": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
        }
    return files


def render_figures(data: ChartData, output: Path) -> dict:
    """Export five identically styled PNG/SVG figures without sampling."""
    plt = _style()
    import matplotlib.dates as mdates
    from matplotlib.lines import Line2D
    from matplotlib.ticker import FuncFormatter, PercentFormatter

    metrics, charts = data.actual_metrics, {}
    dates = pd.to_datetime(data.daily["date"])
    scope = "FULL DATA · 4,850,000 store-product-days · 50,000 series · 97 days"

    figure, axes = plt.subplots(
        2,
        1,
        figsize=(12, 8.4),
        sharex=True,
        gridspec_kw={"height_ratios": [1.15, 1], "hspace": 0.19},
    )
    figure.subplots_adjust(left=0.11, right=0.94, bottom=0.16, top=0.82)
    _heading(figure, "Observed sales & stockout exposure", scope)
    axes[0].plot(dates, data.daily["normalized_sales"], color=TEAL, linewidth=2.1)
    axes[0].fill_between(dates, data.daily["normalized_sales"], color=TEAL, alpha=0.08)
    axes[0].set_ylabel("Daily observed sales\n(normalized units)", labelpad=15)
    axes[0].set_ylim(bottom=0)
    axes[0].yaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x / 1000:,.0f}k"))
    axes[0].grid(axis="y")
    axes[1].plot(dates, data.daily["stockout_hour_rate"], color=RUST, linewidth=2.1)
    axes[1].fill_between(dates, data.daily["stockout_hour_rate"], color=RUST, alpha=0.08)
    mean_exposure = metrics["data"]["stockout_hour_rate"]
    axes[1].axhline(mean_exposure, color=NAVY, linewidth=1.2, linestyle="--")
    axes[1].text(
        0.025,
        0.91,
        f"Period average: {mean_exposure:.1%} of operating hours unavailable",
        transform=axes[1].transAxes,
        fontsize=12,
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.92, "pad": 4},
    )
    axes[1].set_ylabel("Unavailable operating\nhours (%)", labelpad=15)
    axes[1].set_ylim(0, max(data.daily["stockout_hour_rate"]) * 1.20)
    axes[1].yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    axes[1].grid(axis="y")
    ticks = pd.to_datetime(
        [
            "2024-03-28",
            "2024-04-15",
            "2024-05-01",
            "2024-05-15",
            "2024-06-01",
            "2024-06-15",
            "2024-07-02",
        ]
    )
    axes[1].set_xticks(ticks)
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    axes[1].set_xlim(dates.iloc[0], dates.iloc[-1])
    axes[1].set_xlabel("Historical observation date · 2024", labelpad=12)
    _note(
        figure,
        "Source: FreshRetailNet-50K (CC BY 4.0). Exposure denominator: 16 hours per series-day (06:00–22:00).\n"
        "Sales use the source's global normalization; they are neither physical units nor recovered lost demand.",
    )
    charts[FIGURES[0]] = {
        "files": _export(figure, output, FIGURES[0]),
        "data_rows": len(data.daily),
        "period": "2024-03-28–2024-07-02",
    }
    plt.close(figure)

    products = data.products
    crossing = metrics["concentration"]["products_for_80pct_observed_sales"]
    contribution = metrics["concentration"]["cumulative_share_at_crossing"]
    figure, axis = plt.subplots(figsize=(12, 8.4))
    figure.subplots_adjust(left=0.11, right=0.88, bottom=0.17, top=0.82)
    _heading(
        figure,
        f"{crossing} of {len(products):,} products contribute at least 80% of sales",
        "PRODUCT PARETO · All stores combined · Observed normalized sales · Mar 28–Jul 02, 2024",
    )
    axis.bar(products["rank"], products["normalized_sales"], color=NAVY, width=1.0, linewidth=0)
    axis.set_xlabel("Product rank by observed normalized sales (all 865 products)", labelpad=14)
    axis.set_ylabel("Sales per product\n(normalized units)", labelpad=15)
    axis.set_xlim(0, len(products) + 1)
    axis.set_ylim(bottom=0)
    axis.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x / 1000:,.0f}k"))
    axis.grid(axis="y")
    cumulative = axis.twinx()
    cumulative.spines["right"].set_visible(True)
    cumulative.plot(products["rank"], products["cumulative_share"], color=TEAL, linewidth=2.5)
    cumulative.set_ylim(0, 1.03)
    cumulative.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    cumulative.set_ylabel("Cumulative observed sales contribution (%)", labelpad=15)
    cumulative.axhline(0.8, color=GREY, linewidth=1.2, linestyle="--")
    cumulative.axvline(crossing, color=GREY, linewidth=1.2, linestyle="--")
    cumulative.scatter([crossing], [contribution], color=TEAL, s=70, zorder=4)
    cumulative.annotate(
        f"{crossing} products ({crossing / len(products):.1%})\n{contribution:.2%} cumulative contribution",
        xy=(crossing, contribution),
        xytext=(290, 0.55),
        fontsize=15,
        color=NAVY,
        arrowprops={"arrowstyle": "-", "color": GREY, "linewidth": 1.2},
        bbox={"facecolor": "white", "edgecolor": "none", "pad": 7},
    )
    axis.legend(
        [Line2D([0], [0], color=NAVY, linewidth=5), Line2D([0], [0], color=TEAL, linewidth=2.5)],
        ["Observed sales per product", "Cumulative contribution"],
        loc="upper left",
        bbox_to_anchor=(0, 1.12),
        ncol=2,
        frameon=False,
        fontsize=12,
    )
    _note(
        figure,
        "Source: FreshRetailNet-50K (CC BY 4.0). 865 encoded product IDs; globally normalized sales, not revenue.\n"
        "Product Pareto aggregates stores; the management queue's ABC classes apply at store-product level.",
    )
    charts[FIGURES[1]] = {
        "files": _export(figure, output, FIGURES[1]),
        "data_rows": len(products),
        "period": "2024-03-28–2024-07-02",
    }
    plt.close(figure)

    models = data.models
    ses = metrics["forecast"]["ses_alpha0.3"]["wape"]
    selector = metrics["forecast"]["per_series_selector"]["wape"]
    figure, axis = plt.subplots(figsize=(12, 8.4))
    figure.subplots_adjust(left=0.32, right=0.91, bottom=0.25, top=0.80)
    _heading(
        figure,
        f"Fixed SES: {ses:.1%} WAPE · Per-series selector: {selector:.1%}",
        "SAME UNTOUCHED HOLDOUT · Jun 26–Jul 02, 2024 · 350,000 observations · Lower WAPE is better",
    )
    model_colors = [NAVY, NAVY, NAVY, TEAL, RUST]
    positions = np.arange(len(models))
    bars = axis.barh(positions, models["wape"], color=model_colors, height=0.54)
    bars[-1].set_hatch("//")
    axis.set_yticks(positions, models["label"], fontsize=14)
    axis.invert_yaxis()
    axis.set_xlim(0, 0.50)
    axis.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    axis.set_xlabel("WAPE = total absolute forecast error / total observed sales (%)", labelpad=15)
    axis.grid(axis="x")
    axis.set_axisbelow(True)
    for index, row in models.iterrows():
        axis.text(
            row["wape"] + 0.009,
            index,
            f"{row['wape']:.2%}",
            va="center",
            fontsize=16,
            weight="bold" if index >= 3 else "normal",
        )
    figure.text(
        0.32,
        0.13,
        f"Selector is {(selector - ses) * 100:.2f} percentage points worse than fixed SES on this holdout.",
        fontsize=12.5,
        color=RUST,
    )
    _note(
        figure,
        "Source: FreshRetailNet-50K (CC BY 4.0). All 50,000 series; forecasts target observed sales, possibly stockout-censored.\n"
        "Selector uses pooled MAE from three 7-day training-period folds. The final holdout did not choose its models.",
    )
    charts[FIGURES[2]] = {
        "files": _export(figure, output, FIGURES[2]),
        "data_rows": len(models),
        "period": "2024-06-26–2024-07-02",
    }
    plt.close(figure)

    risk = data.risk
    figure, axis = plt.subplots(figsize=(12, 8.4))
    figure.subplots_adjust(left=0.11, right=0.91, bottom=0.20, top=0.78)
    _heading(
        figure,
        "Stockout risk needs a focused management queue",
        "ALL 50,000 STORE-PRODUCT SERIES · Recent 28 days: Jun 05–Jul 02, 2024 · No points sampled",
    )
    legend = []
    for name in ("Healthy", "Watch", "High Risk", "Critical"):
        subset = risk.loc[risk["availability_risk"].eq(name)]
        axis.scatter(
            subset["recent_sales_share"] * 100,
            subset["stockout_hour_rate"],
            color=RISK_COLORS[name],
            s=8,
            alpha=0.25,
            linewidths=0,
            rasterized=True,
        )
        legend.append(
            Line2D(
                [0],
                [0],
                marker="o",
                color="none",
                markerfacecolor=RISK_COLORS[name],
                markersize=7,
                label=f"{name}: {len(subset):,}",
            )
        )
    top20 = risk.nsmallest(20, "priority_rank")
    axis.scatter(
        top20["recent_sales_share"] * 100,
        top20["stockout_hour_rate"],
        facecolors="none",
        edgecolors=NAVY,
        s=58,
        linewidths=1.1,
        zorder=5,
    )
    legend.append(
        Line2D(
            [0],
            [0],
            marker="o",
            color="none",
            markeredgecolor=NAVY,
            markerfacecolor="none",
            markersize=8,
            label="Top 20 existing priority ranks",
        )
    )
    # Log coordinates reveal the long tail; a symlog fallback preserves zeros.
    if risk["recent_sales_share"].gt(0).all():
        axis.set_xscale("log")
    else:
        axis.set_xscale("symlog", linthresh=0.0001)
    axis.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:g}%"))
    axis.set_ylabel("Unavailable operating hours (%)", labelpad=14)
    axis.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    axis.set_ylim(-0.015, 1)
    axis.set_xlabel(
        "Recent observed sales contribution per store-product series (%; log scale)", labelpad=14
    )
    axis.grid(axis="y")
    for threshold, label in ((0.10, "High Risk threshold: 10%"), (0.25, "Critical threshold: 25%")):
        axis.axhline(threshold, color=GREY, linewidth=1.1, linestyle="--")
        axis.text(
            0.99,
            threshold + 0.012,
            label,
            transform=axis.get_yaxis_transform(),
            ha="right",
            fontsize=11,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.9, "pad": 2},
        )
    axis.legend(
        handles=legend,
        loc="upper left",
        bbox_to_anchor=(0, 1.14),
        ncol=3,
        frameon=False,
        fontsize=11,
        handletextpad=0.45,
        columnspacing=1.4,
    )
    hp = metrics["risk"]["high_priority_series"]
    share = metrics["risk"]["high_priority_recent_sales_share"]
    _note(
        figure,
        f"{hp:,} Critical / High Risk series account for {share:.1%} of recent observed sales. Source: FreshRetailNet-50K (CC BY 4.0).\n"
        "Exposure = unavailable hours / (28 × 16 hours). Sales add business context; existing risk rules and severity ranks are unchanged.",
    )
    charts[FIGURES[3]] = {
        "files": _export(figure, output, FIGURES[3]),
        "data_rows": len(risk),
        "period": "2024-06-05–2024-07-02",
        "sampled": False,
        "highlight": "Existing priority ranks 1–20; risk definitions unchanged",
    }
    plt.close(figure)

    bands = data.zero_sales
    with_stockout = metrics["data"]["zero_sales_with_stockout"]
    all_zero = metrics["data"]["zero_sales_days"]
    coincidence = with_stockout / all_zero
    figure, (axis, composition) = plt.subplots(
        2, 1, figsize=(12, 8.4), gridspec_kw={"height_ratios": [3.1, 1], "hspace": 0.34}
    )
    figure.subplots_adjust(left=0.12, right=0.94, bottom=0.19, top=0.81)
    _heading(
        figure,
        f"{coincidence:.1%} of zero-sales days also had stockout exposure",
        "AVAILABILITY & ZERO SALES · Full 4,850,000-day cohort · Mar 28–Jul 02, 2024 · Association, not causation",
    )
    x = np.arange(len(bands))
    axis.bar(x, bands["zero_sales_rate"], color=[NAVY] * 5 + [RUST], width=0.62)
    axis.set_ylim(0, 1)
    axis.set_yticks(np.arange(0, 1.01, 0.25))
    axis.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    axis.set_ylabel("Zero-sales rate\nwithin exposure band (%)", labelpad=15)
    labels = [
        f"{row.stockout_hours_band} hours\nn = {row.observed_days:,}" for row in bands.itertuples()
    ]
    axis.set_xticks(x, labels, fontsize=11.5)
    axis.grid(axis="y")
    axis.set_axisbelow(True)
    for index, row in bands.iterrows():
        axis.text(
            index,
            row["zero_sales_rate"] + 0.035,
            f"{row['zero_sales_rate']:.1%}",
            ha="center",
            va="bottom",
            fontsize=14,
            weight="bold",
        )
    composition.barh([0], [coincidence], color=RUST, height=0.45)
    composition.barh([0], [1 - coincidence], left=[coincidence], color=NAVY, height=0.45)
    composition.text(
        coincidence / 2,
        0,
        f"With exposure\n{with_stockout:,} days",
        ha="center",
        va="center",
        color="white",
        fontsize=12,
    )
    composition.text(
        coincidence + (1 - coincidence) / 2,
        0,
        f"No exposure\n{all_zero - with_stockout:,} days",
        ha="center",
        va="center",
        color="white",
        fontsize=12,
    )
    composition.set_title(f"Among all {all_zero:,} zero-sales days", loc="left", fontsize=13, pad=9)
    composition.set_xlim(0, 1)
    composition.set_ylim(-0.30, 0.30)
    composition.set_yticks([])
    composition.set_xticks([0, 0.5, 1])
    composition.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    for spine in composition.spines.values():
        spine.set_visible(False)
    _note(
        figure,
        "Source: FreshRetailNet-50K (CC BY 4.0). n denotes store-product-days in each band; every day has 16 exposure hours.\n"
        "The conditional rates and zero-day composition have different denominators. Neither estimates lost demand.",
    )
    charts[FIGURES[4]] = {
        "files": _export(figure, output, FIGURES[4]),
        "data_rows": len(bands),
        "period": "2024-03-28–2024-07-02",
    }
    plt.close(figure)
    frames = [data.daily, data.products, data.models, data.risk, data.zero_sales]
    for name, frame in zip(FIGURES, frames, strict=True):
        charts[name]["data_sha256"] = hashlib.sha256(frame.to_csv(index=False).encode()).hexdigest()
        charts[name]["png_dimensions"] = [1800, 1260]
    return charts


def build_visualizations(database: Path, findings_path: Path, output: Path, manifest: Path) -> dict:
    findings = json.loads(findings_path.read_text())
    data = load_chart_data(database, findings)
    charts = render_figures(data, output)
    report = {
        "scope": "full dataset; all 50,000 store-product series; not the 200-series demo",
        "source": {
            "dataset": "FreshRetailNet-50K",
            "license": "CC BY 4.0",
            "url": data.metadata["source_url"],
            "revision": data.metadata["source_revision"],
        },
        "units": "globally normalized observed sales; not physical units, revenue, or recovered demand",
        "build_command": "uv run --extra viz python scripts/build_visualizations.py",
        "findings_sha256": hashlib.sha256(findings_path.read_bytes()).hexdigest(),
        "metrics": data.actual_metrics,
        "charts": charts,
        "verification": {
            "all_full_data_metrics_reconcile_with_saved_findings": True,
            "fixed_baseline_wape_recomputed_from_90_day_source_histories": True,
            "selector_wape_recomputed_from_actual_and_prediction_rows": True,
            "all_97_dates_all_865_products_all_50000_series_included": True,
            "risk_definitions_unchanged": True,
            "risk_axes_and_classes_recomputed_from_daily_facts": True,
            "existing_priority_ranks_reconciled": True,
        },
    }
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return report
