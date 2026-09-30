"""Load (cloud path): upload the Parquet lake partitions to S3.

Snowflake reads them through an external stage (see infra/snowflake/).

Usage:
    python -m apple_pricing.ingest.upload_to_s3 --bucket my-bucket
    python -m apple_pricing.ingest.upload_to_s3 --bucket my-bucket --dry-run

Credentials come from the standard AWS chain (env vars, ~/.aws/credentials, SSO).
"""

import argparse

from apple_pricing.config import AWS_REGION, S3_BUCKET, S3_PREFIX
from apple_pricing.ingest.extract import LAKE_TABLE_DIR, run as extract


def upload(bucket: str, prefix: str = S3_PREFIX, dry_run: bool = False) -> list[str]:
    files = sorted(LAKE_TABLE_DIR.rglob("*.parquet"))
    if not files:
        files = extract()

    keys = [
        f"{prefix.rstrip('/')}/{path.relative_to(LAKE_TABLE_DIR).as_posix()}"
        for path in files
    ]

    if dry_run:
        for key in keys:
            print(f"[dry-run] s3://{bucket}/{key}")
        return keys

    import boto3  # imported lazily so the local path does not need AWS libraries

    s3 = boto3.client("s3", region_name=AWS_REGION)
    for path, key in zip(files, keys):
        s3.upload_file(str(path), bucket, key)
        print(f"Uploaded s3://{bucket}/{key}")

    return keys


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bucket", default=S3_BUCKET, help="Target S3 bucket (or set S3_BUCKET)")
    parser.add_argument("--prefix", default=S3_PREFIX)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.bucket:
        parser.error("--bucket is required (or set the S3_BUCKET environment variable)")

    upload(args.bucket, args.prefix, args.dry_run)


if __name__ == "__main__":
    main()
