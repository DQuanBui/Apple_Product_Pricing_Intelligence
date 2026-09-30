-- Grain: one marketplace listing snapshot. Cleans, standardises and types the raw feed;
-- no business logic beyond simple derived flags.

with source as (

    select * from {{ source('raw', 'apple_prices') }}

),

standardised as (

    select
        cast(observation_date as date)                                  as price_date,

        case lower(trim(platform))
            when 'amazon' then 'Amazon'
            when 'flipkart' then 'Flipkart'
            else trim(platform)
        end                                                             as platform,

        trim(product_category)                                          as product_category,
        trim(model_name)                                                as model_name,

        case
            when lower(trim(condition)) in ('renewed', 'refurbished', 'renewed/refurbished')
                then 'Refurbished'
            else trim(condition)
        end                                                             as condition,

        case
            when sale_event is null or trim(sale_event) in ('', 'None') then 'No Event'
            else trim(sale_event)
        end                                                             as sale_event,

        case lower(trim(stock_status))
            when 'in stock' then 'In Stock'
            when 'low stock' then 'Low Stock'
            when 'out of stock' then 'Out of Stock'
            else trim(stock_status)
        end                                                             as stock_status,

        cast(launch_price_usd as {{ dbt.type_float() }})                as launch_price_usd,
        cast(current_price_usd as {{ dbt.type_float() }})               as current_price_usd,
        cast(discount_pct as {{ dbt.type_float() }})                    as reported_discount_pct,
        cast(rating as {{ dbt.type_float() }})                          as rating,
        cast(reviews_count as {{ dbt.type_int() }})                     as reviews_count,
        _ingested_at

    from source

),

keyed as (

    select
        {{ dbt.hash(dbt.concat([
            "cast(price_date as " ~ dbt.type_string() ~ ")", "'|'",
            "platform", "'|'", "model_name", "'|'", "condition", "'|'",
            "cast(current_price_usd as " ~ dbt.type_string() ~ ")", "'|'",
            "stock_status", "'|'",
            "cast(rating as " ~ dbt.type_string() ~ ")", "'|'",
            "cast(reviews_count as " ~ dbt.type_string() ~ ")"
        ])) }}                                                          as price_observation_id,
        *
    from standardised

),

deduplicated as (

    -- Exact duplicate snapshots are dropped (0 in the current extract, but the
    -- rule protects the marts if the feed ever double-delivers a file).
    select *
    from keyed
    qualify row_number() over (
        partition by price_observation_id
        order by _ingested_at desc
    ) = 1

)

select
    price_observation_id,
    price_date,
    platform,
    product_category,
    model_name,
    condition,
    sale_event,
    stock_status,
    launch_price_usd,
    current_price_usd,
    reported_discount_pct,
    (launch_price_usd - current_price_usd) / launch_price_usd * 100    as discount_pct,
    current_price_usd / launch_price_usd * 100                          as price_index,
    rating,
    reviews_count,

    case when sale_event <> 'No Event' then 1 else 0 end                as is_sale_event,
    case when stock_status = 'In Stock' then 1 else 0 end               as is_in_stock,
    case when stock_status = 'Low Stock' then 1 else 0 end              as is_low_stock,
    case when stock_status = 'Out of Stock' then 1 else 0 end           as is_out_of_stock,
    case when current_price_usd > launch_price_usd then 1 else 0 end    as is_above_msrp

from deduplicated
