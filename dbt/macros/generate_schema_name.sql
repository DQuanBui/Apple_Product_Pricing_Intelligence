{#
    Use the custom schema name as-is (staging, intermediate, marts, reference)
    instead of dbt's default "<target_schema>_<custom_schema>". This gives the
    same schema names in DuckDB and Snowflake, which keeps Power BI and the
    Streamlit exports target-agnostic.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
