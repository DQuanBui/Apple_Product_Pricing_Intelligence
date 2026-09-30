"""Export the marts to small Parquet files in data/marts/.

The Streamlit app reads these files, so the deployed app needs no warehouse
credentials; Power BI can use them in file mode as well.
"""

import pandas as pd

from apple_pricing.config import MARTS_EXPORT_DIR

EXPORTS = {
    "dim_product": "select * from marts.dim_product",
    "dim_date": "select * from marts.dim_date",
    "fct_daily_market_prices": """
        select
            price_date, series_id, platform, product_category, model_name, condition,
            launch_price_usd, min_price_usd, median_price_usd, max_price_usd, listing_count,
            avg_rating, in_stock_share, is_sale_event, sale_event, price_index, discount_pct,
            days_since_release, months_since_release, is_successor_released,
            baseline_price_30obs_usd, savings_vs_baseline_pct
        from marts.fct_daily_market_prices
    """,
    "mart_platform_price_gap": "select * from marts.mart_platform_price_gap",
    "mart_sale_event_impact": "select * from marts.mart_sale_event_impact",
    "mart_depreciation_curve": "select * from marts.mart_depreciation_curve",
    "mart_successor_launch_impact": "select * from marts.mart_successor_launch_impact",
    "mart_model_scorecard": "select * from marts.mart_model_scorecard",
    "mart_deal_scores": "select * from marts.mart_deal_scores",
    "mart_forecast_backtest": "select * from marts.mart_forecast_backtest",
}


def run(warehouse, dbt_results: pd.DataFrame | None = None) -> None:
    MARTS_EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    for name, sql in EXPORTS.items():
        data = warehouse.query(sql)
        for column in data.columns:
            if "date" in column and data[column].dtype == object:
                data[column] = pd.to_datetime(data[column])
        data.to_parquet(MARTS_EXPORT_DIR / f"{name}.parquet", index=False)
        print(f"Exported {name}: {len(data):,} rows")

    if dbt_results is not None and not dbt_results.empty:
        dbt_results.to_parquet(MARTS_EXPORT_DIR / "dbt_run_results.parquet", index=False)
        print(f"Exported dbt_run_results: {len(dbt_results):,} nodes")
