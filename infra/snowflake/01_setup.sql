-- One-time account setup: warehouse, database, schemas, and a least-privilege
-- role for dbt / the pipeline. Run as ACCOUNTADMIN (or SYSADMIN + SECURITYADMIN).

use role sysadmin;

create warehouse if not exists transform_wh
    warehouse_size = 'XSMALL'
    auto_suspend = 60            -- seconds; keeps the trial/credit cost negligible
    auto_resume = true
    initially_suspended = true;

create database if not exists apple_pricing;

create schema if not exists apple_pricing.raw;           -- COPY INTO target
create schema if not exists apple_pricing.reference;     -- dbt seeds
create schema if not exists apple_pricing.staging;       -- dbt views
create schema if not exists apple_pricing.intermediate;  -- dbt views
create schema if not exists apple_pricing.marts;         -- dbt tables (BI layer)
create schema if not exists apple_pricing.ml;            -- forecast outputs from Python

create table if not exists apple_pricing.raw.apple_prices (
    observation_date   date,
    platform           varchar,
    product_category   varchar,
    model_name         varchar,
    condition          varchar,
    launch_price_usd   number(10, 2),
    launch_price_inr   number(12, 2),
    current_price_usd  float,
    current_price_inr  float,
    discount_pct       float,
    sale_event         varchar,
    stock_status       varchar,
    rating             float,
    reviews_count      number,
    _source_file       varchar,
    _ingested_at       timestamp_ntz
);

use role securityadmin;

create role if not exists transformer;
grant role transformer to role sysadmin;

grant usage on warehouse transform_wh to role transformer;
grant usage, create schema on database apple_pricing to role transformer;
grant all privileges on all schemas in database apple_pricing to role transformer;
grant all privileges on future schemas in database apple_pricing to role transformer;
grant all privileges on all tables in database apple_pricing to role transformer;
grant all privileges on future tables in database apple_pricing to role transformer;
grant all privileges on future views in database apple_pricing to role transformer;

-- Read-only role for Power BI / analysts.
create role if not exists reporter;
grant usage on warehouse transform_wh to role reporter;
grant usage on database apple_pricing to role reporter;
grant usage on schema apple_pricing.marts to role reporter;
grant select on all tables in schema apple_pricing.marts to role reporter;
grant select on future tables in schema apple_pricing.marts to role reporter;

-- Assign to your user, e.g.:
-- grant role transformer to user <your_user>;
-- grant role reporter to user <powerbi_service_user>;
