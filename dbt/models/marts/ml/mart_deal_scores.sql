{{ config(tags=['ml']) }}

-- Q: For each listing series right now, should a buyer buy now or wait?
-- Combines the latest observed price, the series' normal (non-event) price,
-- and the calibrated 7- and 30-day forecasts written by the Python job.
-- Grain: one row per platform x model x condition series.

with forecasts as (

    select
        platform,
        model_name,
        condition,
        max(as_of_date)                                                        as as_of_date,
        max(current_price_usd)                                                 as current_price_usd,
        max(case when horizon_days = 7 then pred_p50_usd end)                  as forecast_7d_usd,
        max(case when horizon_days = 30 then pred_p10_usd end)                 as forecast_30d_p10_usd,
        max(case when horizon_days = 30 then pred_p50_usd end)                 as forecast_30d_usd,
        max(case when horizon_days = 30 then pred_p90_usd end)                 as forecast_30d_p90_usd
    from {{ source('ml', 'forecast_latest') }}
    group by 1, 2, 3

),

latest_state as (

    select
        platform,
        model_name,
        condition,
        product_category,
        launch_price_usd,
        price_index,
        baseline_price_30obs_usd,
        avg_rating,
        in_stock_share,
        days_since_release
    from {{ ref('fct_daily_market_prices') }}
    where is_latest_observation = 1

),

data_end as (

    select max(as_of_date) as max_as_of_date from forecasts

),

scored as (

    select
        f.platform || ' | ' || f.model_name || ' | ' || f.condition               as series_id,
        f.platform,
        s.product_category,
        f.model_name,
        f.condition,
        f.as_of_date,
        s.launch_price_usd,
        f.current_price_usd,
        s.price_index,
        s.baseline_price_30obs_usd,
        (s.baseline_price_30obs_usd - f.current_price_usd)
            / s.baseline_price_30obs_usd * 100                                    as discount_vs_normal_pct,
        f.forecast_7d_usd,
        f.forecast_30d_usd,
        f.forecast_30d_p10_usd,
        f.forecast_30d_p90_usd,
        (f.forecast_7d_usd - f.current_price_usd) / f.current_price_usd * 100    as expected_change_7d_pct,
        (f.forecast_30d_usd - f.current_price_usd) / f.current_price_usd * 100   as expected_change_30d_pct,
        f.current_price_usd - f.forecast_30d_usd                                  as expected_saving_if_wait_30d_usd,
        s.avg_rating,
        s.in_stock_share,
        s.days_since_release,
        case
            when f.as_of_date < {{ dbt.dateadd('day', -14, 'data_end.max_as_of_date') }} then 1
            else 0
        end                                                                       as is_stale

    from forecasts as f
    inner join latest_state as s
        on  f.platform = s.platform
        and f.model_name = s.model_name
        and f.condition = s.condition
    cross join data_end

)

select
    *,

    -- Rule order matters: a calibrated interval that excludes today's price is
    -- the strongest signal, then the point forecast, then today's discount.
    case
        when forecast_30d_p10_usd > current_price_usd then 'Buy now'
        when forecast_30d_p90_usd < current_price_usd then 'Wait'
        when expected_change_30d_pct >= 2 then 'Buy now'
        when expected_change_30d_pct <= -3 then 'Wait'
        when discount_vs_normal_pct >= 5 then 'Buy now'
        else 'No rush'
    end                                                                           as recommendation,

    case
        when forecast_30d_p10_usd > current_price_usd
            then 'Price is below the 80% forecast range for the next 30 days'
        when forecast_30d_p90_usd < current_price_usd
            then 'Price is above the 80% forecast range for the next 30 days'
        when expected_change_30d_pct >= 2
            then 'Forecast expects the price to rise'
        when expected_change_30d_pct <= -3
            then 'Forecast expects the price to fall'
        when discount_vs_normal_pct >= 5
            then 'Currently at least 5% below its normal price'
        else 'Price is close to normal and expected to stay flat'
    end                                                                           as recommendation_reason,

    -- 0-100 composite used to rank deals; weights favour price signals.
    round(100 * (
          0.45 * percent_rank() over (order by expected_change_30d_pct)
        + 0.35 * percent_rank() over (order by discount_vs_normal_pct)
        + 0.10 * percent_rank() over (order by avg_rating)
        + 0.10 * in_stock_share
    ), 1)                                                                         as deal_score

from scored
