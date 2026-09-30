"""Load (cloud path): COPY the S3 Parquet partitions into Snowflake RAW.APPLE_PRICES.

Assumes infra/snowflake/01_setup.sql and 02_s3_integration.sql have been run once.
The statement is idempotent: Snowflake's load metadata skips files already loaded.
"""

from pathlib import Path

from apple_pricing.config import PROJECT_DIR

LOAD_SQL_PATH = PROJECT_DIR / "infra" / "snowflake" / "03_load_raw.sql"


def _statements(path: Path) -> list[str]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if not line.strip().startswith("--")]
    return [statement.strip() for statement in "\n".join(lines).split(";") if statement.strip()]


def load(warehouse) -> None:
    for statement in _statements(LOAD_SQL_PATH):
        warehouse.execute(statement)
    row_count = warehouse.query("select count(*) as n from raw.apple_prices")["n"].iloc[0]
    print(f"RAW.APPLE_PRICES now holds {row_count:,} rows")
