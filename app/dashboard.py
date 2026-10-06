"""Business review of real retail sales, availability exposure and planning assumptions."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from scdi.scenarios import evaluate_scenario

ROOT = Path(__file__).resolve().parents[1]
BLUE = "#245b93"
TEAL = "#126b72"
RISK_COLORS = {
    "Critical": "#a63838",
    "High Risk": "#bf6c31",
    "Watch": "#b49232",
    "Healthy": TEAL,
    "Review": "#72849a",
}


def resolve_database(root: Path = ROOT) -> Path:
    """Prefer the full reproducible build, then the committed source-data demonstration."""
    override = os.environ.get("SCDI_DATABASE")
    candidates = (
        [Path(override)]
        if override
        else [
            root / "data/processed/decision_intelligence.sqlite",
            root / "data/demo/decision_intelligence.sqlite",
        ]
    )
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError("No analytics database found. Run the documented processing pipeline.")


@st.cache_data(show_spinner=False)
def query_database(path: str, modified: float, query: str, params: tuple = ()) -> pd.DataFrame:
    """Read a SQLite result; file timestamp invalidates cached results after a rebuild."""
    with sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro", uri=True) as connection:
        return pd.read_sql_query(query, connection, params=params)


def read_metadata(path: Path) -> dict[str, Any]:
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master")}
        if "metadata" not in tables:
            return {}
        values = connection.execute("SELECT key, value FROM metadata").fetchall()
    result = {}
    for key, value in values:
        try:
            result[key] = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            result[key] = value
    return result


def scope_clause(city: Any = None, category: Any = None) -> tuple[str, tuple]:
    """Only fixed identifiers enter SQL; filter values remain parameterized."""
    conditions, params = [], []
    for field, value in [("city_id", city), ("category_id", category)]:
        if value is not None:
            conditions.append(f"{field} = ?")
            params.append(value)
    return (" WHERE " + " AND ".join(conditions) if conditions else ""), tuple(params)


def forecast_metrics(predictions: pd.DataFrame) -> dict[str, float | None]:
    """Pooled WAPE and bias weight actual demand, avoiding means of series ratios."""
    values = predictions[["actual", "prediction"]].dropna()
    denominator = values["actual"].abs().sum()
    if values.empty:
        return {"wape": None, "bias": None, "mae": None}
    errors = values["prediction"] - values["actual"]
    return {
        "wape": float(errors.abs().sum() / denominator) if denominator else None,
        "bias": float(errors.sum() / denominator) if denominator else None,
        "mae": float(errors.abs().mean()),
    }


def style_chart(fig: go.Figure, height: int = 360) -> go.Figure:
    fig.update_layout(
        template="plotly_white",
        height=height,
        margin=dict(l=15, r=15, t=35, b=15),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#142b43", size=13),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        hovermode="x unified",
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#e5ebf0")
    return fig


def render_dashboard() -> None:
    st.set_page_config(
        page_title="Supply Chain Decision Intelligence", page_icon="📦", layout="wide"
    )
    st.markdown(
        """<style>
        .block-container{padding-top:3.7rem;padding-bottom:3rem;max-width:1480px}
        h1{font-weight:650;letter-spacing:-.035em;line-height:1.12}
        h2,h3{letter-spacing:-.02em}
        [data-testid="stMetric"]{background:white;border:1px solid #e0e7ee;
          padding:1.1rem 1.25rem;border-radius:8px}
        [data-testid="stMetricLabel"]{color:#61768b;font-size:.85rem}
        [data-testid="stMetricValue"]{font-variant-numeric:tabular-nums;font-size:1.9rem}
        .review-kicker{color:#126b72;font-size:.72rem;font-weight:700;
          letter-spacing:.16em;margin-bottom:.6rem}
        .evidence-line{border-left:3px solid #126b72;padding:.75rem 1rem;
          color:#52677c;background:white;margin:.7rem 0 1.7rem;font-size:.9rem}
        [data-testid="stSidebar"]{border-right:1px solid #e0e7ee}
        </style>""",
        unsafe_allow_html=True,
    )
    try:
        database = resolve_database()
    except FileNotFoundError as error:
        st.error(str(error))
        st.stop()
    stamp = database.stat().st_mtime

    def query(sql: str, params: tuple = ()) -> pd.DataFrame:
        return query_database(str(database), stamp, sql, params)

    summary = query("SELECT * FROM series_summary ORDER BY series_id")
    metadata = read_metadata(database)
    st.sidebar.markdown("### Review scope")
    cities = sorted(summary["city_id"].dropna().unique().tolist())
    city = st.sidebar.selectbox(
        "City ID", [None, *cities], format_func=lambda x: "All cities" if x is None else str(x)
    )
    candidates = summary if city is None else summary[summary["city_id"] == city]
    categories = sorted(candidates["category_id"].dropna().unique().tolist())
    category = st.sidebar.selectbox(
        "Category ID",
        [None, *categories],
        format_func=lambda x: "All categories" if x is None else str(x),
    )
    selected = candidates if category is None else candidates[candidates["category_id"] == category]
    if selected.empty:
        st.info("No series match the selected scope.")
        st.stop()
    selected = selected.copy()
    clause, params = scope_clause(city, category)
    scope = "SELECT series_id FROM series_summary" + clause
    daily_scope = f"SELECT * FROM daily_sales WHERE series_id IN ({scope})"
    overview = query(
        "SELECT COUNT(*) AS rows, COUNT(DISTINCT store_id) AS stores, "
        "COUNT(DISTINCT product_id) AS products, MIN(date) AS first_date, MAX(date) AS last_date, "
        "SUM(stockout_hours) / (COUNT(*) * 16.0) AS stockout_hour_rate, "
        "AVG(CASE WHEN stockout_hours > 0 THEN 1.0 ELSE 0 END) AS stockout_day_rate "
        f"FROM ({daily_scope})",
        params,
    ).iloc[0]
    accuracy = query(
        "SELECT SUM(ABS(prediction-actual)) / NULLIF(SUM(ABS(actual)),0) AS wape "
        f"FROM forecast_values WHERE split='holdout' AND series_id IN ({scope})",
        params,
    ).iloc[0]["wape"]
    st.sidebar.caption(f"{len(selected):,} store–product series in the current view")
    demo_scope = metadata.get("scope") == "demo"
    if demo_scope:
        st.sidebar.info(
            "Source-data demonstration subset. Counts and findings on this page describe the selected subset."
        )
    else:
        st.sidebar.caption("Full processed source data")
    st.sidebar.markdown(
        "[Dataset source](https://huggingface.co/datasets/Dingdong-Inc/FreshRetailNet-50K)"
    )
    st.sidebar.caption("IDs are anonymized. Sales are normalized, not physical units or revenue.")

    st.markdown(
        '<div class="review-kicker">SUPPLY CHAIN • DECISION REVIEW</div>', unsafe_allow_html=True
    )
    st.title("Supply Chain Decision Intelligence")
    st.write(
        "Find recurring availability exposure, compare forecasts, and test transparent replenishment assumptions."
    )
    st.markdown(
        '<div class="evidence-line">Real source: FreshRetailNet-50K daily sales and stockout observations. '
        "Planning scenarios use explicit assumptions; actual inventory, procurement and supplier records are unavailable.</div>",
        unsafe_allow_html=True,
    )
    st.caption(
        f"CURRENT VIEW  ·  {overview['first_date']} → {overview['last_date']}  ·  {len(selected):,} series"
    )
    tabs = st.tabs(
        [
            "Executive Overview",
            "Demand",
            "Availability Risk",
            "Forecasts",
            "Planning Scenarios",
            "Data Quality",
        ]
    )

    ids = selected["series_id"].astype(str).tolist()
    with tabs[0]:
        columns = st.columns(5)
        columns[0].metric("Daily observations", f"{overview['rows']:,.0f}")
        columns[1].metric(
            "Stores / products", f"{overview['stores']:,.0f} / {overview['products']:,.0f}"
        )
        columns[2].metric("Stockout exposure", f"{overview['stockout_hour_rate']:.1%}")
        attention = selected["availability_risk"].isin(["Critical", "High Risk"]).sum()
        columns[3].metric("Series requiring review", f"{attention:,}")
        columns[4].metric(
            "Holdout pooled WAPE", "Unavailable" if pd.isna(accuracy) else f"{accuracy:.1%}"
        )
        st.caption(
            f"Days with stockouts: {overview['stockout_day_rate']:.1%}. Stockout exposure uses the full displayed history and 16 operating hours per day. Priority rules use the latest 28 days of observed availability, not current inventory."
        )
        left, right = st.columns([1.8, 1])
        with left:
            st.subheader("Where management attention is needed")
            risks = (
                selected["availability_risk"]
                .value_counts()
                .rename_axis("Risk")
                .reset_index(name="Series")
            )
            chart = px.bar(
                risks,
                x="Risk",
                y="Series",
                color="Risk",
                color_discrete_map=RISK_COLORS,
                category_orders={"Risk": ["Critical", "High Risk", "Watch", "Healthy"]},
            )
            chart.update_layout(showlegend=False)
            st.plotly_chart(style_chart(chart, 290), width="stretch")
        with right:
            st.subheader("Decision brief")
            st.write(
                "**1. Investigate repeated stockout exposure.** Review availability patterns and operational causes for the highest-priority store–product series."
            )
            st.write(
                "**2. Account for censored demand.** Sales during unavailable hours understate customer demand; forecasts estimate observed sales."
            )
            st.write(
                "**3. Test before replenishing.** Use the scenario tab to evaluate assumed lead times and service targets; obtain real inventory positions before ordering."
            )
        st.subheader("Priority queue")
        display_recommendations(selected, key="overview")

    with tabs[1]:
        st.subheader("How does observed sales volume change?")
        trend = query(
            "SELECT date, SUM(sales) AS observed_sales, "
            "SUM(stockout_hours) / (COUNT(*) * 16.0) AS stockout_hour_rate "
            f"FROM ({daily_scope}) GROUP BY date ORDER BY date",
            params,
        )
        trend["date"] = pd.to_datetime(trend["date"])
        fig = px.line(trend, x="date", y="observed_sales", color_discrete_sequence=[BLUE])
        fig.update_yaxes(title="Observed sales · normalized scale")
        st.plotly_chart(style_chart(fig), width="stretch")
        left, right = st.columns(2)
        with left:
            st.subheader("Sales concentration by category")
            category_volume = selected.groupby("category_id", as_index=False)[
                "observed_sales_total"
            ].sum()
            fig = px.bar(
                category_volume,
                x="category_id",
                y="observed_sales_total",
                color_discrete_sequence=[TEAL],
            )
            fig.update_xaxes(type="category", title="Category ID")
            fig.update_yaxes(title="Observed sales · normalized scale")
            st.plotly_chart(style_chart(fig, 310), width="stretch")
        with right:
            st.subheader("Demand variability")
            variability = (
                selected["xyz_class"]
                .value_counts()
                .rename_axis("XYZ class")
                .reset_index(name="Series")
            )
            fig = px.bar(variability, x="XYZ class", y="Series", color_discrete_sequence=[BLUE])
            st.plotly_chart(style_chart(fig, 310), width="stretch")
        st.caption(
            "Category concentration uses the full displayed history; XYZ uses the latest 28 days of observed normalized sales. Neither measures revenue, unit consumption value or unconstrained demand."
        )

    with tabs[2]:
        st.subheader("Which series combine sales volume and availability exposure?")
        st.caption(
            "Priority window: latest 28 days · Critical ≥25% unavailable hours; High Risk ≥10%; remaining exposure, sales CV >1 or zero observed mean = Watch; otherwise Healthy. XYZ is Unknown when the observed mean is zero."
        )
        fig = px.scatter(
            selected,
            x="observed_mean_sales",
            y="stockout_hour_rate",
            color="availability_risk",
            hover_data=["series_id", "store_id", "product_id", "xyz_class"],
            color_discrete_map=RISK_COLORS,
            opacity=0.75,
        )
        fig.update_xaxes(title="Mean observed daily sales · normalized scale")
        fig.update_yaxes(title="Unavailable operating hours", tickformat=".0%")
        st.plotly_chart(style_chart(fig, 400), width="stretch")
        st.subheader("Recommended management actions")
        display_recommendations(selected, key="risk")
        st.caption(
            "This queue cannot identify current stock, reorder quantities or excess inventory. Those decisions need on-hand stock, open orders and measured lead times."
        )

    with tabs[3]:
        st.subheader("Time-validated observed-sales forecasts")
        choice = st.selectbox("Store–product series", ids, key="forecast_series")
        history = query(
            "SELECT date, sales, stockout_hours FROM daily_sales WHERE series_id = ? ORDER BY date",
            (choice,),
        )
        forecasts = query(
            "SELECT * FROM forecast_values WHERE series_id = ? ORDER BY date", (choice,)
        )
        scores = query("SELECT * FROM forecast_scores WHERE series_id = ?", (choice,))
        holdout = forecasts[forecasts["split"] == "holdout"].copy()
        future = forecasts[forecasts["split"] == "future"].copy()
        metrics = forecast_metrics(holdout)
        columns = st.columns(3)
        columns[0].metric(
            "Holdout WAPE", "Unavailable" if metrics["wape"] is None else f"{metrics['wape']:.1%}"
        )
        columns[1].metric(
            "Holdout bias", "Unavailable" if metrics["bias"] is None else f"{metrics['bias']:+.1%}"
        )
        model = str(forecasts["selected_model"].iloc[0]) if len(forecasts) else "Unavailable"
        columns[2].metric("Selected model", model.replace("_", " ").title())
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=history["date"], y=history["sales"], name="Observed sales", line=dict(color=BLUE)
            )
        )
        if not holdout.empty:
            fig.add_trace(
                go.Scatter(
                    x=holdout["date"],
                    y=holdout["prediction"],
                    name="Holdout prediction · scored",
                    line=dict(color=TEAL, dash="dash"),
                )
            )
        if not future.empty:
            fig.add_trace(
                go.Scatter(
                    x=future["date"],
                    y=future["prediction"],
                    name="Future forecast · unscored",
                    line=dict(color="#b49232", dash="dot"),
                )
            )
        fig.update_yaxes(title="Observed sales · normalized scale")
        st.plotly_chart(style_chart(fig, 410), width="stretch")
        st.caption(
            "Models are selected using historical rolling windows before the holdout. The holdout is evaluated once; future forecasts have no observed outcomes. Forecasts target observed sales, not latent customer demand."
        )
        with st.expander("Review holdout observations and score details"):
            st.dataframe(holdout, width="stretch", hide_index=True)
            st.dataframe(scores, width="stretch", hide_index=True)

    with tabs[4]:
        st.subheader("What inventory target follows from your assumptions?")
        st.write(
            "Scenario output is an illustrative target on the dataset’s normalized sales scale. Observed mean and variability use the latest 28 days; inputs below are assumptions, not source inventory or supplier data."
        )
        choice = st.selectbox("Scenario series", ids, key="scenario_series")
        item = selected.loc[selected["series_id"].astype(str) == choice].iloc[0]
        baselines = {"Recent observed daily sales": float(item["observed_mean_sales"])}
        if "forecast_daily_sales" in item and pd.notna(item["forecast_daily_sales"]):
            baselines["Refit future daily sales estimate"] = float(item["forecast_daily_sales"])
        baseline = st.selectbox("Demand baseline", list(baselines), key="scenario_baseline")
        mean_sales = baselines[baseline]
        st.caption(
            f"Baseline mean: {mean_sales:.3f} normalized sales per day. Variability remains the latest 28-day observed sample standard deviation."
        )
        columns = st.columns(3)
        lead = columns[0].number_input(
            "Assumed mean lead time · days", min_value=0.0, value=3.0, step=0.5
        )
        lead_std = columns[1].number_input(
            "Assumed lead-time standard deviation · days", min_value=0.0, value=1.0, step=0.25
        )
        service = columns[2].selectbox(
            "Assumed service target",
            [0.90, 0.95, 0.97, 0.99],
            index=1,
            format_func=lambda x: f"{x:.0%}",
        )
        columns = st.columns(2)
        shock = columns[0].slider(
            "Assumed demand change · %", min_value=-50, max_value=100, value=0, step=10
        )
        inventory = columns[1].number_input(
            "Assumed inventory position · normalized scale", min_value=0.0, value=0.0, step=0.1
        )
        try:
            scenario = evaluate_scenario(
                mean_sales,
                float(item["observed_std_sales"]),
                lead_time_days=lead,
                lead_time_std_days=lead_std,
                service_level=service,
                demand_shock_pct=shock,
                inventory_position=inventory,
            ).to_dict()
        except ValueError as error:
            scenario = None
            if lead == 0 and lead_std > 0:
                st.warning(
                    "A zero mean lead time requires zero lead-time variability. Adjust the lead-time assumptions."
                )
            elif mean_sales == 0 and float(item["observed_std_sales"]) > 0:
                st.warning(
                    "A zero sales baseline cannot have positive variability in this planning model. Select the recent observed baseline or another series."
                )
            else:
                st.warning(f"These assumptions cannot be evaluated: {error}")
        if scenario is not None:
            columns = st.columns(3)
            columns[0].metric("Illustrative safety stock", f"{scenario['safety_stock']:.3f}")
            columns[1].metric("Illustrative reorder point", f"{scenario['reorder_point']:.3f}")
            columns[2].metric("Hypothetical order gap", f"{scenario['hypothetical_order_gap']:.3f}")
            comparison = []
            for level in [0.90, 0.95, 0.97, 0.99]:
                result = evaluate_scenario(
                    mean_sales,
                    float(item["observed_std_sales"]),
                    lead_time_days=lead,
                    lead_time_std_days=lead_std,
                    service_level=level,
                    demand_shock_pct=shock,
                    inventory_position=inventory,
                ).to_dict()
                comparison.append(
                    {
                        "Service target": f"{level:.0%}",
                        "Safety stock": result["safety_stock"],
                        "Reorder point": result["reorder_point"],
                    }
                )
            fig = px.bar(
                pd.DataFrame(comparison),
                x="Service target",
                y=["Safety stock", "Reorder point"],
                barmode="group",
                color_discrete_sequence=[BLUE, TEAL],
            )
            fig.update_yaxes(title="Illustrative inventory target · normalized scale")
            st.plotly_chart(style_chart(fig, 320), width="stretch")
            st.caption(
                "Assumes independent daily demand and lead times, a normal approximation and stationary demand. Stockout censoring and only 97 days of source history limit policy conclusions. No order is created."
            )
            with st.expander("Calculation inputs and outputs"):
                st.json(scenario)

    with tabs[5]:
        st.subheader("Data boundaries and quality evidence")
        st.write(
            "FreshRetailNet-50K provides anonymized daily store–product sales, hierarchical product IDs and hourly stock status. Monetary, procurement, physical inventory and supplier fields are absent."
        )
        quality = query(
            "SELECT SUM(CASE WHEN sales < 0 THEN 1 ELSE 0 END) AS negative_sales, "
            "SUM(CASE WHEN stockout_hours < 0 OR stockout_hours > 16 THEN 1 ELSE 0 END) AS invalid_stockout_hours, "
            "SUM(CASE WHEN series_id IS NULL OR date IS NULL THEN 1 ELSE 0 END) AS missing_keys "
            f"FROM ({daily_scope})",
            params,
        )
        st.dataframe(quality.T.rename(columns={0: "Records in current view"}), width="stretch")
        st.write(
            "The reproducible pipeline validates keys, date coverage, hourly array lengths and sales values. Meaningful exclusions and source anomalies are recorded in the repository data-quality report."
        )
        with st.expander("Database provenance and build metadata"):
            st.json(metadata)
        st.markdown(
            "[Source dataset card and license](https://huggingface.co/datasets/Dingdong-Inc/FreshRetailNet-50K)"
        )


def display_recommendations(summary: pd.DataFrame, key: str) -> None:
    ordered = summary.sort_values("priority_rank")
    columns = [
        "priority_rank",
        "series_id",
        "availability_risk",
        "stockout_hour_rate",
        "forecast_next7_sales",
        "observed_mean_sales",
        "volume_abc_class",
        "xyz_class",
        "recommendation",
        "reason",
    ]
    columns = [column for column in columns if column in ordered.columns]
    display = ordered[columns].head(500).copy()
    display["stockout_hour_rate"] *= 100
    st.dataframe(
        display,
        hide_index=True,
        width="stretch",
        column_config={
            "priority_rank": st.column_config.NumberColumn("Priority", format="%d"),
            "series_id": st.column_config.TextColumn("Store : product"),
            "availability_risk": st.column_config.TextColumn("Review status"),
            "stockout_hour_rate": st.column_config.NumberColumn(
                "Unavailable hours", format="%.1f%%"
            ),
            "forecast_next7_sales": st.column_config.NumberColumn(
                "Next 7-day sales", format="%.2f"
            ),
            "observed_mean_sales": st.column_config.NumberColumn("Mean daily sales", format="%.2f"),
            "volume_abc_class": st.column_config.TextColumn("ABC sales tier"),
            "xyz_class": st.column_config.TextColumn("XYZ sales group"),
            "recommendation": st.column_config.TextColumn("Recommended action", width="large"),
            "reason": st.column_config.TextColumn("Reason", width="large"),
        },
    )
    if len(ordered) > 500:
        st.caption("Showing the first 500 priorities. Download includes the entire selected scope.")
    st.caption(
        "Forecasts estimate normalized observed sales for the next seven days. Volume ABC classes retain the pipeline cohort classification; filtering does not reclassify them."
    )
    st.download_button(
        "Download management recommendations",
        ordered.to_csv(index=False).encode(),
        "management_recommendations.csv",
        "text/csv",
        key=f"download_{key}",
    )


if __name__ == "__main__":
    render_dashboard()
