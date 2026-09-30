import pandas as pd
import pytest

from dashboard.sql_sandbox import UnsafeQueryError, build_connection, run_query, validate_query


@pytest.mark.parametrize(
    "sql",
    [
        "select * from dim_product",
        "SELECT 1;",
        "with x as (select 1 as a) select a from x",
        "select * from mart_sale_event_impact where sale_event = 'Black Friday'",
        # Forbidden words inside string literals are fine.
        "select 'drop table' as label",
    ],
)
def test_allows_read_only_selects(sql):
    assert validate_query(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "drop table dim_product",
        "select 1; drop table dim_product",
        "insert into dim_product values (1)",
        "select * from read_csv('secrets.csv')",
        "select * from read_parquet('/etc/passwd')",
        "attach 'other.db'",
        "copy dim_product to 'out.csv'",
        "set enable_external_access = true",
        "select getenv('ANTHROPIC_API_KEY')",
        "",
        "-- only a comment",
    ],
)
def test_rejects_unsafe_sql(sql):
    with pytest.raises(UnsafeQueryError):
        validate_query(sql)


def test_sandbox_blocks_file_access_and_caps_rows(tmp_path):
    pd.DataFrame({"model_name": [f"m{i}" for i in range(500)]}).to_parquet(tmp_path / "dim_product.parquet")
    connection = build_connection(tmp_path)

    assert len(run_query(connection, "select * from dim_product")) == 200

    # Even if the regex guard were bypassed, DuckDB itself refuses file access.
    with pytest.raises(Exception):
        connection.execute(f"select * from read_parquet('{(tmp_path / 'dim_product.parquet').as_posix()}')")
    with pytest.raises(Exception):
        connection.execute("set enable_external_access = true")
