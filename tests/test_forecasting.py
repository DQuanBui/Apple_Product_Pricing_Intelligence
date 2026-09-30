import numpy as np
import pandas as pd
import pytest

from apple_pricing.forecasting.features import add_target, asof_series_value, build_features
from apple_pricing.forecasting.train import conformal_adjustment, time_split


def make_daily(dates, prices, platform="Amazon", model="iPhone 15 128GB", condition="New"):
    dates = pd.to_datetime(dates)
    n = len(dates)
    return pd.DataFrame(
        {
            "price_date": dates,
            "platform": platform,
            "product_category": "iPhone",
            "model_name": model,
            "condition": condition,
            "launch_price_usd": 799.0,
            "min_price_usd": prices,
            "median_price_usd": prices,
            "max_price_usd": prices,
            "listing_count": 1,
            "avg_rating": 4.5,
            "median_reviews": 100.0,
            "in_stock_share": 1.0,
            "out_of_stock_share": 0.0,
            "is_sale_event": 0,
            "sale_event": "No Event",
            "price_index": np.asarray(prices) / 799 * 100,
            "days_since_release": np.arange(n) * 3,
            "is_successor_released": 0,
            "successor_release_date": pd.NaT,
            "baseline_price_30obs_usd": np.nan,
        }
    )


@pytest.fixture
def irregular_series():
    # Irregular spacing on purpose: row-based shifts would give wrong answers here.
    dates = ["2025-01-01", "2025-01-03", "2025-01-08", "2025-01-09", "2025-01-20", "2025-02-15"]
    prices = [700.0, 710.0, 720.0, 730.0, 740.0, 750.0]
    return make_daily(dates, prices)


def test_backward_lag_uses_calendar_time_not_rows(irregular_series):
    lagged = asof_series_value(irregular_series, -7, "backward", tolerance_days=7)
    # 2025-01-09 minus 7 days = 2025-01-02 -> latest observation on/before is 2025-01-01.
    assert lagged[3] == 700.0
    # 2025-01-20 minus 7 = 2025-01-13 -> latest on/before is 2025-01-09.
    assert lagged[4] == 730.0
    # 2025-02-15 minus 7 = 2025-02-08 -> last obs 2025-01-20 is 19 days earlier: beyond tolerance.
    assert np.isnan(lagged[5])


def test_lags_never_look_ahead(irregular_series):
    for offset in (-7, -14, -30):
        lagged = asof_series_value(irregular_series, offset, "backward", tolerance_days=60)
        for row, value in enumerate(lagged):
            if np.isnan(value):
                continue
            source_date = irregular_series.loc[irregular_series["median_price_usd"] == value, "price_date"].iloc[0]
            assert source_date <= irregular_series["price_date"].iloc[row] + pd.Timedelta(days=offset)


def test_target_is_future_within_tolerance(irregular_series):
    labelled = add_target(irregular_series, horizon_days=7)
    # 2025-01-01 + 7 = 2025-01-08 exists exactly.
    assert labelled.loc[0, "target_price"] == 720.0
    # 2025-01-03 + 7 = 2025-01-10 -> first obs on/after is 2025-01-20 (10 days late): no target.
    assert np.isnan(labelled.loc[1, "target_price"])
    assert labelled.loc[0, "target_log_ratio"] == pytest.approx(np.log(720 / 700))


def test_series_do_not_leak_into_each_other():
    amazon = make_daily(["2025-01-01", "2025-01-08"], [700.0, 720.0], platform="Amazon")
    flipkart = make_daily(["2025-01-05"], [999.0], platform="Flipkart")
    data = pd.concat([amazon, flipkart], ignore_index=True).sort_values(["platform", "price_date"])
    data = data.reset_index(drop=True)
    target = add_target(data, horizon_days=3)
    amazon_first = target[(target.platform == "Amazon") & (target.price_date == "2025-01-01")]
    # Flipkart's 2025-01-05 price must not become Amazon's 3-day target.
    assert np.isnan(amazon_first["target_price"].iloc[0])


def test_rolling_features_exclude_current_day(irregular_series):
    features = build_features(irregular_series)
    row = features.iloc[3]  # 2025-01-09, previous 7 days contain 2025-01-03 and 2025-01-08
    expected_mean = np.mean([710.0, 720.0])
    assert row["vs_roll_mean_7d"] == pytest.approx(730.0 / expected_mean - 1)


def test_time_split_has_embargo_between_folds():
    dates = pd.date_range("2022-01-01", "2026-07-31", freq="D")
    data = pd.DataFrame({"price_date": dates})
    for horizon in (7, 30):
        split = time_split(data, horizon)
        gap = pd.Timedelta(days=horizon + 3)
        assert split["train"]["price_date"].max() + gap < split["validation"]["price_date"].min()
        assert split["validation"]["price_date"].max() + gap < split["test"]["price_date"].min()


def test_conformal_margin_reaches_target_coverage():
    rng = np.random.default_rng(0)
    actual = rng.normal(0, 1, 5_000)
    # Deliberately too-narrow quantiles (true 10/90% points are +/-1.28).
    quantiles = np.column_stack([np.full(5_000, -0.5), np.zeros(5_000), np.full(5_000, 0.5)])
    margin = conformal_adjustment(quantiles, actual)
    covered = (actual >= quantiles[:, 0] - margin) & (actual <= quantiles[:, 2] + margin)
    assert covered.mean() == pytest.approx(0.8, abs=0.01)
