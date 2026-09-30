-- The feed's reported discount must agree with (MSRP - price) / MSRP within 0.15 pp.
-- A failure here means the source changed how it computes discounts.
select
    price_observation_id,
    reported_discount_pct,
    discount_pct,
    abs(reported_discount_pct - discount_pct) as discount_gap_pp
from {{ ref('stg_apple_prices') }}
where abs(reported_discount_pct - discount_pct) > 0.15
