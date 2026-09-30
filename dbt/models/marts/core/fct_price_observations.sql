-- Grain: one marketplace listing snapshot (80K rows). The most granular fact;
-- used for distribution analysis, statistical tests and Power BI drill-through.

select
    p.price_observation_id,
    p.price_date,
    p.platform,
    p.product_category,
    p.model_name,
    p.condition,
    p.sale_event,
    p.stock_status,
    p.launch_price_usd,
    p.current_price_usd,
    p.discount_pct,
    p.price_index,
    p.rating,
    p.reviews_count,
    p.is_sale_event,
    p.is_in_stock,
    p.is_low_stock,
    p.is_out_of_stock,
    p.is_above_msrp,
    {{ dbt.datediff('d.release_date', 'p.price_date', 'day') }} as days_since_release

from {{ ref('stg_apple_prices') }} as p
inner join {{ ref('dim_product') }} as d
    on p.model_name = d.model_name
