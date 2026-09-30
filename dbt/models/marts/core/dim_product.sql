-- Grain: one row per tracked Apple model. Conformed product dimension for
-- every fact and mart (Power BI relates on model_name).

with observed as (

    select
        model_name,
        max(launch_price_usd)   as msrp_usd,
        min(price_date)         as first_observed_date,
        max(price_date)         as last_observed_date,
        count(*)                as listing_snapshots
    from {{ ref('stg_apple_prices') }}
    group by 1

),

catalog as (

    select * from {{ ref('product_catalog') }}

)

select
    row_number() over (
        order by catalog.product_category, catalog.product_line, catalog.release_date
    )                                           as product_key,
    catalog.model_name,
    catalog.product_category,
    catalog.product_line,
    catalog.tier,
    catalog.generation,
    catalog.chip,
    catalog.storage_gb,
    catalog.display_size,
    catalog.release_date,
    extract(year from catalog.release_date)     as release_year,
    observed.msrp_usd,
    catalog.successor_model_name,
    successor.release_date                      as successor_release_date,
    observed.first_observed_date,
    observed.last_observed_date,
    observed.listing_snapshots

from catalog
inner join observed
    on catalog.model_name = observed.model_name
left join catalog as successor
    on catalog.successor_model_name = successor.model_name
