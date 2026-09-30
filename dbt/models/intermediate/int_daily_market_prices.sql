-- Grain: price_date x platform x model_name x condition ("series-day").
-- The raw feed has ~1.4 listings per series-day (21,389 extra rows share a
-- business key), so every downstream time-series analysis works at this grain.

select
    price_date,
    platform,
    product_category,
    model_name,
    condition,

    max(launch_price_usd)                                   as launch_price_usd,
    min(current_price_usd)                                  as min_price_usd,
    median(current_price_usd)                               as median_price_usd,
    max(current_price_usd)                                  as max_price_usd,
    avg(current_price_usd)                                  as avg_price_usd,
    count(*)                                                as listing_count,

    avg(rating)                                             as avg_rating,
    median(reviews_count)                                   as median_reviews,
    avg(cast(is_in_stock as {{ dbt.type_float() }}))        as in_stock_share,
    avg(cast(is_low_stock as {{ dbt.type_float() }}))       as low_stock_share,
    avg(cast(is_out_of_stock as {{ dbt.type_float() }}))    as out_of_stock_share,

    max(is_sale_event)                                      as is_sale_event,
    coalesce(
        max(case when sale_event <> 'No Event' then sale_event end),
        'No Event'
    )                                                       as sale_event

from {{ ref('stg_apple_prices') }}
group by 1, 2, 3, 4, 5
