"""Small, auditable baselines for normalized, possibly stockout-censored sales.

Model selection uses expanding validation windows wholly inside the training
period. The final holdout is scored once before every selected model is refit on
all observations for the future forecast. These are sales forecasts, not an
estimate of unconstrained demand.
"""

import re
from dataclasses import dataclass

import numpy as np
import pandas as pd

MODEL_NAMES = ("naive", "seasonal_naive7", "mean28", "ses_alpha0.3")


@dataclass
class ForecastResult:
    """Long-form outputs; WAPE and bias are ratios, not percentage points."""

    selections: pd.DataFrame
    validation: pd.DataFrame
    holdout_predictions: pd.DataFrame
    holdout_metrics: dict
    holdout_by_series: pd.DataFrame
    future_predictions: pd.DataFrame
    protocol: dict


@dataclass
class _DailyMatrix:
    series: np.ndarray
    dates: np.ndarray
    sales: np.ndarray
    stockouts: np.ndarray
    metadata: pd.DataFrame


def _positive_integer(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return int(value)


def _daily_matrix(daily: pd.DataFrame, max_stockout_hours: int = 16) -> _DailyMatrix:
    """Reject duplicate, incomplete, noncontiguous, or invalid daily series."""
    required = ["series_id", "date", "sales", "stockout_hours"]
    missing = set(required).difference(daily.columns)
    if missing or daily.empty:
        raise ValueError(f"Nonempty daily data requires {required}; missing {sorted(missing)}")
    max_hours = _positive_integer(max_stockout_hours, "max_stockout_hours")
    if max_hours > 24:
        raise ValueError("max_stockout_hours must not exceed 24")
    if daily[required].isna().any().any():
        raise ValueError("Daily identifiers, dates, sales, and stockout hours cannot be missing")
    ids = daily["series_id"].astype(str)
    if ids.str.len().eq(0).any():
        raise ValueError("series_id cannot be empty")
    dates_column = daily["date"].astype(str)
    dates = np.sort(dates_column.unique())
    if any(re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) is None for day in dates):
        raise ValueError("Dates must use ISO YYYY-MM-DD format")
    parsed = pd.to_datetime(dates, format="%Y-%m-%d", errors="raise")
    if len(dates) > 1 and not np.all(np.diff(parsed.values) == np.timedelta64(1, "D")):
        raise ValueError("Dates must be contiguous daily periods")
    # Cast explicitly and check before reshaping; sorting makes shuffled input safe.
    metadata_cols = [
        column for column in ("city_id", "store_id", "product_id", "category_id") if column in daily
    ]
    ordered = (
        daily[required + metadata_cols]
        .assign(series_id=ids, date=dates_column)
        .sort_values(["series_id", "date"])
    )
    if ordered.duplicated(["series_id", "date"]).any():
        raise ValueError("Duplicate series_id/date observations")
    sizes = ordered.groupby("series_id", sort=True).size()
    if not sizes.eq(len(dates)).all():
        raise ValueError("Every series must cover every date; missing periods are not imputed")
    try:
        sales = ordered["sales"].to_numpy(dtype=float)
        stockouts = ordered["stockout_hours"].to_numpy(dtype=float)
    except (ValueError, TypeError) as error:
        raise ValueError("Sales and stockout hours must be numeric") from error
    if not np.isfinite(sales).all() or (sales < 0).any():
        raise ValueError("Normalized sales must be finite and nonnegative")
    if not np.isfinite(stockouts).all() or (stockouts < 0).any() or (stockouts > max_hours).any():
        raise ValueError(f"Stockout hours must be finite and between 0 and {max_hours}")
    if not np.equal(stockouts, np.floor(stockouts)).all():
        raise ValueError("Stockout hours must be whole observed hours")
    if metadata_cols:
        grouped = ordered.groupby("series_id", sort=True)[metadata_cols]
        if grouped.nunique(dropna=False).gt(1).any().any():
            raise ValueError("Series metadata must be constant across dates")
        metadata = grouped.first().reset_index()
    else:
        metadata = pd.DataFrame({"series_id": sizes.index.to_numpy()})
    shape = (len(sizes), len(dates))
    return _DailyMatrix(
        sizes.index.to_numpy(), dates, sales.reshape(shape), stockouts.reshape(shape), metadata
    )


def forecast_metrics(actual, prediction) -> dict:
    """Micro metrics across all supplied observations; zero actual totals yield null ratios."""
    actual = np.asarray(actual, dtype=float)
    prediction = np.asarray(prediction, dtype=float)
    if actual.shape != prediction.shape:
        raise ValueError("Actual and prediction shapes must match")
    if not np.isfinite(actual).all() or not np.isfinite(prediction).all():
        raise ValueError("Metrics require finite actuals and predictions")
    if (actual < 0).any() or (prediction < 0).any():
        raise ValueError("Sales actuals and predictions must be nonnegative")
    total = float(actual.sum())
    if actual.size == 0:
        return {
            "mae": None,
            "rmse": None,
            "wape": None,
            "bias": None,
            "n_observations": 0,
            "actual_sum": 0.0,
        }
    error = prediction - actual
    return {
        "mae": float(np.abs(error).mean()),
        "rmse": float(np.sqrt(np.square(error).mean())),
        "wape": float(np.abs(error).sum() / total) if total > 0 else None,
        "bias": float(error.sum() / total) if total > 0 else None,
        "n_observations": int(actual.size),
        "actual_sum": total,
    }


def _predict_candidates(history: np.ndarray, horizon: int) -> np.ndarray:
    """Return [series, model, horizon], vectorized across every series."""
    naive = np.repeat(history[:, -1:], horizon, axis=1)
    seasonal = history[:, -7:][:, np.arange(horizon) % 7]
    mean28 = np.repeat(history[:, -28:].mean(axis=1, keepdims=True), horizon, axis=1)
    level = history[:, 0].copy()
    for day in range(1, history.shape[1]):
        level = 0.3 * history[:, day] + 0.7 * level
    ses = np.repeat(level[:, None], horizon, axis=1)
    return np.stack((naive, seasonal, mean28, ses), axis=1)


def _ratio(numerator, denominator):
    return np.divide(
        numerator,
        denominator,
        out=np.full_like(numerator, np.nan, dtype=float),
        where=denominator > 0,
    )


def forecast_sales(
    daily: pd.DataFrame,
    *,
    training_days: int = 90,
    horizon: int = 7,
    validation_folds: int = 3,
    max_stockout_hours: int = 16,
) -> ForecastResult:
    """Select one baseline per series, score the untouched holdout, then refit.

    Defaults require exactly 97 complete daily periods. Three expanding folds
    end on training days 76, 83, and 90, with initial training days 1–69.
    Ties use MODEL_NAMES order. No holdout value influences model selection.
    """
    training_days = _positive_integer(training_days, "training_days")
    horizon = _positive_integer(horizon, "horizon")
    validation_folds = _positive_integer(validation_folds, "validation_folds")
    first_cutoff = training_days - validation_folds * horizon
    if first_cutoff < 28:
        raise ValueError("The first validation fold needs at least 28 training days")
    matrix = _daily_matrix(daily, max_stockout_hours)
    if len(matrix.dates) != training_days + horizon:
        raise ValueError(
            f"Expected exactly {training_days + horizon} daily periods for training plus holdout"
        )
    count = len(matrix.series)
    abs_errors = np.zeros((count, len(MODEL_NAMES)))
    squared_errors = np.zeros_like(abs_errors)
    signed_errors = np.zeros_like(abs_errors)
    actual_total = np.zeros((count, 1))
    fold_dates = []
    for fold in range(validation_folds):
        cutoff = first_cutoff + fold * horizon
        actual = matrix.sales[:, cutoff : cutoff + horizon]
        error = _predict_candidates(matrix.sales[:, :cutoff], horizon) - actual[:, None, :]
        abs_errors += np.abs(error).sum(axis=2)
        squared_errors += np.square(error).sum(axis=2)
        signed_errors += error.sum(axis=2)
        actual_total += actual.sum(axis=1, keepdims=True)
        fold_dates.append(
            {
                "train_end": str(matrix.dates[cutoff - 1]),
                "validation_start": str(matrix.dates[cutoff]),
                "validation_end": str(matrix.dates[cutoff + horizon - 1]),
            }
        )
    validation_n = validation_folds * horizon
    maes = abs_errors / validation_n
    selected_indices = np.argmin(maes, axis=1)
    selected_names = np.asarray(MODEL_NAMES)[selected_indices]
    selections = pd.DataFrame(
        {
            "series_id": matrix.series,
            "selected_model": selected_names,
            "validation_mae": maes[np.arange(count), selected_indices],
        }
    )
    validation = pd.DataFrame(
        {
            "series_id": np.repeat(matrix.series, len(MODEL_NAMES)),
            "model": np.tile(MODEL_NAMES, count),
            "mae": maes.ravel(),
            "rmse": np.sqrt(squared_errors / validation_n).ravel(),
            "wape": _ratio(abs_errors, actual_total).ravel(),
            "bias": _ratio(signed_errors, actual_total).ravel(),
            "n_observations": validation_n,
        }
    )
    actual = matrix.sales[:, training_days:]
    stockouts = matrix.stockouts[:, training_days:]
    holdout_candidates = _predict_candidates(matrix.sales[:, :training_days], horizon)
    prediction = holdout_candidates[np.arange(count), selected_indices]
    holdout_predictions = pd.DataFrame(
        {
            "series_id": np.repeat(matrix.series, horizon),
            "date": np.tile(matrix.dates[training_days:], count),
            "actual": actual.ravel(),
            "prediction": prediction.ravel(),
            "stockout_hours": stockouts.ravel().astype(int),
            "selected_model": np.repeat(selected_names, horizon),
        }
    )
    mask = stockouts == 0
    holdout_metrics = {
        "all_days": forecast_metrics(actual, prediction),
        "uncensored_days": forecast_metrics(actual[mask], prediction[mask]),
    }
    holdout_metrics["all_days"]["n_series"] = count
    holdout_metrics["uncensored_days"]["n_series"] = int(mask.any(axis=1).sum())
    holdout_metrics["baselines"] = {
        model: forecast_metrics(actual, holdout_candidates[:, index, :])
        for index, model in enumerate(MODEL_NAMES)
    }
    error = prediction - actual
    total = actual.sum(axis=1)
    holdout_by_series = pd.DataFrame(
        {
            "series_id": matrix.series,
            "selected_model": selected_names,
            "mae": np.abs(error).mean(axis=1),
            "rmse": np.sqrt(np.square(error).mean(axis=1)),
            "wape": _ratio(np.abs(error).sum(axis=1), total),
            "bias": _ratio(error.sum(axis=1), total),
            "n_observations": horizon,
            "actual_sum": total,
        }
    )
    future = _predict_candidates(matrix.sales, horizon)[np.arange(count), selected_indices]
    future_dates = pd.date_range(
        pd.Timestamp(matrix.dates[-1]) + pd.Timedelta(days=1), periods=horizon
    ).strftime("%Y-%m-%d")
    future_predictions = pd.DataFrame(
        {
            "series_id": np.repeat(matrix.series, horizon),
            "date": np.tile(future_dates.to_numpy(), count),
            "prediction": future.ravel(),
            "selected_model": np.repeat(selected_names, horizon),
        }
    )
    protocol = {
        "training_days": training_days,
        "horizon": horizon,
        "validation_folds": fold_dates,
        "holdout_start": str(matrix.dates[training_days]),
        "holdout_end": str(matrix.dates[-1]),
        "future_refit_end": str(matrix.dates[-1]),
        "model_tie_order": list(MODEL_NAMES),
        "units": "normalized_sales_units",
        "target": "observed_possibly_censored_sales",
        "baseline_comparison": "Final holdout diagnostic only; does not alter validation selection",
        "uncensored_filter": "stockout_hours == 0; selection-biased diagnostic, not lost-demand recovery",
    }
    return ForecastResult(
        selections,
        validation,
        holdout_predictions,
        holdout_metrics,
        holdout_by_series,
        future_predictions,
        protocol,
    )
