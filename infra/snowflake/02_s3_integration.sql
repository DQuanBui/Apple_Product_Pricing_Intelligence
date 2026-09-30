-- One-time: connect Snowflake to the S3 bucket with a storage integration
-- (IAM role, no long-lived AWS keys stored in Snowflake).
--
-- 1. Create the IAM role in AWS with infra/aws/s3_read_policy.json attached.
-- 2. Run this script, replacing <bucket> and <aws_account_id>.
-- 3. Run `desc integration s3_apple_pricing`, copy STORAGE_AWS_IAM_USER_ARN and
--    STORAGE_AWS_EXTERNAL_ID into infra/aws/trust_policy.json, and apply it as
--    the role's trust policy.

use role accountadmin;

create storage integration if not exists s3_apple_pricing
    type = external_stage
    storage_provider = 's3'
    enabled = true
    storage_aws_role_arn = 'arn:aws:iam::<aws_account_id>:role/snowflake-apple-pricing-read'
    storage_allowed_locations = ('s3://<bucket>/raw/apple_pricing/');

grant usage on integration s3_apple_pricing to role transformer;

desc integration s3_apple_pricing;

use role transformer;
use schema apple_pricing.raw;

create file format if not exists parquet_format
    type = parquet
    use_logical_type = true;

create stage if not exists apple_pricing_stage
    storage_integration = s3_apple_pricing
    url = 's3://<bucket>/raw/apple_pricing/'
    file_format = parquet_format;

-- Should list year=2020/ ... year=2026/ partitions after the upload step.
list @apple_pricing_stage;
