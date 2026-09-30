-- One row per model: the "product card" used by the dashboard and Power BI.
-- Current price = median series-day price for New units over the last 30 days
-- of data; all other metrics use the full history.

with daily as (

    select * from {{ ref('fct_daily_market_prices') }}

),

data_end as (

    select max(price_date) as max_date from daily

),

recent_new as (

    select
        daily.model_name,
        median(daily.median_price_usd)  as current_price_usd,
        median(daily.price_index)       as current_price_index
    from daily
    cross join data_end
    where daily.condition = 'New'
      and daily.price_date > {{ dbt.dateadd('day', -30, 'data_end.max_date') }}
    group by 1

),

history as (

    select
        model_name,
        count(*)                                                            as series_days,
        avg(price_index)                                                    as avg_price_index,
        avg(case when median_price_usd > launch_price_usd then 1.0 else 0.0 end) * 100
                                                                            as pct_days_above_msrp,
        avg(case when is_sale_event = 1 then savings_vs_baseline_pct end)   as avg_event_savings_pct,
        stddev(savings_vs_baseline_pct)                                     as price_volatility_pct
    from daily
    group by 1

),

platform as (

    select
        model_name,
        count(*)                                                            as matched_days,
        avg(case when cheaper_platform = 'Amazon' then 1.0 else 0.0 end) * 100
                                                                            as pct_days_amazon_cheaper,
        avg(gap_pct)                                                        as avg_amazon_vs_flipkart_pct
    from {{ ref('mart_platform_price_gap') }}
    group by 1

),

refurb as (

    -- Matched new vs refurbished on the same platform and day.
    select
        new_units.model_name,
        avg((new_units.median_price_usd - refurb_units.median_price_usd)
            / new_units.median_price_usd * 100)                             as refurbished_discount_pct
    from daily as new_units
    inner join daily as refurb_units
        on  new_units.price_date = refurb_units.price_date
        and new_units.platform   = refurb_units.platform
        and new_units.model_name = refurb_units.model_name
    where new_units.condition = 'New'
      and refurb_units.condition = 'Refurbished'
    group by 1

)

select
    p.product_key,
    p.model_name,
    p.product_category,
    p.product_line,
    p.tier,
    p.release_date,
    p.msrp_usd,
    {{ dbt.datediff('p.release_date', 'data_end.max_date', 'month') }}     as months_since_release,
    r.current_price_usd,
    r.current_price_index,
    (100 - r.current_price_index)
        / nullif({{ dbt.datediff('p.release_date', 'data_end.max_date', 'month') }}, 0)
                                                                            as avg_monthly_depreciation_pts,
    h.series_days,
    h.avg_price_index,
    h.pct_days_above_msrp,
    h.avg_event_savings_pct,
    h.price_volatility_pct,
    pl.pct_days_amazon_cheaper,
    pl.avg_amazon_vs_flipkart_pct,
    rf.refurbished_discount_pct,
    case when p.successor_release_date is not null then 1 else 0 end        as has_successor
from {{ ref('dim_product') }} as p
cross join data_end
left join recent_new as r  on p.model_name = r.model_name
left join history as h     on p.model_name = h.model_name
left join platform as pl   on p.model_name = pl.model_name
left join refurb as rf     on p.model_name = rf.model_name
