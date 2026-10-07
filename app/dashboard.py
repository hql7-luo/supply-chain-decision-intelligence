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
from plotly.subplots import make_subplots

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
RISK_ORDER = ["Critical", "High Risk", "Watch", "Healthy"]
MODEL_LABELS = {
    "naive": "Naive",
    "seasonal_naive7": "Seasonal naive · 7 days",
    "mean28": "Moving average · 28 days",
    "ses_alpha0.3": "SES · α = 0.3",
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
        margin=dict(l=12, r=20, t=52, b=35),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#142b43", size=12),
        legend=dict(orientation="h", yanchor="bottom", y=1.04, x=0, font=dict(size=11)),
        hovermode="x unified",
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#e5ebf0")
    return fig


def chart_html(fig: go.Figure) -> bytes:
    """Self-contained export uses the same figure displayed on screen."""
    return fig.to_html(full_html=True, include_plotlyjs=True).encode("utf-8")


def display_chart(fig: go.Figure, data: pd.DataFrame, key: str) -> None:
    """Keep chart, image export and underlying data together; generate files on demand."""
    st.plotly_chart(
        fig,
        width="stretch",
        key=f"chart_{key}",
        config={
            "displaylogo": False,
            "responsive": True,
            "toImageButtonOptions": {"format": "png", "filename": key, "scale": 2},
        },
    )
    with st.expander("Download chart or underlying data"):
        columns = st.columns(2)
        columns[0].download_button(
            "Interactive chart · HTML",
            lambda: chart_html(fig),
            f"{key}.html",
            "text/html",
            key=f"html_{key}",
            on_click="ignore",
        )
        columns[1].download_button(
            "Chart data · CSV",
            lambda: data.to_csv(index=False).encode("utf-8"),
            f"{key}.csv",
            "text/csv",
            key=f"csv_{key}",
            on_click="ignore",
        )
        st.caption("Use the camera icon above the chart to save a PNG. HTML opens offline.")


def management_queue(
    summary: pd.DataFrame, statuses: list[str], sort_by: str, limit: int
) -> pd.DataFrame:
    """Limit review workload without changing saved risk definitions or priority ranks."""
    matching = summary[summary["availability_risk"].isin(statuses)]
    fields = {
        "Original management priority": (["priority_rank", "series_id"], [True, True]),
        "Highest observed sales": (
            ["observed_sales_total", "priority_rank", "series_id"],
            [False, True, True],
        ),
        "Highest stockout exposure": (
            ["stockout_hour_rate", "priority_rank", "series_id"],
            [False, True, True],
        ),
    }
    columns, ascending = fields[sort_by]
    return matching.sort_values(columns, ascending=ascending, kind="stable").head(limit).copy()


def demand_trend_figure(trend: pd.DataFrame) -> go.Figure:
    """Aligned panels keep normalized sales and availability percentages on their own scales."""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.12)
    fig.add_trace(
        go.Scatter(
            x=trend["date"],
            y=trend["observed_sales"],
            name="Observed sales",
            line=dict(color=BLUE, width=2.5),
            hovertemplate="%{y:,.2f} normalized sales<extra></extra>",
        ),
        row=1,
        col=1,
    )
    for field, label, color, dash in [
        ("stockout_hour_rate", "Operating hours unavailable", "#bf6c31", "solid"),
        ("stockout_day_rate", "Days with stockouts", "#a63838", "dot"),
    ]:
        fig.add_trace(
            go.Scatter(
                x=trend["date"],
                y=trend[field],
                name=label,
                line=dict(color=color, dash=dash, width=2),
                hovertemplate="%{y:.1%}<extra>" + label + "</extra>",
            ),
            row=2,
            col=1,
        )
    fig.update_yaxes(title_text="Normalized sales", rangemode="tozero", row=1, col=1)
    fig.update_yaxes(
        title_text="Stockout exposure", tickformat=".0%", rangemode="tozero", row=2, col=1
    )
    fig.update_xaxes(title_text="Observation date", row=2, col=1)
    return style_chart(fig, 440)


def forecast_figure(
    history: pd.DataFrame, forecasts: pd.DataFrame, show_full_history: bool
) -> tuple[go.Figure, pd.DataFrame]:
    """Show the scored period against actual sales and observed availability."""
    history = history.copy()
    forecasts = forecasts.copy()
    history["date"] = pd.to_datetime(history["date"])
    forecasts["date"] = pd.to_datetime(forecasts["date"])
    if not show_full_history:
        history = history[history["date"] >= history["date"].max() - pd.Timedelta(days=27)]
    holdout = forecasts[forecasts["split"] == "holdout"]
    future = forecasts[forecasts["split"] == "future"]
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25], vertical_spacing=0.12
    )
    fig.add_trace(
        go.Scatter(
            x=history["date"],
            y=history["sales"],
            name="Actual observed sales",
            line=dict(color=BLUE, width=2),
            hovertemplate="%{y:.3f} normalized sales<extra>Actual observed sales</extra>",
        ),
        row=1,
        col=1,
    )
    for part, label, color, dash in [
        (holdout, "Holdout prediction · scored", TEAL, "dash"),
        (future, "Next 7 days · unscored", "#b49232", "dot"),
    ]:
        if part.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=part["date"],
                y=part["prediction"],
                name=label,
                mode="lines+markers",
                line=dict(color=color, dash=dash, width=2.5),
                marker=dict(size=6),
                hovertemplate="%{y:.3f} normalized sales<extra>" + label + "</extra>",
            ),
            row=1,
            col=1,
        )
        fig.add_vrect(
            x0=part["date"].min() - pd.Timedelta(hours=12),
            x1=part["date"].max() + pd.Timedelta(hours=12),
            fillcolor=color,
            opacity=0.06,
            line_width=0,
        )
    fig.add_trace(
        go.Bar(
            x=history["date"],
            y=history["stockout_hours"],
            name="Stockout hours · observed",
            marker_color="#bf6c31",
            opacity=0.65,
            hovertemplate="%{y:.0f} of 16 hours unavailable<extra></extra>",
        ),
        row=2,
        col=1,
    )
    fig.update_yaxes(title_text="Normalized sales", rangemode="tozero", row=1, col=1)
    fig.update_yaxes(title_text="Stockout hours", range=[0, 16], row=2, col=1)
    fig.update_xaxes(title_text="Observation / historical forecast date", row=2, col=1)
    exported = history.merge(
        forecasts[["date", "prediction", "split", "selected_model"]],
        on="date",
        how="outer",
    ).sort_values("date")
    exported["prediction_error"] = exported["prediction"] - exported["sales"]
    return style_chart(fig, 490), exported


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
        [data-testid="stMetricLabel"] p{white-space:normal}
        [data-testid="stTabs"] button p{font-size:.9rem}
        @media(max-width:760px){
          .block-container{padding:3.2rem 1rem 2rem}
          h1{font-size:2.1rem!important}
          [data-testid="stHorizontalBlock"]{flex-wrap:wrap;gap:.7rem}
          [data-testid="stColumn"]{min-width:100%!important;flex:1 1 100%!important}
          [data-testid="stMetric"]{padding:.8rem 1rem}
          [data-testid="stMetricValue"]{font-size:1.6rem}
        }
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
            f"Source-data demonstration subset: {metadata.get('series', len(summary)):,} real series. "
            "Counts and findings on this page describe the selected subset."
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
        "Analyze observed retail sales, identify recurring stockout exposure, and turn evidence into a focused management review."
    )
    st.markdown(
        '<div class="evidence-line">Real source: FreshRetailNet-50K daily sales and stockout observations. '
        "Planning scenarios use explicit assumptions; actual inventory, procurement and supplier records are unavailable.</div>",
        unsafe_allow_html=True,
    )
    st.caption(
        f"CURRENT VIEW · {overview['first_date']} → {overview['last_date']} · {len(selected):,} series · "
        f"{overview['rows']:,.0f} daily observations · {overview['stores']:,.0f} stores / {overview['products']:,.0f} products"
    )
    if demo_scope:
        st.info(
            f"Real-data Demo · {len(summary):,} store–product series / "
            f"{metadata.get('rows', overview['rows']):,.0f} daily observations before filters. "
            "This is a selected subset, not the full 4.85 million observations; its metrics are not population conclusions."
        )
    st.sidebar.markdown("### Start with the evidence")
    st.sidebar.caption(
        "1. Overview: choose a review workload.\n\n"
        "2. Demand / Risk: locate exposure and sales patterns.\n\n"
        "3. Forecasts: compare actuals before testing assumptions."
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

    ids = selected.sort_values("priority_rank")["series_id"].astype(str).tolist()
    with tabs[0]:
        columns = st.columns(4)
        columns[0].metric(
            "Days with stockouts",
            f"{overview['stockout_day_rate']:.1%}",
            help="Share of store–product days with at least one unavailable operating hour across the displayed history.",
        )
        columns[1].metric(
            "Operating hours unavailable",
            f"{overview['stockout_hour_rate']:.1%}",
            help="Unavailable operating hours / (daily observations × 16 hours). This does not measure current inventory.",
        )
        attention = selected["availability_risk"].isin(["Critical", "High Risk"]).sum()
        columns[2].metric(
            "Series requiring review",
            f"{attention:,}",
            help="Critical + High Risk under the unchanged latest-28-day availability rules. Top 20 / 50 below sets review capacity, not new risk classes.",
        )
        columns[3].metric(
            "Holdout pooled WAPE",
            "Unavailable" if pd.isna(accuracy) else f"{accuracy:.1%}",
            help="Total absolute forecast error / total actual sales for the untouched final seven days. Lower is better.",
        )
        st.caption(
            "Exposure KPIs use the displayed history and 16 operating hours per day. Review status uses the latest 28 days. "
            "Forecast WAPE uses the final seven observed days. Sales remain on the normalized source scale."
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
                category_orders={"Risk": RISK_ORDER},
                text_auto=",.0f",
            )
            chart.update_layout(showlegend=False)
            chart.update_yaxes(title="Store–product series", rangemode="tozero")
            chart.update_xaxes(title=None)
            display_chart(style_chart(chart, 290), risks, "review_status")
        with right:
            st.subheader("Decision brief")
            st.write(
                "**1. Investigate repeated stockout exposure.** Review availability patterns and operational causes for the highest-priority store–product series."
            )
            st.write(
                "**2. Treat unavailable periods carefully.** Observed sales can be constrained by stockouts; a zero sale does not prove zero customer demand."
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
            "SUM(stockout_hours) / (COUNT(*) * 16.0) AS stockout_hour_rate, "
            "AVG(CASE WHEN stockout_hours > 0 THEN 1.0 ELSE 0 END) AS stockout_day_rate "
            f"FROM ({daily_scope}) GROUP BY date ORDER BY date",
            params,
        )
        trend["date"] = pd.to_datetime(trend["date"])
        display_chart(demand_trend_figure(trend), trend, "sales_and_stockout_trend")
        st.caption(
            "Read the dates together: observed sales and availability use aligned panels with separate units. "
            "Their movement does not establish that stockouts caused a change in sales."
        )
        left, right = st.columns(2)
        with left:
            st.subheader("Sales concentration by category")
            category_volume = (
                selected.groupby("category_id", as_index=False)["observed_sales_total"]
                .sum()
                .sort_values("observed_sales_total", ascending=False)
            )
            fig = px.bar(
                category_volume,
                x="category_id",
                y="observed_sales_total",
                color_discrete_sequence=[TEAL],
            )
            fig.update_xaxes(type="category", title="Category ID")
            fig.update_yaxes(title="Normalized observed sales", rangemode="tozero")
            display_chart(style_chart(fig, 310), category_volume, "category_sales")
        with right:
            st.subheader("Demand variability")
            variability = (
                selected["xyz_class"]
                .value_counts()
                .rename_axis("XYZ class")
                .reset_index(name="Series")
            )
            fig = px.bar(variability, x="XYZ class", y="Series", color_discrete_sequence=[BLUE])
            fig.update_yaxes(title="Store–product series", rangemode="tozero")
            display_chart(style_chart(fig, 310), variability, "sales_variability")
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
            hover_data={
                "series_id": True,
                "store_id": True,
                "product_id": True,
                "xyz_class": True,
                "priority_rank": True,
                "observed_mean_sales": ":.3f",
                "stockout_hour_rate": ":.1%",
            },
            color_discrete_map=RISK_COLORS,
            category_orders={"availability_risk": RISK_ORDER},
            opacity=0.5,
            render_mode="webgl",
            labels={"availability_risk": "Review status"},
        )
        fig.update_xaxes(title="Mean observed daily sales · normalized scale")
        fig.update_yaxes(title="Unavailable operating hours", tickformat=".0%")
        for threshold, label in [(0.10, "High Risk ≥10%"), (0.25, "Critical ≥25%")]:
            fig.add_hline(
                y=threshold,
                line_dash="dot",
                line_color="#8d9bab",
                annotation_text=label,
                annotation_position="top right",
                annotation_font_size=10,
            )
        fig = style_chart(fig, 430)
        fig.update_layout(hovermode="closest")
        display_chart(fig, selected, "stockout_risk")
        st.caption(
            "Each point is a store–product series. Both axes use the latest 28 days. "
            "Start with high observed sales and repeated exposure, then inspect the original review rank below."
        )
        st.subheader("Recommended management actions")
        display_recommendations(selected, key="risk")
        st.caption(
            "This queue cannot identify current stock, reorder quantities or excess inventory. Those decisions need on-hand stock, open orders and measured lead times."
        )
        with st.expander("Does zero observed sales coincide with stockout exposure?"):
            zero_sales = query(
                "SELECT CASE WHEN stockout_hours > 0 THEN 'Any stockout hours' ELSE 'No stockout hours' END AS availability, "
                "COUNT(*) AS daily_observations, SUM(CASE WHEN sales = 0 THEN 1 ELSE 0 END) AS zero_sales_days, "
                "AVG(CASE WHEN sales = 0 THEN 1.0 ELSE 0 END) AS zero_sales_rate "
                f"FROM ({daily_scope}) GROUP BY availability ORDER BY availability DESC",
                params,
            )
            fig = px.bar(
                zero_sales,
                x="availability",
                y="zero_sales_rate",
                color="availability",
                color_discrete_map={"No stockout hours": TEAL, "Any stockout hours": "#bf6c31"},
                hover_data={
                    "daily_observations": ":,",
                    "zero_sales_days": ":,",
                    "zero_sales_rate": ":.1%",
                },
            )
            fig.update_layout(showlegend=False)
            fig.update_xaxes(title="Observed daily availability")
            fig.update_yaxes(
                title="Zero-sales days / days in each group", tickformat=".1%", rangemode="tozero"
            )
            display_chart(style_chart(fig, 330), zero_sales, "zero_sales_availability")
            st.caption(
                "Rates use all displayed history and each group's own number of days. "
                "Zero sales can have multiple causes; exposure is an observed association, not a lost-sales estimate."
            )

    with tabs[3]:
        st.subheader("Time-validated observed-sales forecasts")
        st.caption(
            "90 training days → three historical validation folds → untouched final 7-day holdout. "
            "Next-period forecasts are refitted after evaluation and have no observed outcomes."
        )
        if not demo_scope and city is None and category is None:
            evidence_path = ROOT / "docs/evidence/findings.json"
            if evidence_path.is_file():
                evidence = json.loads(evidence_path.read_text())
                benchmark = evidence["forecast"]["holdout_metrics"]
                fixed_wape = benchmark["baselines"]["ses_alpha0.3"]["wape"]
                selector_wape = benchmark["all_days"]["wape"]
                st.info(
                    f"Full-data benchmark: fixed SES WAPE {fixed_wape:.1%} vs per-series selection {selector_wape:.1%}. "
                    "The selector did not beat this simpler benchmark on the untouched holdout. "
                    "The series-specific metrics below answer a different, narrower question."
                )
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
        metrics = forecast_metrics(holdout)
        columns = st.columns(3)
        columns[0].metric(
            "Holdout WAPE", "Unavailable" if metrics["wape"] is None else f"{metrics['wape']:.1%}"
        )
        columns[1].metric(
            "Holdout bias", "Unavailable" if metrics["bias"] is None else f"{metrics['bias']:+.1%}"
        )
        columns[2].metric(
            "Holdout MAE",
            "Unavailable" if metrics["mae"] is None else f"{metrics['mae']:.3f}",
            help="Mean absolute error in normalized sales per store–product day.",
        )
        model = str(forecasts["selected_model"].iloc[0]) if len(forecasts) else "Unavailable"
        st.write(f"**Selected model:** {MODEL_LABELS.get(model, model)} · **Series:** {choice}")
        st.caption(
            f"Single-series score over {len(holdout):,} holdout days; actual sales total "
            f"{holdout['actual'].sum():.3f} normalized sales. Small actual totals can make WAPE large. "
            "Use the pooled scope KPI for aggregate forecast performance."
        )
        view = st.radio(
            "Forecast chart period",
            ["Latest 28 days + forecast", "Full history + forecast"],
            horizontal=True,
            key="forecast_period",
        )
        fig, forecast_export = forecast_figure(
            history, forecasts, view == "Full history + forecast"
        )
        display_chart(fig, forecast_export, "actual_vs_forecast")
        st.caption(
            "Models are selected using historical rolling windows before the holdout. The holdout is evaluated once; future forecasts have no observed outcomes. Forecasts target observed sales, not latent customer demand."
        )
        with st.expander("Review holdout observations and score details"):
            holdout["prediction_error"] = holdout["prediction"] - holdout["actual"]
            st.dataframe(
                holdout[["date", "actual", "prediction", "prediction_error", "stockout_hours"]],
                width="stretch",
                hide_index=True,
                column_config={
                    "date": "Holdout date",
                    "actual": "Actual sales",
                    "prediction": "Predicted sales",
                    "prediction_error": "Prediction − actual",
                    "stockout_hours": "Stockout hours / 16",
                },
            )
            st.caption(
                "Actuals, predictions and errors use normalized sales. Positive bias means overprediction."
            )
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
            comparison_data = pd.DataFrame(comparison)
            fig = px.bar(
                comparison_data,
                x="Service target",
                y=["Safety stock", "Reorder point"],
                barmode="group",
                color_discrete_sequence=[BLUE, TEAL],
            )
            fig.update_yaxes(title="Illustrative inventory target · normalized scale")
            display_chart(style_chart(fig, 320), comparison_data, "planning_assumptions")
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
    st.caption(
        "Set a practical review workload. Status and priority remain the pipeline results; "
        "filters and alternate sorting do not reclassify risk."
    )
    controls = st.columns([1, 1.5, 1.5])
    capacity = controls[0].selectbox(
        "Review workload",
        ["Top 20", "Top 50", "Top 500"],
        key=f"capacity_{key}",
    )
    available = [risk for risk in RISK_ORDER if risk in set(summary["availability_risk"])]
    defaults = [risk for risk in ["Critical", "High Risk"] if risk in available]
    statuses = controls[1].multiselect(
        "Review status",
        available,
        default=defaults or available,
        key=f"statuses_{key}",
    )
    sort_by = controls[2].selectbox(
        "Sort management view",
        ["Original management priority", "Highest observed sales", "Highest stockout exposure"],
        key=f"sort_{key}",
    )
    limit = int(capacity.split()[-1])
    ordered = management_queue(summary, statuses, sort_by, limit)
    matching_count = int(summary["availability_risk"].isin(statuses).sum())
    st.caption(
        f"Showing {len(ordered):,} of {matching_count:,} matching series in the current scope. "
        f"Sales sorting uses the full observed history; exposure sorting uses the latest 28 days."
    )
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
    display = ordered[columns].copy()
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
    if not ordered.empty:
        with st.expander("Read the evidence and action for one review item", expanded=True):
            choice = st.selectbox(
                "Review item",
                ordered["series_id"].astype(str).tolist(),
                key=f"review_item_{key}",
            )
            item = ordered.loc[ordered["series_id"].astype(str) == choice].iloc[0]
            st.write(
                f"**{choice} · {item['availability_risk']} · Original priority {int(item['priority_rank']):,}**"
            )
            st.write(
                f"Latest 28 days: **{item['stockout_hour_rate']:.1%}** of operating hours unavailable; "
                f"observed mean **{item['observed_mean_sales']:.3f} normalized sales / day**."
            )
            st.write(f"**Evidence:** {item['reason']}")
            st.write(f"**Recommended next step:** {item['recommendation']}")
            st.caption(
                "Inspect this series in Forecasts, then verify actual stock, open orders and operating causes "
                "before setting a replenishment policy."
            )
    else:
        st.info("Choose at least one available review status to populate the management view.")
    st.caption(
        "Forecasts estimate normalized observed sales for the next seven days. Volume ABC classes retain the pipeline cohort classification; filtering does not reclassify them."
    )
    columns = st.columns(2)
    columns[0].download_button(
        "Download displayed review queue",
        lambda: ordered.to_csv(index=False).encode(),
        f"management_{key}_{limit}.csv",
        "text/csv",
        key=f"queue_download_{key}",
        on_click="ignore",
    )
    columns[1].download_button(
        "Download management recommendations",
        lambda: summary.sort_values("priority_rank").to_csv(index=False).encode(),
        "management_recommendations.csv",
        "text/csv",
        key=f"download_{key}",
        on_click="ignore",
        help="Includes every series in the city/category scope, including statuses hidden in this review queue.",
    )


if __name__ == "__main__":
    render_dashboard()
