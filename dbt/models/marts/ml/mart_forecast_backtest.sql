{{ config(tags=['ml']) }}

-- Out-of-sample predictions from the held-out test window, with the two
-- baselines alongside, so forecast accuracy can be sliced in BI tools.
-- Grain: horizon x series-day in the test window.

select
    horizon_days,
    price_date,
    platform,
    product_category,
    model_name,
    condition,
    current_price_usd,
    actual_price_usd,
    pred_p10_usd,
    pred_p50_usd,
    pred_p90_usd,
    baseline_trailing_30d_usd,
    abs(actual_price_usd - pred_p50_usd)                        as model_abs_error_usd,
    abs(actual_price_usd - current_price_usd)                   as naive_abs_error_usd,
    abs(actual_price_usd - baseline_trailing_30d_usd)           as trailing_abs_error_usd,
    case
        when actual_price_usd between pred_p10_usd and pred_p90_usd then 1 else 0
    end                                                         as is_within_interval
from {{ source('ml', 'forecast_backtest') }}
