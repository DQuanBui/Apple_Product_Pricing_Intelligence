"""End-to-end pipeline.

    python -m apple_pricing.pipeline                      # local: DuckDB, no credentials
    python -m apple_pricing.pipeline --target prod        # S3 + Snowflake
    python -m apple_pricing.pipeline --skip-train         # reuse the last forecasts

Steps:
  1. extract   CSV -> year-partitioned Parquet (same layout as S3)
  2. load      dev: Parquet -> DuckDB raw.apple_prices
               prod: Parquet -> S3 -> COPY INTO Snowflake RAW.APPLE_PRICES
  3. dbt       build + test everything except the `ml`-tagged models
  4. train     CatBoost 7/30-day quantile forecasts -> ml.forecast_* tables
  5. dbt       build + test the `ml`-tagged marts (deal scores, backtest)
  6. export    marts -> data/marts/*.parquet for the Streamlit app
"""

import argparse
import os
import time

import pandas as pd

from apple_pricing.config import DBT_DIR, DUCKDB_PATH, S3_BUCKET


def run_dbt(args: list[str], target: str) -> pd.DataFrame:
    from dbt.cli.main import dbtRunner

    os.environ.setdefault("DUCKDB_PATH", str(DUCKDB_PATH))
    command = [*args, "--project-dir", str(DBT_DIR), "--profiles-dir", str(DBT_DIR), "--target", target]
    result = dbtRunner().invoke(command)

    rows = []
    for node_result in getattr(result.result, "results", None) or []:
        node = node_result.node
        rows.append(
            {
                "unique_id": node.unique_id,
                "name": node.name,
                "resource_type": str(node.resource_type),
                "status": str(node_result.status),
                "failures": node_result.failures or 0,
                "execution_time_s": round(node_result.execution_time or 0.0, 3),
            }
        )

    if not result.success:
        raise RuntimeError(f"dbt {' '.join(args)} failed: {result.exception or 'see log output'}")
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", choices=["dev", "prod"], default="dev")
    parser.add_argument("--skip-train", action="store_true", help="Reuse existing ml.forecast_* tables")
    parser.add_argument("--bucket", default=S3_BUCKET, help="S3 bucket for --target prod")
    args = parser.parse_args()

    from apple_pricing import export
    from apple_pricing.ingest import extract
    from apple_pricing.warehouse import get_warehouse

    started = time.time()

    print("\n[1/6] Extract")
    extract.run()

    print("\n[2/6] Load")
    if args.target == "dev":
        from apple_pricing.ingest import load_duckdb

        load_duckdb.load()
    else:
        from apple_pricing.ingest import load_snowflake, upload_to_s3

        if not args.bucket:
            parser.error("--bucket (or S3_BUCKET) is required for --target prod")
        upload_to_s3.upload(args.bucket)
        warehouse = get_warehouse("prod")
        try:
            load_snowflake.load(warehouse)
        finally:
            warehouse.close()

    print("\n[3/6] dbt build (core + analytics)")
    core_results = run_dbt(["build", "--exclude", "tag:ml"], args.target)

    if not args.skip_train:
        print("\n[4/6] Train forecasts")
        from apple_pricing.forecasting import train

        warehouse = get_warehouse(args.target)
        try:
            train.run(warehouse)
        finally:
            warehouse.close()
    else:
        print("\n[4/6] Train forecasts (skipped)")

    print("\n[5/6] dbt build (ml marts)")
    ml_results = run_dbt(["build", "--select", "tag:ml"], args.target)

    print("\n[6/6] Export marts")
    # Same connection settings as dbt-duckdb, which keeps its handle open in-process.
    warehouse = get_warehouse(args.target)
    try:
        export.run(warehouse, pd.concat([core_results, ml_results], ignore_index=True))
    finally:
        warehouse.close()

    print(f"\nPipeline finished in {time.time() - started:,.0f}s")


if __name__ == "__main__":
    main()
