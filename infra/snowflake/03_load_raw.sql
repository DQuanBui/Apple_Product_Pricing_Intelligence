-- Incremental load from S3. Snowflake keeps 64 days of load metadata per
-- table, so files that were already loaded are skipped automatically.
-- Executed by apple_pricing.ingest.load_snowflake (pipeline --target prod).

use schema apple_pricing.raw;

copy into raw.apple_prices
from @raw.apple_pricing_stage
file_format = (format_name = raw.parquet_format)
match_by_column_name = case_insensitive
pattern = '.*year=[0-9]{4}/.*[.]parquet'
on_error = abort_statement;
