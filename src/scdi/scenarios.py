"""Hypothetical replenishment math using explicit assumptions in normalized units.

This normal approximation assumes independent daily demand and lead time.
Observed sales may be stockout-censored and are only a proxy for demand. Actual
lead times, service targets, and inventory positions are not in the dataset.
"""

from dataclasses import asdict, dataclass
from math import isfinite, sqrt
from statistics import NormalDist


@dataclass(frozen=True)
class ScenarioResult:
    assumed_mu_daily: float
    assumed_sigma_daily: float
    assumed_lead_time_days: float
    assumed_lead_time_std_days: float
    assumed_service_level: float
    assumed_demand_shock_pct: float
    assumed_inventory_position: float
    service_z: float
    expected_lead_time_demand: float
    safety_stock: float
    reorder_point: float
    hypothetical_order_gap: float
    units: str = "normalized_sales_units"
    assumption_label: str = (
        "Hypothetical assumptions; not actual company inventory or an executable order"
    )

    def to_dict(self) -> dict:
        return asdict(self)


def _finite_number(value, name):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a finite number") from error
    if not isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    return number


def evaluate_scenario(
    mean_daily_demand,
    std_daily_demand,
    *,
    lead_time_days=3,
    lead_time_std_days=1,
    service_level=0.95,
    demand_shock_pct=0,
    inventory_position=0,
) -> ScenarioResult:
    """Calculate SS, ROP, and an assumed-position gap; shock 25 means +25%.

    SS = z * sqrt(L * sigma_D**2 + mu_D**2 * sigma_L**2)
    ROP = mu_D * L + SS; hypothetical gap = max(ROP - assumed position, 0).
    Shock scales both daily mean and daily standard deviation. Inventory
    position defaults to an explicit hypothetical zero, not observed inventory.
    Service must lie in [0.5, 1); demand shock cannot be below -100%.
    Nonnegative demand or lead time with zero mean must also have zero standard
    deviation; otherwise the supplied moments describe an impossible variable.
    """
    inputs = {
        "mean_daily_demand": mean_daily_demand,
        "std_daily_demand": std_daily_demand,
        "lead_time_days": lead_time_days,
        "lead_time_std_days": lead_time_std_days,
        "service_level": service_level,
        "demand_shock_pct": demand_shock_pct,
        "inventory_position": inventory_position,
    }
    values = {name: _finite_number(value, name) for name, value in inputs.items()}
    for name in (
        "mean_daily_demand",
        "std_daily_demand",
        "lead_time_days",
        "lead_time_std_days",
        "inventory_position",
    ):
        if values[name] < 0:
            raise ValueError(f"{name} must be nonnegative")
    if not 0.5 <= values["service_level"] < 1:
        raise ValueError("service_level must be at least 0.5 and less than 1")
    if values["demand_shock_pct"] < -100:
        raise ValueError("demand_shock_pct must be at least -100")
    if values["mean_daily_demand"] == 0 and values["std_daily_demand"] > 0:
        raise ValueError("Zero mean daily demand requires zero demand standard deviation")
    if values["lead_time_days"] == 0 and values["lead_time_std_days"] > 0:
        raise ValueError("Zero mean lead time requires zero lead-time standard deviation")
    multiplier = 1 + values["demand_shock_pct"] / 100
    mean = values["mean_daily_demand"] * multiplier
    std = values["std_daily_demand"] * multiplier
    lead = values["lead_time_days"]
    lead_std = values["lead_time_std_days"]
    z = NormalDist().inv_cdf(values["service_level"])
    try:
        expected = mean * lead
        safety = z * sqrt(lead * std**2 + mean**2 * lead_std**2)
        reorder = expected + safety
    except OverflowError as error:
        raise ValueError("Scenario inputs exceed finite numeric limits") from error
    if not all(isfinite(value) for value in (mean, std, expected, safety, reorder)):
        raise ValueError("Scenario inputs exceed finite numeric limits")
    gap = max(reorder - values["inventory_position"], 0.0)
    return ScenarioResult(
        mean,
        std,
        lead,
        lead_std,
        values["service_level"],
        values["demand_shock_pct"],
        values["inventory_position"],
        z,
        expected,
        safety,
        reorder,
        gap,
    )
