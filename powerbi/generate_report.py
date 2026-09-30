"""Generate the Power BI project (PBIP) for the Apple pricing report.

Writes a Power BI Project that Power BI Desktop opens directly:
  powerbi/ApplePricing.pbip
  powerbi/ApplePricing.SemanticModel/   TMDL: tables (from the Parquet exports), relationships, DAX measures
  powerbi/ApplePricing.Report/          PBIR: six report pages, visuals, custom theme

The model imports data/marts/*.parquet through the `DataFolder` parameter. To
point the same model at Snowflake instead, swap each partition's source for
Snowflake.Databases(...) on APPLE_PRICING.MARTS.

    python powerbi/generate_report.py [--data-folder <absolute path to data/marts>]
"""

import argparse
import json
import shutil
import uuid
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent
PROJECT_DIR = ROOT.parent
NAME = "ApplePricing"
MODEL_DIR = ROOT / f"{NAME}.SemanticModel"
REPORT_DIR = ROOT / f"{NAME}.Report"

SCHEMA = "https://developer.microsoft.com/json-schemas/fabric"
PAGE_W, PAGE_H = 1280, 720

INK, INK_2, MUTED, RULE = "#0B0B0B", "#52514E", "#898781", "#E1E0D9"
CATEGORY_COLORS = {"iPhone": "#2A78D6", "iPad": "#EB6834", "Mac": "#1BAF7A", "Watch": "#EDA100"}
SERIES = ["#2A78D6", "#EB6834", "#1BAF7A"]


def tag(*parts: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "apple-pricing/" + "/".join(parts)))


# --------------------------------------------------------------------------- semantic model

PARQUET_TABLES = [
    "dim_product",
    "dim_date",
    "fct_daily_market_prices",
    "mart_platform_price_gap",
    "mart_sale_event_impact",
    "mart_depreciation_curve",
    "mart_successor_launch_impact",
    "mart_model_scorecard",
    "mart_deal_scores",
    "mart_forecast_backtest",
]

ARROW_TO_TMDL = {
    "large_string": "string",
    "string": "string",
    "int32": "int64",
    "int64": "int64",
    "float": "double",
    "double": "double",
    "timestamp[us]": "dateTime",
    "timestamp[ns]": "dateTime",
    "bool": "boolean",
}

# Measures per home table: (name, DAX, format string, display folder)
MEASURES = {
    "fct_daily_market_prices": [
        ("Series-Days", "COUNTROWS ( fct_daily_market_prices )", "#,0", "Market"),
        ("Listings", "SUM ( fct_daily_market_prices[listing_count] )", "#,0", "Market"),
        ("Models Tracked", "DISTINCTCOUNT ( fct_daily_market_prices[model_name] )", "0", "Market"),
        ("Avg Price", "AVERAGE ( fct_daily_market_prices[median_price_usd] )", "\\$#,0", "Price"),
        (
            "Price Index",
            "DIVIDE ( SUM ( fct_daily_market_prices[median_price_usd] ), SUM ( fct_daily_market_prices[launch_price_usd] ) ) * 100",
            "0.0",
            "Price",
        ),
        ("Discount vs Launch %", "DIVIDE ( 100 - [Price Index], 100 )", "0.0%", "Price"),
        (
            "Savings vs Normal %",
            "AVERAGEX ( FILTER ( fct_daily_market_prices, NOT ISBLANK ( fct_daily_market_prices[baseline_price_30obs_usd] ) ), fct_daily_market_prices[savings_vs_baseline_pct] ) / 100",
            "0.0%",
            "Sale events",
        ),
        (
            "Event Savings vs Normal %",
            "CALCULATE ( [Savings vs Normal %], fct_daily_market_prices[is_sale_event] = 1 )",
            "0.0%",
            "Sale events",
        ),
        ("In-Stock Share", "AVERAGE ( fct_daily_market_prices[in_stock_share] )", "0.0%", "Market"),
    ],
    "mart_depreciation_curve": [
        (
            "Price Index New",
            "CALCULATE ( AVERAGE ( mart_depreciation_curve[median_price_index] ), mart_depreciation_curve[condition] = \"New\", mart_depreciation_curve[models] >= 2, mart_depreciation_curve[series_days] >= 60 )",
            "0.0",
            "Life cycle",
        ),
        (
            "Price Index Refurbished",
            "CALCULATE ( AVERAGE ( mart_depreciation_curve[median_price_index] ), mart_depreciation_curve[condition] = \"Refurbished\", mart_depreciation_curve[models] >= 2, mart_depreciation_curve[series_days] >= 60 )",
            "0.0",
            "Life cycle",
        ),
    ],
    "mart_successor_launch_impact": [
        ("Successor Price Change %", "AVERAGE ( mart_successor_launch_impact[price_change_pct] ) / 100", "0.0%", "Life cycle"),
        ("Models with Successor", "COUNTROWS ( mart_successor_launch_impact )", "0", "Life cycle"),
    ],
    "mart_sale_event_impact": [
        (
            "Headline Discount %",
            "DIVIDE ( SUMX ( mart_sale_event_impact, mart_sale_event_impact[avg_discount_vs_msrp_pct] * mart_sale_event_impact[series_days] ), SUM ( mart_sale_event_impact[series_days] ) ) / 100",
            "0.0%",
            "Sale events",
        ),
        (
            "Real Saving vs Normal %",
            "DIVIDE ( SUMX ( mart_sale_event_impact, mart_sale_event_impact[avg_savings_vs_baseline_pct] * mart_sale_event_impact[series_days] ), SUM ( mart_sale_event_impact[series_days] ) ) / 100",
            "0.0%",
            "Sale events",
        ),
        (
            "Event Days Saving 5%+",
            "DIVIDE ( SUMX ( mart_sale_event_impact, mart_sale_event_impact[pct_days_saving_5pct_plus] * mart_sale_event_impact[series_days] ), SUM ( mart_sale_event_impact[series_days] ) ) / 100",
            "0.0%",
            "Sale events",
        ),
        (
            "Avg Saving per Day (USD)",
            "DIVIDE ( SUMX ( mart_sale_event_impact, mart_sale_event_impact[avg_savings_usd] * mart_sale_event_impact[series_days] ), SUM ( mart_sale_event_impact[series_days] ) )",
            "\\$#,0",
            "Sale events",
        ),
        (
            "Event Headline Discount %",
            "CALCULATE ( [Headline Discount %], mart_sale_event_impact[sale_event] <> \"No Event\" )",
            "0.0%",
            "Sale events",
        ),
        (
            "Event Real Saving %",
            "CALCULATE ( [Real Saving vs Normal %], mart_sale_event_impact[sale_event] <> \"No Event\" )",
            "0.0%",
            "Sale events",
        ),
        (
            "Event Days Saving 5%+ (events)",
            "CALCULATE ( [Event Days Saving 5%+], mart_sale_event_impact[sale_event] <> \"No Event\" )",
            "0.0%",
            "Sale events",
        ),
        (
            "Event Series-Days",
            "CALCULATE ( SUM ( mart_sale_event_impact[series_days] ), mart_sale_event_impact[sale_event] <> \"No Event\" )",
            "#,0",
            "Sale events",
        ),
    ],
    "mart_platform_price_gap": [
        ("Matched Days", "COUNTROWS ( mart_platform_price_gap )", "#,0", "Marketplaces"),
        (
            "Amazon Cheaper %",
            "DIVIDE ( CALCULATE ( COUNTROWS ( mart_platform_price_gap ), mart_platform_price_gap[cheaper_platform] = \"Amazon\" ), COUNTROWS ( mart_platform_price_gap ) )",
            "0.0%",
            "Marketplaces",
        ),
        ("Median Gap %", "MEDIAN ( mart_platform_price_gap[gap_pct] ) / 100", "0.00%", "Marketplaces"),
        (
            "Avg Absolute Gap %",
            "AVERAGEX ( mart_platform_price_gap, ABS ( mart_platform_price_gap[gap_pct] ) ) / 100",
            "0.0%",
            "Marketplaces",
        ),
    ],
    "mart_model_scorecard": [
        ("Launch Price", "AVERAGE ( mart_model_scorecard[msrp_usd] )", "\\$#,0", "Scorecard"),
        ("Current Price", "AVERAGE ( mart_model_scorecard[current_price_usd] )", "\\$#,0", "Scorecard"),
        ("Current Price Index", "AVERAGE ( mart_model_scorecard[current_price_index] )", "0.0", "Scorecard"),
        ("Refurbished Discount %", "AVERAGE ( mart_model_scorecard[refurbished_discount_pct] ) / 100", "0.0%", "Scorecard"),
        ("Monthly Depreciation (pts)", "AVERAGE ( mart_model_scorecard[avg_monthly_depreciation_pts] )", "0.00", "Scorecard"),
    ],
    "mart_forecast_backtest": [
        ("Forecast MAE", "AVERAGE ( mart_forecast_backtest[model_abs_error_usd] )", "\\$#,0.00", "Forecast"),
        ("Naive MAE", "AVERAGE ( mart_forecast_backtest[naive_abs_error_usd] )", "\\$#,0.00", "Forecast"),
        ("30-Day Avg MAE", "AVERAGE ( mart_forecast_backtest[trailing_abs_error_usd] )", "\\$#,0.00", "Forecast"),
        ("Improvement vs Naive %", "DIVIDE ( [Naive MAE] - [Forecast MAE], [Naive MAE] )", "0.0%", "Forecast"),
        ("Improvement vs 30-Day Avg %", "DIVIDE ( [30-Day Avg MAE] - [Forecast MAE], [30-Day Avg MAE] )", "0.0%", "Forecast"),
        ("Interval Coverage %", "AVERAGE ( mart_forecast_backtest[is_within_interval] )", "0.0%", "Forecast"),
        ("Forecast MAE 7d", "CALCULATE ( [Forecast MAE], mart_forecast_backtest[horizon_days] = 7 )", "\\$#,0.00", "Forecast"),
        ("Forecast MAE 30d", "CALCULATE ( [Forecast MAE], mart_forecast_backtest[horizon_days] = 30 )", "\\$#,0.00", "Forecast"),
        ("Naive MAE 7d", "CALCULATE ( [Naive MAE], mart_forecast_backtest[horizon_days] = 7 )", "\\$#,0.00", "Forecast"),
        ("30-Day Avg MAE 7d", "CALCULATE ( [30-Day Avg MAE], mart_forecast_backtest[horizon_days] = 7 )", "\\$#,0.00", "Forecast"),
        ("Improvement vs Naive 7d %", "CALCULATE ( [Improvement vs Naive %], mart_forecast_backtest[horizon_days] = 7 )", "0.0%", "Forecast"),
        ("Improvement vs 30-Day Avg 7d %", "CALCULATE ( [Improvement vs 30-Day Avg %], mart_forecast_backtest[horizon_days] = 7 )", "0.0%", "Forecast"),
        ("Improvement vs 30-Day Avg 30d %", "CALCULATE ( [Improvement vs 30-Day Avg %], mart_forecast_backtest[horizon_days] = 30 )", "0.0%", "Forecast"),
        ("Interval Coverage 7d %", "CALCULATE ( [Interval Coverage %], mart_forecast_backtest[horizon_days] = 7 )", "0.0%", "Forecast"),
    ],
    "mart_deal_scores": [
        ("Series Scored", "COUNTROWS ( mart_deal_scores )", "0", "Deals"),
        ("Buy Now Series", "CALCULATE ( COUNTROWS ( mart_deal_scores ), mart_deal_scores[recommendation] = \"Buy now\" )", "0", "Deals"),
        ("Wait Series", "CALCULATE ( COUNTROWS ( mart_deal_scores ), mart_deal_scores[recommendation] = \"Wait\" )", "0", "Deals"),
        ("Avg Deal Score", "AVERAGE ( mart_deal_scores[deal_score] )", "0.0", "Deals"),
    ],
}

CALCULATED_COLUMNS = {
    "mart_platform_price_gap": [
        (
            "Gap Bucket %",
            "MAX ( -10, MIN ( 10, ROUND ( mart_platform_price_gap[gap_pct], 0 ) ) )",
            "double",
            "0",
        )
    ]
}

# many-side table.column -> one-side table.column
RELATIONSHIPS = [
    ("dim_product", "product_category", "dim_category", "product_category"),
    ("fct_daily_market_prices", "model_name", "dim_product", "model_name"),
    ("fct_daily_market_prices", "price_date", "dim_date", "date_day"),
    ("mart_platform_price_gap", "model_name", "dim_product", "model_name"),
    ("mart_platform_price_gap", "price_date", "dim_date", "date_day"),
    ("mart_successor_launch_impact", "model_name", "dim_product", "model_name"),
    ("mart_model_scorecard", "model_name", "dim_product", "model_name"),
    ("mart_deal_scores", "model_name", "dim_product", "model_name"),
    ("mart_forecast_backtest", "model_name", "dim_product", "model_name"),
    ("mart_sale_event_impact", "product_category", "dim_category", "product_category"),
    ("mart_depreciation_curve", "product_category", "dim_category", "product_category"),
]


def quote(name: str) -> str:
    return name if name.replace("_", "").isalnum() else "'" + name.replace("'", "''") + "'"


def m_source(expression_lines: list[str]) -> str:
    return "\n".join("\t\t\t\t" + line for line in expression_lines)


def table_tmdl(table: str, columns: list[tuple[str, str]], partition_lines: list[str]) -> str:
    lines = [f"table {table}", f"\tlineageTag: {tag(table)}", ""]

    for name, dax, fmt, folder in MEASURES.get(table, []):
        lines += [
            f"\tmeasure {quote(name)} = {dax}",
            f"\t\tformatString: {fmt}",
            f"\t\tdisplayFolder: {folder}",
            f"\t\tlineageTag: {tag(table, 'measure', name)}",
            "",
        ]

    for name, data_type in columns:
        lines += [f"\tcolumn {quote(name)}", f"\t\tdataType: {data_type}"]
        if data_type == "dateTime":
            lines.append("\t\tformatString: yyyy-mm-dd")
        lines += [
            f"\t\tlineageTag: {tag(table, 'column', name)}",
            "\t\tsummarizeBy: none",
            f"\t\tsourceColumn: {name}",
            "",
            "\t\tannotation SummarizationSetBy = User",
            "",
        ]

    for name, dax, data_type, fmt in CALCULATED_COLUMNS.get(table, []):
        lines += [
            f"\tcolumn {quote(name)} = {dax}",
            f"\t\tdataType: {data_type}",
            f"\t\tformatString: {fmt}",
            f"\t\tlineageTag: {tag(table, 'calc', name)}",
            "\t\tsummarizeBy: none",
            "",
            "\t\tannotation SummarizationSetBy = User",
            "",
        ]

    lines += [
        f"\tpartition {table} = m",
        "\t\tmode: import",
        "\t\tsource =",
        m_source(partition_lines),
        "",
        "\tannotation PBI_ResultType = Table",
        "",
    ]
    return "\n".join(lines)


def parquet_partition(table: str) -> list[str]:
    return [
        "let",
        f'    Source = Parquet.Document ( File.Contents ( DataFolder & "{table}.parquet" ) )',
        "in",
        "    Source",
    ]


def build_model(data_folder: str) -> None:
    if MODEL_DIR.exists():
        shutil.rmtree(MODEL_DIR)
    tables_dir = MODEL_DIR / "definition" / "tables"
    tables_dir.mkdir(parents=True)

    write_json(
        MODEL_DIR / "definition.pbism",
        {"$schema": f"{SCHEMA}/item/semanticModel/definitionProperties/1.0.0/schema.json", "version": "4.2", "settings": {}},
    )
    write_text(MODEL_DIR / "definition" / "database.tmdl", "database\n\tcompatibilityLevel: 1600\n")

    table_names = ["dim_category", *PARQUET_TABLES]
    model = [
        "model Model",
        "\tculture: en-US",
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
        "\tdiscourageImplicitMeasures",
        "\tsourceQueryCulture: en-US",
        "\tdataAccessOptions",
        "\t\tlegacyRedirects",
        "\t\treturnErrorValuesAsNull",
        "",
        f"annotation PBI_QueryOrder = {json.dumps(['DataFolder', *table_names])}",
        "",
        "annotation __PBI_TimeIntelligenceEnabled = 0",
        "",
        *[f"ref table {name}" for name in table_names],
        "",
    ]
    write_text(MODEL_DIR / "definition" / "model.tmdl", "\n".join(model))

    folder = data_folder.rstrip("\\/") + "\\"
    expressions = [
        f'expression DataFolder = "{folder}" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]',
        f"\tlineageTag: {tag('expression', 'DataFolder')}",
        "",
        "\tannotation PBI_ResultType = Text",
        "",
    ]
    write_text(MODEL_DIR / "definition" / "expressions.tmdl", "\n".join(expressions))

    marts = PROJECT_DIR / "data" / "marts"
    for table in PARQUET_TABLES:
        schema = pq.read_schema(marts / f"{table}.parquet")
        columns = [(name, ARROW_TO_TMDL[str(dtype)]) for name, dtype in zip(schema.names, schema.types)]
        write_text(tables_dir / f"{table}.tmdl", table_tmdl(table, columns, parquet_partition(table)))

    category_partition = [
        "let",
        '    Source = Parquet.Document ( File.Contents ( DataFolder & "dim_product.parquet" ) ),',
        '    Categories = Table.Distinct ( Table.SelectColumns ( Source, { "product_category" } ) )',
        "in",
        "    Categories",
    ]
    write_text(tables_dir / "dim_category.tmdl", table_tmdl("dim_category", [("product_category", "string")], category_partition))

    relationships = []
    for many_table, many_column, one_table, one_column in RELATIONSHIPS:
        relationships += [
            f"relationship {tag('rel', many_table, many_column, one_table)}",
            f"\tfromColumn: {many_table}.{many_column}",
            f"\ttoColumn: {one_table}.{one_column}",
            "",
        ]
    write_text(MODEL_DIR / "definition" / "relationships.tmdl", "\n".join(relationships))


# --------------------------------------------------------------------------- report helpers


def lit(value) -> dict:
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, (int, float)):
        text = f"{value}D"
    else:
        text = "'" + str(value).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": text}}}


def color(hex_value: str) -> dict:
    return {"solid": {"color": lit(hex_value)}}


def column(table: str, name: str) -> dict:
    return {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}}


def measure(table: str, name: str) -> dict:
    return {"Measure": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}}


def projection(field: dict, display: str | None = None) -> dict:
    kind = "Column" if "Column" in field else "Measure"
    table = field[kind]["Expression"]["SourceRef"]["Entity"]
    name = field[kind]["Property"]
    item = {"field": field, "queryRef": f"{table}.{name}", "nativeQueryRef": display or name}
    if display:
        item["displayName"] = display
    return item


def title_objects(text: str) -> dict:
    return {
        "title": [
            {
                "properties": {
                    "show": lit(True),
                    "text": lit(text),
                    "fontColor": color(INK),
                    "fontSize": lit(12),
                    "bold": lit(True),
                }
            }
        ]
    }


def category_colors(table: str, field_name: str = "product_category") -> list:
    return [
        {
            "properties": {"fill": color(hex_value)},
            "selector": {
                "data": [
                    {
                        "scopeId": {
                            "Comparison": {
                                "ComparisonKind": 0,
                                "Left": column(table, field_name),
                                "Right": {"Literal": {"Value": f"'{category}'"}},
                            }
                        }
                    }
                ]
            },
        }
        for category, hex_value in CATEGORY_COLORS.items()
    ]


def measure_colors(table: str, names: list[str]) -> list:
    return [
        {"properties": {"fill": color(SERIES[index % len(SERIES)])}, "selector": {"metadata": f"{table}.{name}"}}
        for index, name in enumerate(names)
    ]


class Page:
    def __init__(self, name: str, display_name: str):
        self.name = name
        self.display_name = display_name
        self.visuals: list[dict] = []

    def add(self, visual_name: str, x: int, y: int, w: int, h: int, visual: dict) -> None:
        self.visuals.append(
            {
                "$schema": f"{SCHEMA}/item/report/definition/visualContainer/2.0.0/schema.json",
                "name": visual_name,
                "position": {"x": x, "y": y, "z": len(self.visuals) * 1000, "width": w, "height": h, "tabOrder": len(self.visuals) * 1000},
                "visual": visual,
            }
        )

    # --- visual builders

    def header(self, title: str, subtitle: str) -> None:
        paragraphs = [
            {"textRuns": [{"value": title, "textStyle": {"fontWeight": "bold", "fontSize": "20pt", "color": INK}}]},
            {"textRuns": [{"value": subtitle, "textStyle": {"fontSize": "10pt", "color": INK_2}}]},
        ]
        self.add(
            "header",
            20,
            10,
            820,
            70,
            {
                "visualType": "textbox",
                "objects": {"general": [{"properties": {"paragraphs": paragraphs}}]},
                "visualContainerObjects": {"background": [{"properties": {"show": lit(False)}}], "border": [{"properties": {"show": lit(False)}}]},
            },
        )

    def slicer(self, name: str, x: int, y: int, w: int, h: int, field: dict, title: str, mode: str = "Dropdown") -> None:
        self.add(
            name,
            x,
            y,
            w,
            h,
            {
                "visualType": "slicer",
                "query": {"queryState": {"Values": {"projections": [projection(field)]}}},
                "objects": {"data": [{"properties": {"mode": lit(mode)}}]},
                "visualContainerObjects": title_objects(title),
            },
        )

    def card(self, name: str, x: int, y: int, w: int, h: int, field: dict, label: str) -> None:
        self.add(
            name,
            x,
            y,
            w,
            h,
            {
                "visualType": "card",
                "query": {"queryState": {"Values": {"projections": [projection(field, label)]}}},
                "objects": {
                    "labels": [{"properties": {"color": color(INK), "fontSize": lit(24)}}],
                    "categoryLabels": [{"properties": {"show": lit(True), "color": color(INK_2), "fontSize": lit(10)}}],
                },
            },
        )

    def chart(
        self,
        name: str,
        visual_type: str,
        x: int,
        y: int,
        w: int,
        h: int,
        title: str,
        category: dict,
        values: list[dict],
        series: dict | None = None,
        data_point: list | None = None,
        sort: tuple[dict, str] | None = None,
        labels: bool = False,
        value_names: list[str] | None = None,
    ) -> None:
        query_state = {
            "Category": {"projections": [projection(category)]},
            "Y": {"projections": [projection(value, (value_names or [None] * len(values))[i]) for i, value in enumerate(values)]},
        }
        if series:
            query_state["Series"] = {"projections": [projection(series)]}
        query = {"queryState": query_state}
        if sort:
            query["sortDefinition"] = {"sort": [{"field": sort[0], "direction": sort[1]}], "isDefaultSort": False}

        objects = {"legend": [{"properties": {"show": lit(bool(series) or len(values) > 1), "position": lit("Top")}}]}
        if data_point:
            objects["dataPoint"] = data_point
        if labels:
            objects["labels"] = [{"properties": {"show": lit(True), "color": color(INK), "fontSize": lit(9)}}]
        if visual_type == "lineChart":
            objects["lineStyles"] = [{"properties": {"strokeWidth": lit(2)}}]

        self.add(name, x, y, w, h, {"visualType": visual_type, "query": query, "objects": objects, "visualContainerObjects": title_objects(title)})

    def donut(self, name: str, x: int, y: int, w: int, h: int, title: str, category: dict, value: dict, colors: dict) -> None:
        data_point = [
            {
                "properties": {"fill": color(hex_value)},
                "selector": {
                    "data": [
                        {"scopeId": {"Comparison": {"ComparisonKind": 0, "Left": category, "Right": {"Literal": {"Value": f"'{label}'"}}}}}
                    ]
                },
            }
            for label, hex_value in colors.items()
        ]
        self.add(
            name,
            x,
            y,
            w,
            h,
            {
                "visualType": "donutChart",
                "query": {"queryState": {"Category": {"projections": [projection(category)]}, "Y": {"projections": [projection(value)]}}},
                "objects": {"dataPoint": data_point, "legend": [{"properties": {"show": lit(True), "position": lit("Top")}}]},
                "visualContainerObjects": title_objects(title),
            },
        )

    def table(self, name: str, x: int, y: int, w: int, h: int, title: str, fields: list[dict], sort: tuple[dict, str] | None = None) -> None:
        query = {"queryState": {"Values": {"projections": [projection(f) for f in fields]}}}
        if sort:
            query["sortDefinition"] = {"sort": [{"field": sort[0], "direction": sort[1]}], "isDefaultSort": False}
        self.add(name, x, y, w, h, {"visualType": "tableEx", "query": query, "visualContainerObjects": title_objects(title)})

    def matrix(self, name: str, x: int, y: int, w: int, h: int, title: str, rows: dict, columns: dict, value: dict) -> None:
        self.add(
            name,
            x,
            y,
            w,
            h,
            {
                "visualType": "pivotTable",
                "query": {
                    "queryState": {
                        "Rows": {"projections": [projection(rows)]},
                        "Columns": {"projections": [projection(columns)]},
                        "Values": {"projections": [projection(value)]},
                    }
                },
                "visualContainerObjects": title_objects(title),
            },
        )


# --------------------------------------------------------------------------- pages

M = measure
C = column


def build_pages() -> list[Page]:
    pages = []
    category_slicer = C("dim_category", "product_category")

    # 1. Executive overview
    p = Page("p1_overview", "Executive Overview")
    p.header("Apple Product Pricing Intelligence", "80,000 listings · 31 models · Amazon & Flipkart · Sep 2020 – Jul 2026")
    p.slicer("s_category", 1000, 16, 260, 64, category_slicer, "Category")
    cards = [
        (M("fct_daily_market_prices", "Listings"), "Listings"),
        (M("fct_daily_market_prices", "Models Tracked"), "Models"),
        (M("fct_daily_market_prices", "Price Index"), "Avg price index (launch = 100)"),
        (M("mart_sale_event_impact", "Event Real Saving %"), "Real saving on sale events"),
        (M("mart_forecast_backtest", "Improvement vs Naive 7d %"), "7-day forecast vs naive"),
    ]
    for i, (field, label) in enumerate(cards):
        p.card(f"card_{i}", 20 + i * 250, 92, 238, 96, field, label)
    p.chart(
        "depreciation", "lineChart", 20, 200, 800, 500, "Value retention after release (New units, launch price = 100)",
        C("mart_depreciation_curve", "months_since_release"), [M("mart_depreciation_curve", "Price Index New")],
        series=C("mart_depreciation_curve", "product_category"), data_point=category_colors("mart_depreciation_curve"),
    )
    p.chart(
        "successor_by_category", "clusteredBarChart", 832, 200, 428, 244, "Price change within 60 days of successor launch",
        C("mart_successor_launch_impact", "product_category"), [M("mart_successor_launch_impact", "Successor Price Change %")],
        labels=True, sort=(M("mart_successor_launch_impact", "Successor Price Change %"), "Ascending"),
    )
    p.chart(
        "event_saving", "clusteredBarChart", 832, 456, 428, 244, "Real saving vs normal price, by sale event",
        C("mart_sale_event_impact", "sale_event"), [M("mart_sale_event_impact", "Real Saving vs Normal %")],
        labels=True, sort=(M("mart_sale_event_impact", "Real Saving vs Normal %"), "Descending"),
    )
    pages.append(p)

    # 2. Price explorer
    p = Page("p2_price_explorer", "Price Explorer")
    p.header("Price Explorer", "Daily median price by marketplace · pick a model, condition and period")
    p.slicer("s_model", 700, 16, 280, 64, C("dim_product", "model_name"), "Model")
    p.slicer("s_condition", 990, 16, 130, 64, C("fct_daily_market_prices", "condition"), "Condition")
    p.slicer("s_category", 1130, 16, 130, 64, category_slicer, "Category")
    p.slicer("s_date", 20, 92, 400, 70, C("dim_date", "date_day"), "Period", mode="Between")
    p.card("card_price", 432, 92, 200, 70, M("fct_daily_market_prices", "Avg Price"), "Avg price")
    p.card("card_index", 644, 92, 200, 70, M("fct_daily_market_prices", "Price Index"), "Price index")
    p.card("card_discount", 856, 92, 200, 70, M("fct_daily_market_prices", "Discount vs Launch %"), "Below launch price")
    p.card("card_event", 1068, 92, 192, 70, M("fct_daily_market_prices", "Event Savings vs Normal %"), "Event saving vs normal")
    p.chart(
        "price_history", "lineChart", 20, 174, 1240, 300, "Daily median price by platform",
        C("dim_date", "date_day"), [M("fct_daily_market_prices", "Avg Price")],
        series=C("fct_daily_market_prices", "platform"),
        data_point=[
            {
                "properties": {"fill": color(hex_value)},
                "selector": {"data": [{"scopeId": {"Comparison": {"ComparisonKind": 0, "Left": C("fct_daily_market_prices", "platform"), "Right": {"Literal": {"Value": f"'{name}'"}}}}}]},
            }
            for name, hex_value in {"Amazon": "#4A3AA7", "Flipkart": "#E87BA4"}.items()
        ],
    )
    p.table(
        "scorecard", 20, 486, 1240, 214, "Model scorecard",
        [
            C("mart_model_scorecard", "model_name"),
            C("mart_model_scorecard", "product_category"),
            C("mart_model_scorecard", "release_date"),
            C("mart_model_scorecard", "msrp_usd"),
            C("mart_model_scorecard", "current_price_usd"),
            C("mart_model_scorecard", "current_price_index"),
            C("mart_model_scorecard", "avg_monthly_depreciation_pts"),
            C("mart_model_scorecard", "pct_days_above_msrp"),
            C("mart_model_scorecard", "avg_event_savings_pct"),
            C("mart_model_scorecard", "refurbished_discount_pct"),
        ],
        sort=(C("mart_model_scorecard", "release_date"), "Descending"),
    )
    pages.append(p)

    # 3. Life cycle & launches
    p = Page("p3_life_cycle", "Life Cycle & Launches")
    p.header("Life Cycle & Launches", "Prices step down at every new launch · iPhone −15% and Watch −20% within 60 days; Mac barely moves")
    p.slicer("s_category", 1000, 16, 260, 64, category_slicer, "Category")
    p.chart(
        "curve_new", "lineChart", 20, 92, 620, 300, "Depreciation curve · New (launch price = 100)",
        C("mart_depreciation_curve", "months_since_release"), [M("mart_depreciation_curve", "Price Index New")],
        series=C("mart_depreciation_curve", "product_category"), data_point=category_colors("mart_depreciation_curve"),
    )
    p.chart(
        "curve_refurb", "lineChart", 20, 404, 620, 296, "Depreciation curve · Refurbished",
        C("mart_depreciation_curve", "months_since_release"), [M("mart_depreciation_curve", "Price Index Refurbished")],
        series=C("mart_depreciation_curve", "product_category"), data_point=category_colors("mart_depreciation_curve"),
    )
    p.chart(
        "successor_models", "barChart", 652, 92, 608, 608, "Price change in the 60 days after the successor's release",
        C("mart_successor_launch_impact", "model_name"), [M("mart_successor_launch_impact", "Successor Price Change %")],
        series=C("mart_successor_launch_impact", "product_category"), data_point=category_colors("mart_successor_launch_impact"),
        sort=(M("mart_successor_launch_impact", "Successor Price Change %"), "Ascending"),
    )
    pages.append(p)

    # 4. Sale events
    p = Page("p4_sale_events", "Sale Events")
    p.header("Sale Events", "Headline discounts vs launch price overstate the benefit · real savings are measured vs each product's normal price")
    p.slicer("s_category", 1000, 16, 260, 64, category_slicer, "Category")
    for i, (field, label) in enumerate(
        [
            (M("mart_sale_event_impact", "Event Headline Discount %"), "Headline discount vs launch"),
            (M("mart_sale_event_impact", "Event Real Saving %"), "Real saving vs normal price"),
            (M("mart_sale_event_impact", "Event Days Saving 5%+ (events)"), "Event days saving 5%+"),
            (M("mart_sale_event_impact", "Event Series-Days"), "Event series-days"),
        ]
    ):
        p.card(f"card_{i}", 20 + i * 312, 92, 300, 90, field, label)
    names = ["Headline Discount %", "Real Saving vs Normal %"]
    p.chart(
        "headline_vs_real", "clusteredBarChart", 20, 194, 700, 506, "Headline discount vs real saving, by event",
        C("mart_sale_event_impact", "sale_event"), [M("mart_sale_event_impact", n) for n in names],
        data_point=measure_colors("mart_sale_event_impact", names), labels=True,
        sort=(M("mart_sale_event_impact", "Real Saving vs Normal %"), "Descending"),
    )
    p.matrix(
        "event_matrix", 732, 194, 528, 250, "Real saving vs normal price · event × category",
        C("mart_sale_event_impact", "sale_event"), C("mart_sale_event_impact", "product_category"),
        M("mart_sale_event_impact", "Real Saving vs Normal %"),
    )
    p.chart(
        "saving_usd", "clusteredColumnChart", 732, 456, 528, 244, "Average saving per event day (USD, vs normal price)",
        C("mart_sale_event_impact", "sale_event"), [M("mart_sale_event_impact", "Avg Saving per Day (USD)")], labels=True,
        sort=(M("mart_sale_event_impact", "Avg Saving per Day (USD)"), "Descending"),
    )
    pages.append(p)

    # 5. Marketplaces & condition
    p = Page("p5_marketplaces", "Marketplaces & Condition")
    p.header("Marketplaces & Condition", "Same product, same day · neither platform is cheaper overall, but daily gaps average 2.7%")
    p.slicer("s_condition", 860, 16, 130, 64, C("mart_platform_price_gap", "condition"), "Condition")
    p.slicer("s_category", 1000, 16, 260, 64, category_slicer, "Category")
    for i, (field, label) in enumerate(
        [
            (M("mart_platform_price_gap", "Matched Days"), "Matched product-days"),
            (M("mart_platform_price_gap", "Amazon Cheaper %"), "Amazon cheaper"),
            (M("mart_platform_price_gap", "Median Gap %"), "Median gap (Amazon − Flipkart)"),
            (M("mart_platform_price_gap", "Avg Absolute Gap %"), "Average daily gap"),
        ]
    ):
        p.card(f"card_{i}", 20 + i * 312, 92, 300, 90, field, label)
    p.chart(
        "gap_distribution", "clusteredColumnChart", 20, 194, 620, 250, "Distribution of the Amazon vs Flipkart gap (%, negative = Amazon cheaper)",
        C("mart_platform_price_gap", "Gap Bucket %"), [M("mart_platform_price_gap", "Matched Days")],
        sort=(C("mart_platform_price_gap", "Gap Bucket %"), "Ascending"),
    )
    p.chart(
        "amazon_cheaper_trend", "lineChart", 652, 194, 608, 250, "Share of days Amazon is cheaper, by month",
        C("dim_date", "month_start"), [M("mart_platform_price_gap", "Amazon Cheaper %")],
    )
    p.chart(
        "refurb_discount", "clusteredColumnChart", 20, 456, 1240, 244, "Refurbished discount vs a new unit (same model, platform and day)",
        C("mart_model_scorecard", "model_name"), [M("mart_model_scorecard", "Refurbished Discount %")],
        sort=(M("mart_model_scorecard", "Refurbished Discount %"), "Descending"),
    )
    pages.append(p)

    # 6. Forecasts & buy or wait
    p = Page("p6_forecasts_deals", "Forecasts & Buy or Wait")
    p.header("Forecasts & Buy or Wait", "CatBoost 7- and 30-day forecasts on the unseen final 180 days · calibrated 80% ranges drive the buy / wait call")
    p.slicer("s_recommendation", 860, 16, 130, 64, C("mart_deal_scores", "recommendation"), "Call")
    p.slicer("s_category", 1000, 16, 260, 64, category_slicer, "Category")
    for i, (field, label) in enumerate(
        [
            (M("mart_forecast_backtest", "Forecast MAE 7d"), "7-day MAE"),
            (M("mart_forecast_backtest", "Improvement vs Naive 7d %"), "7-day vs last price"),
            (M("mart_forecast_backtest", "Improvement vs 30-Day Avg 7d %"), "7-day vs 30-day avg"),
            (M("mart_forecast_backtest", "Forecast MAE 30d"), "30-day MAE"),
            (M("mart_forecast_backtest", "Improvement vs 30-Day Avg 30d %"), "30-day vs 30-day avg"),
            (M("mart_forecast_backtest", "Interval Coverage 7d %"), "80% range coverage (7d)"),
        ]
    ):
        p.card(f"card_{i}", 20 + i * 208, 92, 198, 86, field, label)
    names = ["Forecast MAE 7d", "30-Day Avg MAE 7d", "Naive MAE 7d"]
    p.chart(
        "mae_by_category", "clusteredColumnChart", 20, 190, 520, 250, "7-day forecast error by category (lower is better)",
        C("mart_forecast_backtest", "product_category"), [M("mart_forecast_backtest", n) for n in names],
        data_point=measure_colors("mart_forecast_backtest", names), value_names=["CatBoost", "30-day average", "Last price"],
    )
    p.donut(
        "calls", 552, 190, 300, 250, "Recommendations", C("mart_deal_scores", "recommendation"), M("mart_deal_scores", "Series Scored"),
        {"Buy now": "#0CA30C", "Wait": "#EC835A", "No rush": "#C3C2B7"},
    )
    names = ["Forecast MAE", "30-Day Avg MAE", "Naive MAE"]
    p.chart(
        "mae_by_horizon", "clusteredColumnChart", 864, 190, 396, 250, "Error by horizon (days)",
        C("mart_forecast_backtest", "horizon_days"), [M("mart_forecast_backtest", n) for n in names],
        data_point=measure_colors("mart_forecast_backtest", names), value_names=["CatBoost", "30-day average", "Last price"],
    )
    p.table(
        "deals", 20, 452, 1240, 248, "Buy now / wait by series (sorted by deal score)",
        [
            C("mart_deal_scores", "recommendation"),
            C("mart_deal_scores", "model_name"),
            C("mart_deal_scores", "platform"),
            C("mart_deal_scores", "condition"),
            C("mart_deal_scores", "current_price_usd"),
            C("mart_deal_scores", "discount_vs_normal_pct"),
            C("mart_deal_scores", "forecast_30d_usd"),
            C("mart_deal_scores", "forecast_30d_p10_usd"),
            C("mart_deal_scores", "forecast_30d_p90_usd"),
            C("mart_deal_scores", "deal_score"),
            C("mart_deal_scores", "recommendation_reason"),
        ],
        sort=(C("mart_deal_scores", "deal_score"), "Descending"),
    )
    pages.append(p)
    return pages


# --------------------------------------------------------------------------- report files

THEME = {
    "name": "Apple Pricing",
    "dataColors": ["#2A78D6", "#EB6834", "#1BAF7A", "#EDA100", "#E87BA4", "#008300", "#4A3AA7", "#E34948"],
    "background": "#FFFFFF",
    "foreground": INK,
    "tableAccent": "#2A78D6",
    "good": "#0CA30C",
    "neutral": "#EDA100",
    "bad": "#D03B3B",
    "textClasses": {
        "callout": {"fontSize": 24, "fontFace": "Segoe UI Semibold", "color": INK},
        "title": {"fontSize": 12, "fontFace": "Segoe UI Semibold", "color": INK},
        "header": {"fontSize": 12, "fontFace": "Segoe UI Semibold", "color": INK},
        "label": {"fontSize": 10, "fontFace": "Segoe UI", "color": INK_2},
    },
    "visualStyles": {
        "*": {
            "*": {
                "background": [{"show": True, "color": {"solid": {"color": "#FFFFFF"}}, "transparency": 0}],
                "border": [{"show": True, "color": {"solid": {"color": RULE}}, "radius": 8}],
                "dropShadow": [{"show": False}],
                "valueAxis": [{"gridlineColor": {"solid": {"color": RULE}}, "labelColor": {"solid": {"color": MUTED}}}],
                "categoryAxis": [{"labelColor": {"solid": {"color": MUTED}}}],
            }
        },
        "page": {"*": {"background": [{"color": {"solid": {"color": "#F5F5F2"}}, "transparency": 0}]}},
    },
}


def build_report() -> None:
    if REPORT_DIR.exists():
        shutil.rmtree(REPORT_DIR)
    definition = REPORT_DIR / "definition"
    (definition / "pages").mkdir(parents=True)

    write_json(
        REPORT_DIR / "definition.pbir",
        {
            "$schema": f"{SCHEMA}/item/report/definitionProperties/2.0.0/schema.json",
            "version": "4.0",
            "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}},
        },
    )
    write_json(definition / "version.json", {"$schema": f"{SCHEMA}/item/report/definition/versionMetadata/1.0.0/schema.json", "version": "2.0.0"})

    theme_name = "ApplePricingTheme.json"
    write_json(REPORT_DIR / "StaticResources" / "RegisteredResources" / theme_name, THEME)
    write_json(
        definition / "report.json",
        {
            "$schema": f"{SCHEMA}/item/report/definition/report/2.0.0/schema.json",
            "themeCollection": {"customTheme": {"name": theme_name, "reportVersionAtImport": "5.61", "type": "RegisteredResources"}},
            "resourcePackages": [
                {
                    "name": "RegisteredResources",
                    "type": "RegisteredResources",
                    "items": [{"name": theme_name, "path": theme_name, "type": "CustomTheme"}],
                }
            ],
            "settings": {"useStylableVisualContainerHeader": True, "defaultDrillFilterOtherVisuals": True},
        },
    )

    pages = build_pages()
    write_json(
        definition / "pages" / "pages.json",
        {
            "$schema": f"{SCHEMA}/item/report/definition/pagesMetadata/1.0.0/schema.json",
            "pageOrder": [p.name for p in pages],
            "activePageName": pages[0].name,
        },
    )
    for page in pages:
        page_dir = definition / "pages" / page.name
        write_json(
            page_dir / "page.json",
            {
                "$schema": f"{SCHEMA}/item/report/definition/page/2.0.0/schema.json",
                "name": page.name,
                "displayName": page.display_name,
                "displayOption": "FitToPage",
                "height": PAGE_H,
                "width": PAGE_W,
            },
        )
        for visual in page.visuals:
            write_json(page_dir / "visuals" / visual["name"] / "visual.json", visual)

    write_json(
        ROOT / f"{NAME}.pbip",
        {
            "$schema": f"{SCHEMA}/pbip/pbipProperties/1.0.0/schema.json",
            "version": "1.0",
            "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
            "settings": {"enableAutoRecovery": True},
        },
    )


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-folder", default=str(PROJECT_DIR / "data" / "marts"), help="Absolute path to data/marts")
    args = parser.parse_args()
    build_model(args.data_folder)
    build_report()
    print(f"Wrote {ROOT / (NAME + '.pbip')}")


if __name__ == "__main__":
    main()
