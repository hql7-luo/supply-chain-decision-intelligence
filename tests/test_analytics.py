"""Tests for decision-relevant boundaries: leakage, censoring, metrics, and assumptions."""

from math import sqrt
from statistics import NormalDist

import numpy as np
import pandas as pd
import pytest

from scdi.forecasting import MODEL_NAMES, forecast_metrics, forecast_sales
from scdi.inventory import summarize_inventory
from scdi.scenarios import evaluate_scenario


def daily_frame(series_sales, stockouts=None):
    """Each supplied list is one complete daily series."""
    dates = pd.date_range("2024-03-01", periods=len(next(iter(series_sales.values())))).strftime(
        "%Y-%m-%d"
    )
    frames = []
    for index, (series, sales) in enumerate(series_sales.items()):
        frame = pd.DataFrame(
            {
                "series_id": series,
                "date": dates,
                "sales": sales,
                "stockout_hours": stockouts.get(series, 0) if stockouts else 0,
                "city_id": 1,
                "store_id": index,
                "product_id": index,
                "category_id": 2,
            }
        )
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def test_validation_selection_tie_order_and_seasonal_pattern():
    seasonal = np.resize([1, 4, 2, 8, 3, 7, 5], 97)
    data = daily_frame({"seasonal": seasonal, "constant": np.ones(97)})
    result = forecast_sales(data.sample(frac=1, random_state=4))
    chosen = result.selections.set_index("series_id")
    assert chosen.loc["constant", "selected_model"] == MODEL_NAMES[0]
    assert chosen.loc["seasonal", "selected_model"] == "seasonal_naive7"
    assert chosen.loc["seasonal", "validation_mae"] == 0
    assert result.holdout_metrics["all_days"]["mae"] == 0
    assert result.holdout_metrics["baselines"]["seasonal_naive7"]["mae"] == 0
    assert result.holdout_metrics["baselines"]["naive"]["mae"] > 0
    assert len(result.validation) == 8
    assert result.validation["n_observations"].eq(21).all()
    assert result.protocol["validation_folds"][0]["train_end"] == "2024-05-08"
    assert result.protocol["validation_folds"][-1]["validation_end"] == "2024-05-29"
    assert result.future_predictions["date"].min() == "2024-06-06"


def test_holdout_cannot_influence_selection_or_holdout_prediction_but_refit_uses_it():
    original = daily_frame({"constant": np.ones(97)})
    changed = original.copy()
    changed.loc[changed.index[-7:], "sales"] = 10
    baseline = forecast_sales(original)
    shifted = forecast_sales(changed)
    pd.testing.assert_frame_equal(baseline.selections, shifted.selections)
    pd.testing.assert_frame_equal(baseline.validation, shifted.validation)
    np.testing.assert_array_equal(
        baseline.holdout_predictions["prediction"], shifted.holdout_predictions["prediction"]
    )
    assert shifted.holdout_metrics["all_days"]["mae"] == 9
    assert shifted.future_predictions["prediction"].eq(10).all()
    assert baseline.future_predictions["prediction"].eq(1).all()


def test_micro_wape_bias_and_zero_total_are_well_defined():
    metrics = forecast_metrics([1, 100], [2, 90])
    assert metrics["wape"] == pytest.approx(11 / 101)
    assert metrics["bias"] == pytest.approx(-9 / 101)
    assert metrics["mae"] == 5.5
    assert metrics["rmse"] == pytest.approx(sqrt(101 / 2))
    zero = forecast_metrics([0, 0], [1, 1])
    assert zero["wape"] is None and zero["bias"] is None
    assert zero["mae"] == 1
    empty = forecast_metrics([], [])
    assert empty["n_observations"] == 0 and empty["mae"] is None


def test_stockout_days_are_in_primary_score_and_uncensored_subset_is_separate():
    data = daily_frame({"a": np.ones(97)}, {"a": [0] * 90 + [16, 16, 0, 0, 0, 0, 0]})
    data.loc[data.index[-7:-5], "sales"] = 0
    result = forecast_sales(data)
    assert result.holdout_metrics["all_days"]["n_observations"] == 7
    assert result.holdout_metrics["all_days"]["mae"] == pytest.approx(2 / 7)
    assert result.holdout_metrics["uncensored_days"]["n_observations"] == 5
    assert result.holdout_metrics["uncensored_days"]["mae"] == 0
    assert "selection-biased" in result.protocol["uncensored_filter"]


@pytest.mark.parametrize(
    "problem",
    [
        "missing",
        "duplicate",
        "noncontiguous",
        "nan",
        "negative_sales",
        "fractional_hours",
        "excess_hours",
    ],
)
def test_incomplete_or_invalid_daily_input_is_rejected(problem):
    data = daily_frame({"a": np.ones(97), "b": np.ones(97)})
    if problem == "missing":
        data = data.drop(index=0)
    elif problem == "duplicate":
        data = pd.concat([data, data.iloc[[0]]], ignore_index=True)
    elif problem == "noncontiguous":
        data.loc[data["date"].eq("2024-03-01"), "date"] = "2024-02-28"
    elif problem == "nan":
        data.loc[0, "sales"] = np.nan
    elif problem == "negative_sales":
        data.loc[0, "sales"] = -1
    elif problem == "fractional_hours":
        data["stockout_hours"] = data["stockout_hours"].astype(float)
        data.loc[0, "stockout_hours"] = 0.5
    else:
        data.loc[0, "stockout_hours"] = 17
    with pytest.raises(ValueError):
        forecast_sales(data)


def test_observed_availability_thresholds_window_and_deterministic_ranking():
    series = {
        "critical": np.ones(97),
        "high": np.ones(97),
        "watch": np.ones(97),
        "healthy_b": np.ones(97),
        "healthy_a": np.ones(97),
        "variable": np.r_[np.ones(69), np.zeros(27), 28],
    }
    hours = {
        "critical": [0] * 69 + [4] * 28,
        "high": [0] * 69 + [2] * 28,
        "watch": [0] * 69 + [1] * 28,
        "healthy_a": [16] * 69 + [0] * 28,
    }
    results = summarize_inventory(daily_frame(series, hours)).set_index("series_id")
    assert results.loc["critical", "availability_risk"] == "Critical"
    assert results.loc["critical", "stockout_hour_rate"] == 0.25
    assert results.loc["high", "availability_risk"] == "High Risk"
    assert results.loc["watch", "availability_risk"] == "Watch"
    assert results.loc["healthy_a", "availability_risk"] == "Healthy"
    assert results.loc["variable", "availability_risk"] == "Watch"
    assert results.loc["variable", "xyz_class"] == "Z"
    assert results.loc["healthy_a", "xyz_class"] == "X"
    assert results.loc["healthy_a", "priority_rank"] < results.loc["healthy_b", "priority_rank"]
    assert results["days_observed"].eq(28).all()
    assert results.loc["critical", "stockout_hours_total"] == 112


def test_volume_concentration_is_normalized_sales_not_financial_abc():
    results = summarize_inventory(
        daily_frame({"dominant": np.full(97, 90), "next": np.full(97, 8), "last": np.full(97, 2)})
    ).set_index("series_id")
    assert results.loc["dominant", "volume_abc_class"] == "A"
    assert results.loc["next", "volume_abc_class"] == "B"
    assert results.loc["last", "volume_abc_class"] == "C"
    assert results["observed_sales_share"].sum() == pytest.approx(1)
    zero = summarize_inventory(daily_frame({"zero": np.zeros(97)}))
    assert zero["volume_abc_class"].eq("Unknown").all()
    assert zero["observed_sales_share"].isna().all()


def test_zero_recent_sales_is_unknown_variability_and_requires_review():
    data = daily_frame(
        {
            "no_sales": np.zeros(97),
            "zero_critical": np.zeros(97),
            "dormant": np.r_[np.ones(69), np.zeros(28)],
        },
        {"zero_critical": [4] * 97},
    )
    results = summarize_inventory(data).set_index("series_id")
    assert results["sales_cv"].isna().all()
    assert results["xyz_class"].eq("Unknown").all()
    assert results.loc["no_sales", "availability_risk"] == "Watch"
    assert results.loc["dormant", "availability_risk"] == "Watch"
    assert results.loc["zero_critical", "availability_risk"] == "Critical"
    assert results["reason"].str.contains("CV is undefined").all()
    assert results["recommendation"].str.contains("Verify active assortment").all()


def test_scenario_math_and_shock_do_not_claim_actual_inventory():
    scenario = evaluate_scenario(
        10,
        2,
        lead_time_days=4,
        lead_time_std_days=1,
        service_level=0.95,
        demand_shock_pct=25,
        inventory_position=20,
    )
    z = NormalDist().inv_cdf(0.95)
    assert scenario.assumed_mu_daily == 12.5
    assert scenario.assumed_sigma_daily == 2.5
    assert scenario.expected_lead_time_demand == 50
    assert scenario.safety_stock == pytest.approx(z * sqrt(4 * 2.5**2 + 12.5**2))
    assert scenario.hypothetical_order_gap == pytest.approx(scenario.reorder_point - 20)
    assert "Hypothetical" in scenario.to_dict()["assumption_label"]
    assert scenario.units == "normalized_sales_units"
    covered = evaluate_scenario(10, 2, inventory_position=10000)
    assert covered.hypothetical_order_gap == 0
    no_demand = evaluate_scenario(10, 2, demand_shock_pct=-100)
    assert no_demand.reorder_point == 0


@pytest.mark.parametrize(
    "overrides",
    [
        {"mean_daily_demand": -1},
        {"std_daily_demand": float("nan")},
        {"lead_time_days": -1},
        {"lead_time_std_days": float("inf")},
        {"service_level": 1},
        {"service_level": 0.49},
        {"inventory_position": -1},
        {"demand_shock_pct": -101},
        {"inventory_position": True},
        {"mean_daily_demand": 1e308, "std_daily_demand": 1e308},
    ],
)
def test_scenario_rejects_invalid_or_nonfinite_assumptions(overrides):
    values = {"mean_daily_demand": 10, "std_daily_demand": 2, **overrides}
    with pytest.raises(ValueError):
        evaluate_scenario(**values)


@pytest.mark.parametrize(
    "overrides,message",
    [
        ({"mean_daily_demand": 0, "std_daily_demand": 2}, "Zero mean daily demand"),
        ({"lead_time_days": 0, "lead_time_std_days": 1}, "Zero mean lead time"),
    ],
)
def test_scenario_rejects_impossible_zero_mean_nonnegative_variables(overrides, message):
    values = {"mean_daily_demand": 10, "std_daily_demand": 2, **overrides}
    with pytest.raises(ValueError, match=message):
        evaluate_scenario(**values)


def test_zero_mean_with_zero_variability_remains_a_valid_scenario():
    no_demand = evaluate_scenario(0, 0)
    assert no_demand.reorder_point == 0
    immediate = evaluate_scenario(10, 2, lead_time_days=0, lead_time_std_days=0)
    assert immediate.reorder_point == 0
