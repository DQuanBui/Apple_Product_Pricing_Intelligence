-- Q: How much do sale events *really* save a buyer?
-- The headline discount is measured against launch MSRP, which overstates the
-- saving for older products that were already cheap. The honest measure is the
-- saving versus the same series' normal (non-event) price just before the event.
-- Grain: sale_event x product_category (with 'No Event' as the control row).

with daily as (

    select *
    from {{ ref('fct_daily_market_prices') }}
    where baseline_price_30obs_usd is not null

)

select
    sale_event,
    product_category,
    count(*)                                                    as series_days,
    avg(discount_pct)                                           as avg_discount_vs_msrp_pct,
    avg(savings_vs_baseline_pct)                                as avg_savings_vs_baseline_pct,
    median(savings_vs_baseline_pct)                             as median_savings_vs_baseline_pct,
    avg(case when savings_vs_baseline_pct >= 5 then 1.0 else 0.0 end) * 100
                                                                as pct_days_saving_5pct_plus,
    avg(in_stock_share) * 100                                   as avg_in_stock_pct,
    avg(baseline_price_30obs_usd - median_price_usd)            as avg_savings_usd
from daily
group by 1, 2
