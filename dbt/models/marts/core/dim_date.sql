-- Grain: one row per calendar day covering the observation window.
-- Month names are built with CASE rather than monthname()/to_char(), whose
-- output differs between DuckDB and Snowflake.

with spine as (

    {{ dbt.date_spine(
        "day",
        "cast('" ~ var('calendar_start', '2020-09-01') ~ "' as date)",
        "cast('" ~ var('calendar_end', '2026-10-01') ~ "' as date)"
    ) }}

),

days as (

    select cast(date_day as date) as date_day from spine

)

select
    date_day,
    extract(year from date_day)                             as year,
    extract(quarter from date_day)                          as quarter,
    extract(month from date_day)                            as month,
    case extract(month from date_day)
        when 1 then 'Jan' when 2 then 'Feb' when 3 then 'Mar' when 4 then 'Apr'
        when 5 then 'May' when 6 then 'Jun' when 7 then 'Jul' when 8 then 'Aug'
        when 9 then 'Sep' when 10 then 'Oct' when 11 then 'Nov' else 'Dec'
    end                                                     as month_name,
    cast(extract(year from date_day) as {{ dbt.type_string() }})
        || '-'
        || lpad(cast(extract(month from date_day) as {{ dbt.type_string() }}), 2, '0')
                                                            as year_month,
    {{ dbt.date_trunc('month', 'date_day') }}               as month_start,
    dayofweek(date_day)                                     as day_of_week,
    case when dayofweek(date_day) in (0, 6) then 1 else 0 end as is_weekend

from days
