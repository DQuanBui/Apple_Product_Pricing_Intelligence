"""Thin warehouse abstraction so the same Python code runs against DuckDB (dev)
or Snowflake (prod). Select with `--target` on the pipeline or WAREHOUSE_TARGET.
"""

import os

import pandas as pd

from apple_pricing.config import DUCKDB_PATH


class DuckDBWarehouse:
    target = "dev"

    def __init__(self, path=DUCKDB_PATH, read_only: bool = False):
        import duckdb

        self.connection = duckdb.connect(str(path), read_only=read_only)

    def query(self, sql: str) -> pd.DataFrame:
        return self.connection.sql(sql).df()

    def write(self, data: pd.DataFrame, schema: str, table: str) -> None:
        self.connection.execute(f"create schema if not exists {schema}")
        self.connection.register("_frame", data)
        self.connection.execute(f"create or replace table {schema}.{table} as select * from _frame")
        self.connection.unregister("_frame")

    def close(self) -> None:
        self.connection.close()


class SnowflakeWarehouse:
    target = "prod"

    def __init__(self):
        import snowflake.connector

        self.connection = snowflake.connector.connect(
            account=os.environ["SNOWFLAKE_ACCOUNT"],
            user=os.environ["SNOWFLAKE_USER"],
            password=os.environ.get("SNOWFLAKE_PASSWORD"),
            role=os.getenv("SNOWFLAKE_ROLE", "TRANSFORMER"),
            warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "TRANSFORM_WH"),
            database=os.getenv("SNOWFLAKE_DATABASE", "APPLE_PRICING"),
        )

    def query(self, sql: str) -> pd.DataFrame:
        with self.connection.cursor() as cursor:
            cursor.execute(sql)
            data = cursor.fetch_pandas_all()
        # Snowflake returns upper-case identifiers; the Python code uses lower case.
        data.columns = [column.lower() for column in data.columns]
        return data

    def execute(self, sql: str) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(sql)

    def write(self, data: pd.DataFrame, schema: str, table: str) -> None:
        from snowflake.connector.pandas_tools import write_pandas

        self.execute(f"create schema if not exists {schema.upper()}")
        frame = data.copy()
        frame.columns = [column.upper() for column in frame.columns]
        write_pandas(
            self.connection,
            frame,
            table_name=table.upper(),
            schema=schema.upper(),
            auto_create_table=True,
            overwrite=True,
            use_logical_type=True,
        )

    def close(self) -> None:
        self.connection.close()


def get_warehouse(target: str | None = None, read_only: bool = False):
    target = target or os.getenv("WAREHOUSE_TARGET", "dev")
    if target == "dev":
        return DuckDBWarehouse(read_only=read_only)
    if target == "prod":
        return SnowflakeWarehouse()
    raise ValueError(f"Unknown warehouse target: {target!r} (expected 'dev' or 'prod')")
