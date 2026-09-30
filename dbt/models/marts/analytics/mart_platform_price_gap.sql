-- Q: Is Amazon or Flipkart cheaper for the *same* product on the *same* day?
-- Grain: price_date x model_name x condition, only where both platforms listed it
-- (a matched-pairs design, so product mix cannot bias the comparison).

with daily as (

    select * from {{ ref('fct_daily_market_prices') }}

),

paired as (

    select
        amazon.price_date,
        amazon.product_category,
        amazon.model_name,
        amazon.condition,
        amazon.launch_price_usd,
        amazon.median_price_usd     as amazon_price_usd,
        flipkart.median_price_usd   as flipkart_price_usd,
        case
            when amazon.is_sale_event = 1 or flipkart.is_sale_event = 1 then 1 else 0
        end                         as any_sale_event

    from daily as amazon
    inner join daily as flipkart
        on  amazon.price_date = flipkart.price_date
        and amazon.model_name = flipkart.model_name
        and amazon.condition  = flipkart.condition
    where amazon.platform = 'Amazon'
      and flipkart.platform = 'Flipkart'

)

select
    *,
    amazon_price_usd - flipkart_price_usd                                   as gap_usd,
    (amazon_price_usd - flipkart_price_usd) / flipkart_price_usd * 100      as gap_pct,
    case
        when amazon_price_usd < flipkart_price_usd then 'Amazon'
        when flipkart_price_usd < amazon_price_usd then 'Flipkart'
        else 'Tie'
    end                                                                     as cheaper_platform
from paired
