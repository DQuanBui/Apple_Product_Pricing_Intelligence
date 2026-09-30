"""Load (local path): Parquet lake -> DuckDB `raw.apple_prices`.

This is the local equivalent of `infra/snowflake/03_load_raw.sql`
(COPY INTO RAW.APPLE_PRICES from the S3 stage).
"""

import duckdb

from apple_pricing.config import DUCKDB_PATH
from apple_pricing.ingest.extract import LAKE_TABLE_DIR


def load(duckdb_path=DUCKDB_PATH) -> int:
    duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    parquet_glob = (LAKE_TABLE_DIR / "*" / "*.parquet").as_posix()

    with duckdb.connect(str(duckdb_path)) as connection:
        connection.execute("create schema if not exists raw")
        connection.execute(
            f"""
            create or replace table raw.apple_prices as
            select * exclude (year)
            from read_parquet('{parquet_glob}', hive_partitioning = true)
            """
        )
        row_count = connection.execute("select count(*) from raw.apple_prices").fetchone()[0]

    print(f"Loaded {row_count:,} rows into raw.apple_prices ({duckdb_path})")
    return row_count


if __name__ == "__main__":
    load()
