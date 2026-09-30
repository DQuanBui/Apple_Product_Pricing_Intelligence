"""Train 7- and 30-day CatBoost quantile forecasts and publish results to the warehouse.

Design choices:
- Target is the log price *ratio* log(future / current), so one model can serve
  $329 iPads and $1,999 MacBooks; predictions are converted back to dollars.
- One MultiQuantile model gives P10 / P50 / P90. P50 is the point forecast
  (it minimises MAE); P10-P90 is an 80% interval used for buy/wait calls.
  The raw quantile interval is widened by split-conformal calibration on the
  validation fold so its empirical coverage matches the nominal 80%.
- Chronological train / validation / test split with an embargo of
  horizon + 3 days between folds, so no training target overlaps a later fold.
- Two baselines: naive last price, and the 30-day trailing mean. The model has
  to beat the *stronger* one to be worth using.
"""

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor, Pool

from apple_pricing.config import FORECAST_HORIZONS, MARTS_EXPORT_DIR, MODEL_DIR, RANDOM_STATE
from apple_pricing.forecasting.features import (
    CATEGORICAL_FEATURES,
    MODEL_FEATURES,
    SERIES_KEYS,
    TARGET_TOLERANCE_DAYS,
    add_target,
    build_features,
    load_daily,
)

QUANTILES = (0.1, 0.5, 0.9)
TARGET_COVERAGE = 0.8
TEST_DAYS = 180
VALIDATION_DAYS = 180


def regression_metrics(actual, predicted) -> dict:
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    mask = np.isfinite(actual) & np.isfinite(predicted)
    actual, predicted = actual[mask], predicted[mask]
    error = actual - predicted

    return {
        "MAE": float(np.mean(np.abs(error))),
        "RMSE": float(np.sqrt(np.mean(error**2))),
        "WAPE_pct": float(np.sum(np.abs(error)) / np.sum(np.abs(actual)) * 100),
        "MAPE_pct": float(np.mean(np.abs(error / actual)) * 100),
        "R2": float(1 - np.sum(error**2) / np.sum((actual - actual.mean()) ** 2)),
        "n": int(mask.sum()),
    }


def time_split(data: pd.DataFrame, horizon_days: int) -> dict:
    """Chronological split with an embargo between folds.

    A row dated d has a target dated up to d + horizon + tolerance, so each
    fold ends `embargo` days before the next one starts.
    """
    embargo = pd.Timedelta(days=horizon_days + TARGET_TOLERANCE_DAYS)
    last_date = data["price_date"].max()

    test_start = last_date - pd.Timedelta(days=TEST_DAYS)
    validation_end = test_start - embargo
    validation_start = validation_end - pd.Timedelta(days=VALIDATION_DAYS)
    train_end = validation_start - embargo

    dates = data["price_date"]
    return {
        "train": data[dates < train_end],
        "validation": data[(dates >= validation_start) & (dates < validation_end)],
        "test": data[dates >= test_start],
        "boundaries": {
            "train_end_exclusive": str(train_end.date()),
            "validation_start": str(validation_start.date()),
            "validation_end_exclusive": str(validation_end.date()),
            "test_start": str(test_start.date()),
            "test_end": str(last_date.date()),
            "embargo_days": embargo.days,
        },
    }


def make_model(iterations: int = 3000) -> CatBoostRegressor:
    return CatBoostRegressor(
        loss_function=f"MultiQuantile:alpha={','.join(str(q) for q in QUANTILES)}",
        iterations=iterations,
        learning_rate=0.08,
        depth=6,
        l2_leaf_reg=5,
        random_seed=RANDOM_STATE,
        allow_writing_files=False,
        verbose=False,
    )


def predict_log_ratio(model: CatBoostRegressor, frame: pd.DataFrame) -> np.ndarray:
    log_ratio = model.predict(Pool(frame[MODEL_FEATURES], cat_features=CATEGORICAL_FEATURES))
    # Quantile crossing is rare but possible; sorting restores P10 <= P50 <= P90.
    return np.sort(log_ratio, axis=1)


def conformal_adjustment(log_ratio: np.ndarray, actual_log_ratio: np.ndarray) -> float:
    """Split-conformal (CQR) margin that makes [P10 - m, P90 + m] cover TARGET_COVERAGE."""
    scores = np.maximum(log_ratio[:, 0] - actual_log_ratio, actual_log_ratio - log_ratio[:, 2])
    level = min(1.0, TARGET_COVERAGE * (1 + 1 / len(scores)))
    return float(np.quantile(scores, level))


def to_prices(log_ratio: np.ndarray, frame: pd.DataFrame, margin: float = 0.0) -> np.ndarray:
    """Convert (n, 3) log-ratio quantiles to prices, widening the interval by `margin`."""
    adjusted = log_ratio + np.array([-margin, 0.0, margin])
    return frame["median_price_usd"].to_numpy()[:, None] * np.exp(adjusted)


def train_horizon(features: pd.DataFrame, horizon_days: int) -> dict:
    data = add_target(features, horizon_days)
    labelled = data.dropna(subset=["target_log_ratio", "ret_7d", "vs_roll_mean_30d"])
    split = time_split(labelled, horizon_days)
    train, validation, test = split["train"], split["validation"], split["test"]

    model = make_model()
    model.fit(
        Pool(train[MODEL_FEATURES], train["target_log_ratio"], cat_features=CATEGORICAL_FEATURES),
        eval_set=Pool(
            validation[MODEL_FEATURES], validation["target_log_ratio"], cat_features=CATEGORICAL_FEATURES
        ),
        early_stopping_rounds=200,
    )
    best_iterations = model.get_best_iteration() + 1

    margin = conformal_adjustment(
        predict_log_ratio(model, validation), validation["target_log_ratio"].to_numpy()
    )
    test_log_ratio = predict_log_ratio(model, test)
    raw_quantiles = to_prices(test_log_ratio, test)
    quantiles = to_prices(test_log_ratio, test, margin)
    actual = test["target_price"].to_numpy()
    naive = test["median_price_usd"].to_numpy()
    trailing_mean = test["roll_mean_30d"].fillna(test["median_price_usd"]).to_numpy()

    model_metrics = regression_metrics(actual, quantiles[:, 1])
    naive_metrics = regression_metrics(actual, naive)
    trailing_metrics = regression_metrics(actual, trailing_mean)
    coverage = float(np.mean((actual >= quantiles[:, 0]) & (actual <= quantiles[:, 2])) * 100)
    raw_coverage = float(np.mean((actual >= raw_quantiles[:, 0]) & (actual <= raw_quantiles[:, 2])) * 100)

    backtest = test[["price_date", "product_category", *SERIES_KEYS, "median_price_usd", "target_price"]].copy()
    backtest = backtest.rename(columns={"median_price_usd": "current_price_usd", "target_price": "actual_price_usd"})
    backtest["horizon_days"] = horizon_days
    backtest["pred_p10_usd"] = quantiles[:, 0]
    backtest["pred_p50_usd"] = quantiles[:, 1]
    backtest["pred_p90_usd"] = quantiles[:, 2]
    backtest["baseline_trailing_30d_usd"] = trailing_mean
    backtest["abs_error_usd"] = np.abs(backtest["actual_price_usd"] - backtest["pred_p50_usd"])

    by_category = (
        backtest.assign(
            naive_abs_error=np.abs(actual - naive),
            trailing_abs_error=np.abs(actual - trailing_mean),
        )
        .groupby("product_category")[["abs_error_usd", "naive_abs_error", "trailing_abs_error"]]
        .mean()
        .round(2)
        .rename(columns={"abs_error_usd": "model_mae", "naive_abs_error": "naive_mae", "trailing_abs_error": "trailing_30d_mae"})
        .to_dict(orient="index")
    )

    importance = (
        pd.Series(model.get_feature_importance(), index=MODEL_FEATURES)
        .sort_values(ascending=False)
        .round(2)
    )

    # Final model: same settings, refit on every labelled row, used for live forecasts.
    final_model = make_model(iterations=best_iterations)
    final_model.fit(Pool(labelled[MODEL_FEATURES], labelled["target_log_ratio"], cat_features=CATEGORICAL_FEATURES))

    latest = data.sort_values("price_date").groupby(SERIES_KEYS, as_index=False).tail(1).copy()
    latest_quantiles = to_prices(predict_log_ratio(final_model, latest), latest, margin)
    forecast = latest[["price_date", "product_category", *SERIES_KEYS, "median_price_usd"]].rename(
        columns={"price_date": "as_of_date", "median_price_usd": "current_price_usd"}
    )
    forecast["horizon_days"] = horizon_days
    forecast["pred_p10_usd"] = latest_quantiles[:, 0]
    forecast["pred_p50_usd"] = latest_quantiles[:, 1]
    forecast["pred_p90_usd"] = latest_quantiles[:, 2]

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    final_model.save_model(str(MODEL_DIR / f"price_forecast_{horizon_days}d.cbm"))
    model.save_model(str(MODEL_DIR / f"price_forecast_{horizon_days}d_backtest.cbm"))

    metrics = {
        "horizon_days": horizon_days,
        "model": model_metrics,
        "baseline_naive_last_price": naive_metrics,
        "baseline_trailing_30d_mean": trailing_metrics,
        "mae_improvement_vs_naive_pct": (naive_metrics["MAE"] - model_metrics["MAE"]) / naive_metrics["MAE"] * 100,
        "mae_improvement_vs_trailing_30d_pct": (trailing_metrics["MAE"] - model_metrics["MAE"])
        / trailing_metrics["MAE"]
        * 100,
        "p10_p90_interval_coverage_pct": coverage,
        "p10_p90_raw_quantile_coverage_pct": raw_coverage,
        "conformal_margin_log": margin,
        "mae_by_category": by_category,
        "split": split["boundaries"],
        "rows": {"train": len(train), "validation": len(validation), "test": len(test)},
        "best_iterations": best_iterations,
        "top_features": importance.head(15).to_dict(),
    }

    return {"metrics": metrics, "backtest": backtest, "forecast": forecast}


def run(warehouse) -> dict:
    daily = load_daily(warehouse)
    features = build_features(daily)

    results = {}
    for horizon in FORECAST_HORIZONS:
        print(f"Training {horizon}-day forecast...")
        results[horizon] = train_horizon(features, horizon)
        m = results[horizon]["metrics"]
        print(
            f"  MAE ${m['model']['MAE']:.2f} | naive ${m['baseline_naive_last_price']['MAE']:.2f} "
            f"({m['mae_improvement_vs_naive_pct']:.1f}% better) | trailing-30d "
            f"${m['baseline_trailing_30d_mean']['MAE']:.2f} ({m['mae_improvement_vs_trailing_30d_pct']:.1f}% better) "
            f"| P10-P90 coverage {m['p10_p90_interval_coverage_pct']:.1f}%"
        )

    trained_at = datetime.now(timezone.utc).replace(tzinfo=None)
    backtest = pd.concat([r["backtest"] for r in results.values()], ignore_index=True)
    forecast = pd.concat([r["forecast"] for r in results.values()], ignore_index=True)
    for frame in (backtest, forecast):
        frame["trained_at"] = trained_at

    warehouse.write(backtest, "ml", "forecast_backtest")
    warehouse.write(forecast, "ml", "forecast_latest")

    metrics = {
        "trained_at": trained_at.isoformat(timespec="seconds"),
        "quantiles": list(QUANTILES),
        "features": MODEL_FEATURES,
        "horizons": {f"{h}d": results[h]["metrics"] for h in FORECAST_HORIZONS},
    }
    MARTS_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    with open(MARTS_EXPORT_DIR / "model_metrics.json", "w", encoding="utf-8") as file:
        json.dump(metrics, file, indent=2)

    return metrics


if __name__ == "__main__":
    from apple_pricing.warehouse import get_warehouse

    wh = get_warehouse()
    try:
        run(wh)
    finally:
        wh.close()
