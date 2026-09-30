-- Q: What happens to a product's price when Apple launches its successor?
-- Compares the average price index (New condition) in the 60 days before the
-- successor's release with days 0-59 and 60-119 after it.
-- Grain: one row per model that has a tracked successor.

with daily as (

    select
        d.model_name,
        d.product_category,
        d.price_index,
        {{ dbt.datediff('p.successor_release_date', 'd.price_date', 'day') }} as days_from_successor_release
    from {{ ref('fct_daily_market_prices') }} as d
    inner join {{ ref('dim_product') }} as p
        on d.model_name = p.model_name
    where d.condition = 'New'
      and p.successor_release_date is not null

),

windows as (

    select
        model_name,
        product_category,
        avg(case when days_from_successor_release between -60 and -1 then price_index end)  as index_60d_before,
        avg(case when days_from_successor_release between 0 and 59 then price_index end)    as index_0_59d_after,
        avg(case when days_from_successor_release between 60 and 119 then price_index end)  as index_60_119d_after,
        sum(case when days_from_successor_release between -60 and -1 then 1 else 0 end)     as obs_before,
        sum(case when days_from_successor_release between 0 and 59 then 1 else 0 end)       as obs_after
    from daily
    group by 1, 2

)

select
    w.model_name,
    w.product_category,
    p.successor_model_name,
    p.successor_release_date,
    w.index_60d_before,
    w.index_0_59d_after,
    w.index_60_119d_after,
    w.index_0_59d_after - w.index_60d_before                           as index_change_pts,
    (w.index_0_59d_after - w.index_60d_before) / w.index_60d_before * 100
                                                                        as price_change_pct,
    w.obs_before,
    w.obs_after
from windows as w
inner join {{ ref('dim_product') }} as p
    on w.model_name = p.model_name
where w.obs_before >= 10
  and w.obs_after >= 10
