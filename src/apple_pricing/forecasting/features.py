"""Leakage-safe feature and target construction for the price forecasts.

The series are irregular (a platform x model x condition series is observed on
~22% of calendar days), so every lag, rolling window and target is defined in
*calendar time* using as-of joins, not by shifting rows. "7-day lag" really
means "the last price observed at least 7 days ago".

Every feature for a row dated `d` uses only observations dated <= d; the
target is the first observation on or after d + horizon (within 3 days).
"""

import numpy as np
import pandas as pd

SERIES_KEYS = ["platform", "model_name", "condition"]
TARGET_TOLERANCE_DAYS = 3

CATEGORICAL_FEATURES = ["platform", "product_category", "model_name", "condition", "sale_event"]

NUMERIC_FEATURES = [
    "log_price",
    "launch_price_usd",
    "price_index",
    "listing_count",
    "spread_pct",
    "avg_rating",
    "median_reviews",
    "in_stock_share",
    "out_of_stock_share",
    "is_sale_event",
    "days_since_release",
    "is_successor_released",
    "days_since_successor_release",
    "month",
    "week_of_year",
    "day_of_week",
    "ret_7d",
    "ret_14d",
    "ret_30d",
    "ret_60d",
    "vs_roll_mean_7d",
    "vs_roll_mean_30d",
    "vs_roll_mean_90d",
    "vs_roll_min_90d",
    "vs_roll_max_90d",
    "roll_std_30d_pct",
    "roll_count_30d",
    "vs_baseline_30obs",
    "vs_other_platform",
]

MODEL_FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES

DAILY_SQL = """
select
    price_date, platform, product_category, model_name, condition,
    launch_price_usd, min_price_usd, median_price_usd, max_price_usd,
    listing_count, avg_rating, median_reviews, in_stock_share, out_of_stock_share,
    is_sale_event, sale_event, price_index, days_since_release,
    is_successor_released, successor_release_date, baseline_price_30obs_usd
from marts.fct_daily_market_prices
"""


def load_daily(warehouse) -> pd.DataFrame:
    data = warehouse.query(DAILY_SQL)
    data["price_date"] = pd.to_datetime(data["price_date"])
    data["successor_release_date"] = pd.to_datetime(data["successor_release_date"])
    return data.sort_values(SERIES_KEYS + ["price_date"]).reset_index(drop=True)


def asof_series_value(
    data: pd.DataFrame,
    offset_days: int,
    direction: str,
    tolerance_days: int,
    value_column: str = "median_price_usd",
    by: list[str] | None = None,
    right: pd.DataFrame | None = None,
) -> np.ndarray:
    """Value of the same series at `price_date + offset_days`.

    direction="backward": latest observation on or before that date.
    direction="forward":  earliest observation on or after that date.
    Returns NaN where nothing falls within `tolerance_days`.
    """
    by = by or SERIES_KEYS
    right = data if right is None else right

    left = data[by + ["price_date"]].copy()
    left["_row"] = np.arange(len(left))
    left["_key_date"] = left["price_date"] + pd.Timedelta(days=offset_days)

    lookup = right[by + ["price_date", value_column]].rename(
        columns={"price_date": "_key_date", value_column: "_value"}
    )

    merged = pd.merge_asof(
        left.sort_values("_key_date"),
        lookup.sort_values("_key_date"),
        on="_key_date",
        by=by,
        direction=direction,
        tolerance=pd.Timedelta(days=tolerance_days),
    )
    return merged.sort_values("_row")["_value"].to_numpy()


def _rolling(data: pd.DataFrame, window_days: int, statistic: str) -> np.ndarray:
    """Time-based rolling statistic over the previous `window_days`, excluding today."""
    rolling = (
        data.set_index("price_date")
        .groupby(SERIES_KEYS, sort=False)["median_price_usd"]
        .rolling(f"{window_days}D", closed="left")
    )
    values = getattr(rolling, statistic)().to_numpy()
    if len(values) != len(data):
        raise RuntimeError("Rolling output is misaligned with the input rows")
    return values


def build_features(daily: pd.DataFrame) -> pd.DataFrame:
    data = daily.sort_values(SERIES_KEYS + ["price_date"]).reset_index(drop=True).copy()
    price = data["median_price_usd"]

    data["log_price"] = np.log(price)
    data["spread_pct"] = (data["max_price_usd"] - data["min_price_usd"]) / price * 100
    data["month"] = data["price_date"].dt.month
    data["week_of_year"] = data["price_date"].dt.isocalendar().week.astype(int)
    data["day_of_week"] = data["price_date"].dt.dayofweek
    data["days_since_successor_release"] = np.where(
        data["is_successor_released"] == 1,
        (data["price_date"] - data["successor_release_date"]).dt.days,
        np.nan,
    )

    for lag in (7, 14, 30, 60):
        lagged = asof_series_value(data, -lag, "backward", tolerance_days=max(7, lag // 2))
        data[f"ret_{lag}d"] = price / lagged - 1

    for window in (7, 30, 90):
        data[f"vs_roll_mean_{window}d"] = price / _rolling(data, window, "mean") - 1

    data["roll_mean_30d"] = _rolling(data, 30, "mean")
    data["vs_roll_min_90d"] = price / _rolling(data, 90, "min") - 1
    data["vs_roll_max_90d"] = price / _rolling(data, 90, "max") - 1
    data["roll_std_30d_pct"] = _rolling(data, 30, "std") / price * 100
    data["roll_count_30d"] = _rolling(data, 30, "count")
    data["vs_baseline_30obs"] = price / data["baseline_price_30obs_usd"] - 1

    # Same model/condition on the other marketplace, latest price in the last 14 days.
    other = data[SERIES_KEYS + ["price_date", "median_price_usd"]].copy()
    other["platform"] = other["platform"].map({"Amazon": "Flipkart", "Flipkart": "Amazon"})
    other_price = asof_series_value(data, 0, "backward", tolerance_days=14, right=other)
    data["vs_other_platform"] = price / other_price - 1

    for column in CATEGORICAL_FEATURES:
        data[column] = data[column].fillna("Unknown").astype(str)

    return data


def add_target(data: pd.DataFrame, horizon_days: int) -> pd.DataFrame:
    """Adds target_price (future price) and target_log_ratio = log(future / current)."""
    result = data.copy()
    result["target_price"] = asof_series_value(
        result, horizon_days, "forward", tolerance_days=TARGET_TOLERANCE_DAYS
    )
    result["target_log_ratio"] = np.log(result["target_price"] / result["median_price_usd"])
    return result
