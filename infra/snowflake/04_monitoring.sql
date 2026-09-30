-- Operational checks for the Snowflake side of the pipeline.

-- Load history for the raw table (last 7 days).
select file_name, status, row_count, first_error_message, last_load_time
from table(information_schema.copy_history(
    table_name => 'APPLE_PRICING.RAW.APPLE_PRICES',
    start_time => dateadd(day, -7, current_timestamp())
))
order by last_load_time desc;

-- Credit usage of the transform warehouse (last 30 days).
select date_trunc('day', start_time) as usage_day, sum(credits_used) as credits
from snowflake.account_usage.warehouse_metering_history
where warehouse_name = 'TRANSFORM_WH'
  and start_time >= dateadd(day, -30, current_timestamp())
group by 1
order by 1;

-- Row counts across the BI layer.
select table_schema, table_name, row_count, bytes
from apple_pricing.information_schema.tables
where table_schema in ('MARTS', 'ML')
order by table_schema, table_name;
