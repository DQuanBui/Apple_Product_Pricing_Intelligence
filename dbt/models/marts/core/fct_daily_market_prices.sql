-- Grain: series-day (platform x model x condition x date). The central fact for
-- time-series analysis, forecasting (features are built from this table) and BI.

with daily as (

    select * from {{ ref('int_daily_market_prices') }}

),

product as (

    select model_name, release_date, successor_release_date
    from {{ ref('dim_product') }}

),

enriched as (

    select
        daily.platform || ' | ' || daily.model_name || ' | ' || daily.condition   as series_id,
        daily.*,
        daily.median_price_usd / daily.launch_price_usd * 100                     as price_index,
        (daily.launch_price_usd - daily.median_price_usd)
            / daily.launch_price_usd * 100                                        as discount_pct,
        daily.max_price_usd - daily.min_price_usd                                 as price_range_usd,
        {{ dbt.datediff('product.release_date', 'daily.price_date', 'day') }}    as days_since_release,
        product.successor_release_date,
        case
            when product.successor_release_date is not null
             and daily.price_date >= product.successor_release_date then 1
            else 0
        end                                                                       as is_successor_released,

        -- "Normal" price = mean of the previous 30 non-event observations of the
        -- same series. Event days are excluded so a sale does not lower its own
        -- baseline; the current row is excluded to avoid look-ahead.
        avg(case when daily.is_sale_event = 0 then daily.median_price_usd end) over (
            partition by daily.platform, daily.model_name, daily.condition
            order by daily.price_date
            rows between 30 preceding and 1 preceding
        )                                                                         as baseline_price_30obs_usd,

        row_number() over (
            partition by daily.platform, daily.model_name, daily.condition
            order by daily.price_date desc
        )                                                                         as recency_rank

    from daily
    inner join product
        on daily.model_name = product.model_name

)

select
    *,
    floor(days_since_release / 30.4375)                                           as months_since_release,
    (baseline_price_30obs_usd - median_price_usd)
        / nullif(baseline_price_30obs_usd, 0) * 100                               as savings_vs_baseline_pct,
    case when recency_rank = 1 then 1 else 0 end                                  as is_latest_observation
from enriched
