"""Dashboard contract checks use tiny test fixtures, never fabricated project findings."""

import importlib.util
import sqlite3
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app/dashboard.py"
spec = importlib.util.spec_from_file_location("scdi_dashboard", APP)
dashboard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dashboard)


def test_database_resolution_prefers_full_then_demo(tmp_path, monkeypatch):
    monkeypatch.delenv("SCDI_DATABASE", raising=False)
    full = tmp_path / "data/processed/decision_intelligence.sqlite"
    demo = tmp_path / "data/demo/decision_intelligence.sqlite"
    demo.parent.mkdir(parents=True)
    demo.touch()
    assert dashboard.resolve_database(tmp_path) == demo
    full.parent.mkdir(parents=True)
    full.touch()
    assert dashboard.resolve_database(tmp_path) == full


def test_missing_database_is_explained(tmp_path, monkeypatch):
    monkeypatch.delenv("SCDI_DATABASE", raising=False)
    with pytest.raises(FileNotFoundError, match="processing pipeline"):
        dashboard.resolve_database(tmp_path)


def test_sql_scope_parameterizes_user_values():
    malicious = "1 OR 1=1"
    clause, params = dashboard.scope_clause(malicious, 2)
    assert clause == " WHERE city_id = ? AND category_id = ?"
    assert params == (malicious, 2)
    assert malicious not in clause


def test_forecast_dashboard_uses_pooled_not_macro_wape():
    values = pd.DataFrame({"actual": [1.0, 100.0], "prediction": [2.0, 100.0]})
    metrics = dashboard.forecast_metrics(values)
    assert metrics["wape"] == pytest.approx(1 / 101)
    assert metrics["bias"] == pytest.approx(1 / 101)
    assert metrics["mae"] == 0.5
    assert (
        dashboard.forecast_metrics(pd.DataFrame({"actual": [0.0], "prediction": [0.0]}))["wape"]
        is None
    )
    assert (
        dashboard.forecast_metrics(pd.DataFrame({"actual": [0.0], "prediction": [2.0]}))["mae"]
        == 2.0
    )


@pytest.fixture
def fixture_database(tmp_path):
    path = tmp_path / "app-test.sqlite"
    daily = pd.DataFrame(
        {
            "series_id": ["1_1"] * 3,
            "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "sales": [1.0, 2.0, 3.0],
            "stockout_hours": [0, 2, 4],
            "city_id": [1] * 3,
            "store_id": [1] * 3,
            "product_id": [1] * 3,
            "category_id": [1] * 3,
        }
    )
    summary = pd.DataFrame(
        {
            "series_id": ["1_1"],
            "city_id": [1],
            "store_id": [1],
            "product_id": [1],
            "category_id": [1],
            "observed_mean_sales": [2.0],
            "observed_std_sales": [1.0],
            "sales_cv": [0.5],
            "xyz_class": ["X"],
            "stockout_hour_rate": [0.125],
            "stockout_day_fraction": [2 / 3],
            "availability_risk": ["High Risk"],
            "priority_rank": [1],
            "observed_sales_total": [6.0],
            "forecast_daily_sales": [4.0],
            "forecast_next7_sales": [28.0],
            "selected_model": ["mean_7"],
            "recommendation": ["Investigate availability"],
            "reason": ["Repeated exposure"],
        }
    )
    forecasts = pd.DataFrame(
        {
            "series_id": ["1_1"] * 2,
            "date": ["2024-01-03", "2024-01-04"],
            "actual": [3.0, None],
            "prediction": [2.0, 2.5],
            "stockout_hours": [4, None],
            "selected_model": ["mean_7"] * 2,
            "split": ["holdout", "future"],
        }
    )
    with sqlite3.connect(path) as connection:
        daily.to_sql("daily_sales", connection, index=False)
        summary.to_sql("series_summary", connection, index=False)
        forecasts.to_sql("forecast_values", connection, index=False)
        pd.DataFrame({"series_id": ["1_1"], "wape": [1 / 3]}).to_sql(
            "forecast_scores", connection, index=False
        )
        pd.DataFrame({"key": ["scope", "dataset"], "value": ["demo", "test fixture"]}).to_sql(
            "metadata", connection, index=False
        )
    return path


def test_dashboard_renders_tabs_and_assumption_controls(fixture_database, monkeypatch):
    monkeypatch.setenv("SCDI_DATABASE", str(fixture_database))
    app = AppTest.from_file(str(APP)).run(timeout=30)
    assert not app.exception
    assert len(app.get("tab")) == 6
    assert app.title[0].value == "Supply Chain Decision Intelligence"
    labels = {metric.label for metric in app.metric}
    assert "Holdout pooled WAPE" in labels
    assert "Illustrative reorder point" in labels
    assert any("demonstration subset" in message.value for message in app.info)
    app.slider[0].set_value(20).run(timeout=30)
    assert not app.exception
    assert app.slider[0].value == 20
    previous_target = float(
        next(metric.value for metric in app.metric if metric.label == "Illustrative reorder point")
    )
    app.selectbox(key="scenario_baseline").set_value("Refit future daily sales estimate").run(
        timeout=30
    )
    assert not app.exception
    updated_target = float(
        next(metric.value for metric in app.metric if metric.label == "Illustrative reorder point")
    )
    assert updated_target > previous_target


def test_dashboard_explains_incompatible_zero_scenario_inputs(fixture_database, monkeypatch):
    with sqlite3.connect(fixture_database) as connection:
        connection.execute("UPDATE series_summary SET forecast_daily_sales=0")
    monkeypatch.setenv("SCDI_DATABASE", str(fixture_database))
    app = AppTest.from_file(str(APP)).run(timeout=30)
    app.number_input[0].set_value(0.0).run(timeout=30)
    assert not app.exception
    assert any("zero mean lead time" in warning.value for warning in app.warning)
    assert not any(metric.label == "Illustrative reorder point" for metric in app.metric)
    app.number_input[0].set_value(3.0).run(timeout=30)
    app.selectbox(key="scenario_baseline").set_value("Refit future daily sales estimate").run(
        timeout=30
    )
    assert not app.exception
    assert any("zero sales baseline" in warning.value for warning in app.warning)
    assert not any(metric.label == "Illustrative reorder point" for metric in app.metric)
