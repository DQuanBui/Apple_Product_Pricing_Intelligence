"""Read-only, in-memory SQL sandbox over the exported marts.

Used by the AI analyst: the model can only run a single SELECT against
in-memory copies of the marts. External file/network access is disabled and
the configuration is locked before any model-generated SQL runs.
"""

import re
from pathlib import Path

import duckdb
import pandas as pd

TABLE_DESCRIPTIONS = {
    "dim_product": "One row per Apple model: category, product line, tier, chip, storage, release date, MSRP, successor.",
    "fct_daily_market_prices": (
        "Series-day fact (platform x model x condition x date): median/min/max price, listing count, "
        "price_index (price / MSRP x 100), discount_pct vs MSRP, sale_event, months_since_release, "
        "baseline_price_30obs_usd (normal non-event price) and savings_vs_baseline_pct."
    ),
    "mart_platform_price_gap": "Matched Amazon vs Flipkart prices for the same model, condition and day; gap_pct = (Amazon - Flipkart) / Flipkart x 100.",
    "mart_sale_event_impact": "Per sale event x category: headline discount vs MSRP and real savings vs the normal price.",
    "mart_depreciation_curve": "Median price index by category, condition and months since release.",
    "mart_successor_launch_impact": "Price index 60 days before vs after each model's successor was released.",
    "mart_model_scorecard": "One row per model: current price, retention, depreciation per month, volatility, platform and refurbished metrics.",
    "mart_deal_scores": "Latest buy-now / wait recommendation per series with 7/30-day forecasts, P10-P90 range and deal_score (0-100).",
    "mart_forecast_backtest": "Out-of-sample forecast test predictions (7 and 30 day) with actuals and baseline errors.",
}

MAX_ROWS = 200

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|merge|drop|create|alter|attach|detach|copy|export|import|install|load|"
    r"pragma|set|reset|call|checkpoint|vacuum|use|begin|commit|rollback|grant|revoke|"
    r"read_csv\w*|read_parquet|read_json\w*|read_text|read_blob|glob|parquet_scan|sniff_csv|getenv)\b",
    re.IGNORECASE,
)


class UnsafeQueryError(ValueError):
    pass


def validate_query(sql: str) -> str:
    """Return a cleaned single SELECT statement or raise UnsafeQueryError."""
    cleaned = re.sub(r"--[^\n]*", " ", sql)
    cleaned = re.sub(r"/\*.*?\*/", " ", cleaned, flags=re.DOTALL).strip().rstrip(";").strip()

    if not cleaned:
        raise UnsafeQueryError("Empty query.")
    if ";" in cleaned:
        raise UnsafeQueryError("Only a single statement is allowed.")
    if not re.match(r"^(select|with)\b", cleaned, re.IGNORECASE):
        raise UnsafeQueryError("Only SELECT queries are allowed.")

    # Ignore keywords that appear inside string literals, e.g. WHERE sale_event = 'Big Billion Days'.
    without_strings = re.sub(r"'(?:[^']|'')*'", "''", cleaned)
    match = _FORBIDDEN.search(without_strings)
    if match:
        raise UnsafeQueryError(f"Keyword or function not allowed: {match.group(0)}")

    return cleaned


def build_connection(marts_dir: Path) -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(":memory:")
    for table in TABLE_DESCRIPTIONS:
        path = marts_dir / f"{table}.parquet"
        if path.exists():
            connection.execute(f"create table {table} as select * from read_parquet('{path.as_posix()}')")

    connection.execute("set enable_external_access = false")
    connection.execute("set lock_configuration = true")
    return connection


def run_query(connection: duckdb.DuckDBPyConnection, sql: str) -> pd.DataFrame:
    query = validate_query(sql)
    cursor = connection.cursor()
    try:
        return cursor.execute(f"select * from ({query}) as result limit {MAX_ROWS}").df()
    finally:
        cursor.close()


def describe_schema(connection: duckdb.DuckDBPyConnection) -> str:
    lines = []
    tables = {row[0] for row in connection.execute("show tables").fetchall()}
    for table, description in TABLE_DESCRIPTIONS.items():
        if table not in tables:
            continue
        columns = connection.execute(f"describe {table}").fetchall()
        column_list = ", ".join(f"{name} {dtype}" for name, dtype, *_ in columns)
        lines.append(f"- {table}: {description}\n  columns: {column_list}")
    return "\n".join(lines)
