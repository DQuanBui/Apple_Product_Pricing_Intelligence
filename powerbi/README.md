# Power BI Report

The Power BI report sits on the same dbt marts as the Streamlit app, so both show identical numbers.

## Connection

| Mode | Source | When to use |
|---|---|---|
| **Snowflake (recommended)** | `APPLE_PRICING.MARTS`, role `REPORTER`, warehouse `TRANSFORM_WH` | Import mode with scheduled refresh after the pipeline runs |
| Parquet files | `data/marts/*.parquet` (Get Data → Parquet) | Local development without Snowflake |

Load only the `MARTS` schema. Staging and intermediate objects are not part of the reporting contract.

## Data model (star schema)

```
                 dim_date (date_day)
                        │ 1
                        │
                        * price_date
dim_product ─1───*  fct_daily_market_prices      fct_price_observations *───1─ dim_product
 (model_name)            (series-day grain)        (listing grain)

dim_product ─1───*  mart_deal_scores · mart_forecast_backtest · mart_platform_price_gap
dim_product ─1───1  mart_model_scorecard · mart_successor_launch_impact
```

- Relationships are single-direction from dimension to fact.
- Mark `dim_date` as the date table (`date_day`).
- Hide surrogate and technical columns (`series_id`, `recency_rank`, `is_latest_observation`).
- `mart_sale_event_impact` and `mart_depreciation_curve` are pre-aggregated. Use them as standalone visuals rather than relating them to the facts.

## DAX measures

```DAX
Avg Price = AVERAGE ( fct_daily_market_prices[median_price_usd] )

Price Index =
DIVIDE (
    SUM ( fct_daily_market_prices[median_price_usd] ),
    SUM ( fct_daily_market_prices[launch_price_usd] )
) * 100

Discount vs MSRP % = 100 - [Price Index]

Savings vs Normal % =
AVERAGEX (
    FILTER ( fct_daily_market_prices, NOT ISBLANK ( fct_daily_market_prices[baseline_price_30obs_usd] ) ),
    fct_daily_market_prices[savings_vs_baseline_pct]
)

Event Savings vs Normal % =
CALCULATE ( [Savings vs Normal %], fct_daily_market_prices[is_sale_event] = 1 )

Amazon Cheaper % =
DIVIDE (
    COUNTROWS ( FILTER ( mart_platform_price_gap, mart_platform_price_gap[cheaper_platform] = "Amazon" ) ),
    COUNTROWS ( mart_platform_price_gap )
)

Forecast MAE = AVERAGE ( mart_forecast_backtest[model_abs_error_usd] )
Naive MAE = AVERAGE ( mart_forecast_backtest[naive_abs_error_usd] )
MAE Improvement vs Naive % = DIVIDE ( [Naive MAE] - [Forecast MAE], [Naive MAE] ) * 100
Interval Coverage % = AVERAGE ( mart_forecast_backtest[is_within_interval] ) * 100

Buy Now Series =
CALCULATE ( COUNTROWS ( mart_deal_scores ), mart_deal_scores[recommendation] = "Buy now" )
```

## Report pages

1. **Executive summary.** KPI cards (listings, models, avg price index, event savings vs normal, forecast MAE), the depreciation curve by category, and key-finding text boxes.
2. **Product life cycle.** Line chart of price index by `months_since_release` and category, the successor-launch impact bar chart, and a model scorecard table.
3. **Sale events.** Clustered bars of headline discount vs savings vs normal price by event, plus a category × event matrix.
4. **Marketplaces and condition.** Histogram of `gap_pct`, the Amazon Cheaper % card, and refurbished discount by model.
5. **Forecasts and deals.** Forecast vs baseline MAE by category and horizon, the coverage card, and a deal table with conditional formatting on `recommendation` and `deal_score`.

Slicers on every page: product category, platform, condition, and date (from `dim_date`).

## Colours

Use the same fixed colours as the Streamlit app so visuals match across tools:

| Category | Hex | Platform | Hex |
|---|---|---|---|
| iPhone | `#2a78d6` | Amazon | `#4a3aa7` |
| iPad | `#eb6834` | Flipkart | `#e87ba4` |
| Mac | `#1baf7a` | | |
| Watch | `#eda100` | | |
