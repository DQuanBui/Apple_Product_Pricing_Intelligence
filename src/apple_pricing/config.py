"""Central paths and settings. Everything is overridable with environment variables."""

import os
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]

RAW_CSV_PATH = Path(
    os.getenv(
        "RAW_CSV_PATH",
        PROJECT_DIR / "data" / "raw" / "apple_products_pricing_2020_2026.csv",
    )
)

# Local "data lake" that mirrors the S3 layout, so the local and cloud paths match.
LAKE_DIR = PROJECT_DIR / "data" / "lake"

# Local warehouse (DuckDB) used by the `dev` dbt target.
DUCKDB_PATH = Path(
    os.getenv("DUCKDB_PATH", PROJECT_DIR / "warehouse" / "apple_pricing.duckdb")
)

DBT_DIR = PROJECT_DIR / "dbt"

# Small, committed exports that the Streamlit app and Power BI (file mode) read.
MARTS_EXPORT_DIR = PROJECT_DIR / "data" / "marts"

ARTIFACTS_DIR = PROJECT_DIR / "artifacts"
MODEL_DIR = ARTIFACTS_DIR / "models"
FIGURES_DIR = PROJECT_DIR / "reports" / "figures"

# S3 / Snowflake settings (only needed for the cloud path).
S3_BUCKET = os.getenv("S3_BUCKET", "")
S3_PREFIX = os.getenv("S3_PREFIX", "raw/apple_pricing")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

RANDOM_STATE = 42
FORECAST_HORIZONS = (7, 30)

# Canonical raw column names. The CSV header is mapped onto these by position,
# so the same names are used in DuckDB, Parquet, and the Snowflake RAW table.
RAW_COLUMNS = [
    "observation_date",
    "platform",
    "product_category",
    "model_name",
    "condition",
    "launch_price_usd",
    "launch_price_inr",
    "current_price_usd",
    "current_price_inr",
    "discount_pct",
    "sale_event",
    "stock_status",
    "rating",
    "reviews_count",
]
