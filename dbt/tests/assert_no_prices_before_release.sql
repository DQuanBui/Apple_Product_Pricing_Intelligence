-- A listing cannot exist before the product was released (1-day tolerance for
-- time-zone differences between the marketplace and Apple's US launch date).
select
    p.price_observation_id,
    p.model_name,
    p.price_date,
    c.release_date
from {{ ref('stg_apple_prices') }} as p
inner join {{ ref('product_catalog') }} as c
    on p.model_name = c.model_name
where p.price_date < {{ dbt.dateadd('day', -1, 'c.release_date') }}
