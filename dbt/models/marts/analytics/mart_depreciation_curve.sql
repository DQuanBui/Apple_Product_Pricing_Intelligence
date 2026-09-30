-- Q: How fast does each category lose value after release?
-- Uses months since the official release date (from the product catalog), not
-- "first seen in the dataset", so products launched before the data window
-- are placed at the right point of their life cycle.
-- Grain: product_category x condition x months_since_release.

select
    product_category,
    condition,
    months_since_release,
    median(price_index)             as median_price_index,
    avg(price_index)                as avg_price_index,
    count(*)                        as series_days,
    count(distinct model_name)      as models
from {{ ref('fct_daily_market_prices') }}
where months_since_release between 0 and 60
group by 1, 2, 3
