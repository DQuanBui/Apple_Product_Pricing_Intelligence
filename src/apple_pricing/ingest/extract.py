"""Extract: raw CSV -> year-partitioned Parquet files in the local lake.

The lake layout (`raw/apple_pricing/year=YYYY/apple_prices_YYYY.parquet`) is
identical to the S3 layout, so `upload_to_s3.py` is a straight copy and the
Snowflake stage / DuckDB loader read the same files.
"""

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from apple_pricing.config import LAKE_DIR, RAW_COLUMNS, RAW_CSV_PATH

LAKE_TABLE_DIR = LAKE_DIR / "raw" / "apple_pricing"


def read_raw_csv(path: Path = RAW_CSV_PATH) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Raw dataset not found: {path}")

    # keep_default_na=False keeps the literal "None" sale-event label as text;
    # empty strings are treated as missing.
    data = pd.read_csv(path, keep_default_na=False, na_values=[""])

    if len(data.columns) != len(RAW_COLUMNS):
        raise ValueError(
            f"Expected {len(RAW_COLUMNS)} columns, found {len(data.columns)}: "
            f"{data.columns.tolist()}"
        )

    data.columns = RAW_COLUMNS
    data["observation_date"] = pd.to_datetime(data["observation_date"]).dt.date
    data["_source_file"] = path.name
    data["_ingested_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
    return data


def write_partitioned_parquet(data: pd.DataFrame, lake_dir: Path = LAKE_TABLE_DIR) -> list[Path]:
    years = pd.to_datetime(data["observation_date"]).dt.year
    written = []

    for year, partition in data.groupby(years):
        partition_dir = lake_dir / f"year={year}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        file_path = partition_dir / f"apple_prices_{year}.parquet"
        partition.to_parquet(file_path, index=False)
        written.append(file_path)

    return written


def run() -> list[Path]:
    data = read_raw_csv()
    files = write_partitioned_parquet(data)
    print(f"Extracted {len(data):,} rows into {len(files)} Parquet partitions under {LAKE_TABLE_DIR}")
    return files


if __name__ == "__main__":
    run()
