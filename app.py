from pathlib import Path
import json

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st


# ==========================================
# PAGE CONFIGURATION
# ==========================================

st.set_page_config(
    page_title="Apple Pricing Analysis"
    page_icon="🍎",
    layout="wide",
)


# ==========================================
# FILE PATHS
# ==========================================

PROJECT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_DIR / "outputs"

CLEANED_DATA_PATH = (
    OUTPUT_DIR
    / "cleaned_apple_prices.csv"
)

DAILY_DATA_PATH = (
    OUTPUT_DIR
    / "daily_market_prices.csv"
)

PREDICTIONS_7D_PATH = (
    OUTPUT_DIR
    / "predictions_7d.csv"
)

PREDICTIONS_30D_PATH = (
    OUTPUT_DIR
    / "predictions_30d.csv"
)

DEAL_SCORES_PATH = (
    OUTPUT_DIR
    / "deal_scores.csv"
)

MODEL_METRICS_PATH = (
    OUTPUT_DIR
    / "model_metrics.json"
)

QUALITY_REPORT_PATH = (
    OUTPUT_DIR
    / "data_quality_report.json"
)


# ==========================================
# DATA-LOADING FUNCTIONS
# ==========================================

@st.cache_data
def load_csv(path):
    if not path.exists():
        return pd.DataFrame()

    data = pd.read_csv(path)

    if "date" in data.columns:
        data["date"] = pd.to_datetime(
            data["date"],
            errors="coerce",
        )

    return data


@st.cache_data
def load_json(path):
    if not path.exists():
        return {}

    with open(
        path,
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


df = load_csv(CLEANED_DATA_PATH)
daily = load_csv(DAILY_DATA_PATH)
predictions_7d = load_csv(
    PREDICTIONS_7D_PATH
)
predictions_30d = load_csv(
    PREDICTIONS_30D_PATH
)
deal_scores = load_csv(
    DEAL_SCORES_PATH
)

model_metrics = load_json(
    MODEL_METRICS_PATH
)

quality_report = load_json(
    QUALITY_REPORT_PATH
)


# ==========================================
# CHECK REQUIRED OUTPUTS
# ==========================================

if df.empty:
    st.error(
        "The cleaned dataset was not found. "
        "Run the notebook before starting Streamlit."
    )
    st.stop()


# ==========================================
# TITLE
# ==========================================

st.title(
    "🍎 Apple Product Pricing Intelligence"
)

st.caption(
    "Exploratory analysis, platform comparison, "
    "sale-event insights, price forecasting, and deal detection"
)


# ==========================================
# SIDEBAR FILTERS
# ==========================================

st.sidebar.header("Dashboard Filters")

category_options = sorted(
    df["product_category"]
    .dropna()
    .unique()
    .tolist()
)

selected_categories = (
    st.sidebar.multiselect(
        "Product category",
        options=category_options,
        default=category_options,
    )
)

platform_options = sorted(
    df["platform"]
    .dropna()
    .unique()
    .tolist()
)

selected_platforms = (
    st.sidebar.multiselect(
        "Platform",
        options=platform_options,
        default=platform_options,
    )
)

condition_options = sorted(
    df["condition"]
    .dropna()
    .unique()
    .tolist()
)

selected_conditions = (
    st.sidebar.multiselect(
        "Condition",
        options=condition_options,
        default=condition_options,
    )
)

minimum_date = df["date"].min().date()
maximum_date = df["date"].max().date()

selected_date_range = (
    st.sidebar.date_input(
        "Date range",
        value=(
            minimum_date,
            maximum_date,
        ),
        min_value=minimum_date,
        max_value=maximum_date,
    )
)

filtered_df = df.loc[
    df["product_category"].isin(
        selected_categories
    )
    & df["platform"].isin(
        selected_platforms
    )
    & df["condition"].isin(
        selected_conditions
    )
].copy()

if len(selected_date_range) == 2:
    start_date = pd.Timestamp(
        selected_date_range[0]
    )

    end_date = pd.Timestamp(
        selected_date_range[1]
    )

    filtered_df = filtered_df.loc[
        filtered_df["date"].between(
            start_date,
            end_date,
        )
    ]


# ==========================================
# DASHBOARD TABS
# ==========================================

tabs = st.tabs([
    "Executive Overview",
    "Price Trends",
    "Platform Comparison",
    "Sale Events",
    "Forecasting",
    "Deal Finder",
    "Data Quality",
])


# ==========================================
# EXECUTIVE OVERVIEW
# ==========================================

with tabs[0]:

    st.subheader("Executive Overview")

    metric_columns = st.columns(6)

    metric_columns[0].metric(
        "Records",
        f"{len(filtered_df):,}",
    )

    metric_columns[1].metric(
        "Models",
        f"{filtered_df['model_name'].nunique():,}",
    )

    metric_columns[2].metric(
        "Average Price",
        f"${filtered_df['current_price_usd'].mean():,.2f}",
    )

    metric_columns[3].metric(
        "Median Discount",
        f"{filtered_df['discount_pct'].median():,.1f}%",
    )

    metric_columns[4].metric(
        "Average Rating",
        f"{filtered_df['rating'].mean():,.2f}",
    )

    metric_columns[5].metric(
        "In-Stock Rate",
        f"{filtered_df['is_in_stock'].mean() * 100:,.1f}%",
    )

    category_summary = (
        filtered_df
        .groupby(
            "product_category",
            as_index=False,
        )
        .agg(
            average_price=(
                "current_price_usd",
                "mean",
            ),
            median_discount=(
                "discount_pct",
                "median",
            ),
            average_price_index=(
                "price_index",
                "mean",
            ),
            observations=(
                "current_price_usd",
                "size",
            ),
        )
    )

    col1, col2 = st.columns(2)

    with col1:
        figure = px.bar(
            category_summary,
            x="product_category",
            y="average_price",
            title="Average Price by Category",
            labels={
                "product_category": "Category",
                "average_price": "Average Price (USD)",
            },
        )

        st.plotly_chart(
            figure,
            use_container_width=True,
        )

    with col2:
        figure = px.bar(
            category_summary,
            x="product_category",
            y="average_price_index",
            title="Average Value Retention",
            labels={
                "product_category": "Category",
                "average_price_index": "Price Index",
            },
        )

        figure.add_hline(
            y=100,
            line_dash="dash",
        )

        st.plotly_chart(
            figure,
            use_container_width=True,
        )

    st.dataframe(
        category_summary.sort_values(
            "average_price",
            ascending=False,
        ),
        use_container_width=True,
    )


# ==========================================
# PRICE TRENDS
# ==========================================

with tabs[1]:

    st.subheader("Product Price Trends")

    model_options = sorted(
        filtered_df["model_name"]
        .dropna()
        .unique()
        .tolist()
    )

    if model_options:

        selected_model = st.selectbox(
            "Select a product model",
            options=model_options,
        )

        model_data = filtered_df.loc[
            filtered_df["model_name"]
            == selected_model
        ].copy()

        model_trend = (
            model_data
            .groupby(
                [
                    "date",
                    "platform",
                    "condition",
                ],
                as_index=False,
            )
            .agg(
                median_price=(
                    "current_price_usd",
                    "median",
                ),
                launch_price=(
                    "launch_price_usd",
                    "median",
                ),
                median_discount=(
                    "discount_pct",
                    "median",
                ),
            )
        )

        figure = px.line(
            model_trend,
            x="date",
            y="median_price",
            color="platform",
            line_dash="condition",
            title=f"Price History: {selected_model}",
            labels={
                "date": "Date",
                "median_price": "Median Price (USD)",
                "platform": "Platform",
                "condition": "Condition",
            },
        )

        st.plotly_chart(
            figure,
            use_container_width=True,
        )

        depreciation = (
            model_data
            .groupby(
                "days_since_first_seen",
                as_index=False,
            )
            .agg(
                median_price_index=(
                    "price_index",
                    "median",
                )
            )
        )

        figure = px.line(
            depreciation,
            x="days_since_first_seen",
            y="median_price_index",
            title="Product Depreciation",
            labels={
                "days_since_first_seen": "Days Since First Observed",
                "median_price_index": "Median Price Index",
            },
        )

        figure.add_hline(
            y=100,
            line_dash="dash",
        )

        st.plotly_chart(
            figure,
            use_container_width=True,
        )


# ==========================================
# PLATFORM COMPARISON
# ==========================================

with tabs[2]:

    st.subheader("Amazon vs Flipkart")

    platform_summary = (
        filtered_df
        .groupby(
            "platform",
            as_index=False,
        )
        .agg(
            average_price=(
                "current_price_usd",
                "mean",
            ),
            median_price=(
                "current_price_usd",
                "median",
            ),
            average_discount=(
                "discount_pct",
                "mean",
            ),
            average_price_index=(
                "price_index",
                "mean",
            ),
            observations=(
                "current_price_usd",
                "size",
            ),
        )
    )

    st.dataframe(
        platform_summary,
        use_container_width=True,
    )

    figure = px.box(
        filtered_df,
        x="platform",
        y="price_index",
        color="condition",
        points=False,
        title="Price Retention by Platform",
        labels={
            "platform": "Platform",
            "price_index": "Price Index",
            "condition": "Condition",
        },
    )

    st.plotly_chart(
        figure,
        use_container_width=True,
    )

    matched = (
        filtered_df
        .groupby(
            [
                "date",
                "model_name",
                "condition",
                "platform",
            ]
        )["current_price_usd"]
        .median()
        .unstack("platform")
    )

    if {
        "Amazon",
        "Flipkart",
    }.issubset(matched.columns):

        matched = matched[
            [
                "Amazon",
                "Flipkart",
            ]
        ].dropna()

        matched[
            "amazon_minus_flipkart"
        ] = (
            matched["Amazon"]
            - matched["Flipkart"]
        )

        figure = px.histogram(
            matched.reset_index(),
            x="amazon_minus_flipkart",
            nbins=50,
            title=(
                "Matched Price Difference: "
                "Amazon Minus Flipkart"
            ),
            labels={
                "amazon_minus_flipkart": (
                    "Amazon Price - Flipkart Price"
                )
            },
        )

        figure.add_vline(
            x=0,
            line_dash="dash",
        )

        st.plotly_chart(
            figure,
            use_container_width=True,
        )


# ==========================================
# SALE EVENTS
# ==========================================

with tabs[3]:

    st.subheader("Sale-Event Analysis")

    sale_summary = (
        filtered_df
        .groupby(
            "sale_event",
            as_index=False,
        )
        .agg(
            observations=(
                "discount_pct",
                "size",
            ),
            average_discount=(
                "discount_pct",
                "mean",
            ),
            median_discount=(
                "discount_pct",
                "median",
            ),
            average_price=(
                "current_price_usd",
                "mean",
            ),
            in_stock_rate=(
                "is_in_stock",
                "mean",
            ),
        )
    )

    sale_summary[
        "in_stock_rate"
    ] *= 100

    sale_summary = sale_summary.sort_values(
        "average_discount",
        ascending=False,
    )

    figure = px.bar(
        sale_summary,
        x="sale_event",
        y="average_discount",
        title="Average Discount by Sale Event",
        labels={
            "sale_event": "Sale Event",
            "average_discount": "Average Discount (%)",
        },
    )

    st.plotly_chart(
        figure,
        use_container_width=True,
    )

    figure = px.box(
        filtered_df,
        x="sale_event",
        y="discount_pct",
        color="product_category",
        points=False,
        title="Discount Distribution by Event and Category",
        labels={
            "sale_event": "Sale Event",
            "discount_pct": "Discount (%)",
            "product_category": "Category",
        },
    )

    st.plotly_chart(
        figure,
        use_container_width=True,
    )

    st.dataframe(
        sale_summary,
        use_container_width=True,
    )


# ==========================================
# FORECASTING
# ==========================================

with tabs[4]:

    st.subheader("Price Forecasting")

    if model_metrics:

        seven_day = model_metrics.get(
            "7_day_forecast",
            {},
        )

        thirty_day = model_metrics.get(
            "30_day_forecast",
            {},
        )

        metric_columns = st.columns(4)

        metric_columns[0].metric(
            "7-Day MAE",
            (
                f"${seven_day.get('model', {}).get('MAE', 0):,.2f}"
            ),
        )

        metric_columns[1].metric(
            "7-Day Improvement",
            (
                f"{seven_day.get('mae_improvement_pct', 0):,.1f}%"
            ),
        )

        metric_columns[2].metric(
            "30-Day MAE",
            (
                f"${thirty_day.get('model', {}).get('MAE', 0):,.2f}"
            ),
        )

        metric_columns[3].metric(
            "30-Day Improvement",
            (
                f"{thirty_day.get('mae_improvement_pct', 0):,.1f}%"
            ),
        )

    forecast_horizon = st.radio(
        "Forecast horizon",
        options=[
            "7 days",
            "30 days",
        ],
        horizontal=True,
    )

    prediction_data = (
        predictions_7d
        if forecast_horizon == "7 days"
        else predictions_30d
    )

    target_column = (
        "target_price_7d"
        if forecast_horizon == "7 days"
        else "target_price_30d"
    )

    if not prediction_data.empty:

        prediction_model_options = sorted(
            prediction_data[
                "model_name"
            ]
            .dropna()
            .unique()
            .tolist()
        )

        selected_prediction_model = (
            st.selectbox(
                "Select model for forecast evaluation",
                options=prediction_model_options,
                key="prediction_model",
            )
        )

        selected_prediction_data = (
            prediction_data.loc[
                prediction_data[
                    "model_name"
                ]
                == selected_prediction_model
            ]
            .sort_values("date")
        )

        comparison_data = (
            selected_prediction_data[
                [
                    "date",
                    target_column,
                    "predicted_price_usd",
                ]
            ]
            .melt(
                id_vars="date",
                var_name="series",
                value_name="price",
            )
        )

        figure = px.line(
            comparison_data,
            x="date",
            y="price",
            color="series",
            title=(
                f"Actual vs Predicted: "
                f"{selected_prediction_model}"
            ),
            labels={
                "date": "Date",
                "price": "Price (USD)",
                "series": "Series",
            },
        )

        st.plotly_chart(
            figure,
            use_container_width=True,
        )

        error_by_category = (
            prediction_data
            .groupby(
                "product_category",
                as_index=False,
            )
            .agg(
                mae=(
                    "absolute_error",
                    "mean",
                ),
                median_error=(
                    "absolute_error",
                    "median",
                ),
            )
        )

        figure = px.bar(
            error_by_category,
            x="product_category",
            y="mae",
            title="Forecast MAE by Product Category",
            labels={
                "product_category": "Category",
                "mae": "MAE (USD)",
            },
        )

        st.plotly_chart(
            figure,
            use_container_width=True,
        )


# ==========================================
# DEAL FINDER
# ==========================================

with tabs[5]:

    st.subheader("Buy-Now Deal Finder")

    if deal_scores.empty:
        st.warning(
            "Deal scores were not found. "
            "Run the modeling sections of the notebook."
        )
    else:

        minimum_score = st.slider(
            "Minimum deal score",
            min_value=0,
            max_value=100,
            value=60,
        )

        filtered_deals = (
            deal_scores.loc[
                deal_scores["deal_score"]
                >= minimum_score
            ]
            .sort_values(
                "deal_score",
                ascending=False,
            )
        )

        display_columns = [
            "platform",
            "product_category",
            "model_name",
            "condition",
            "median_price_usd",
            "launch_price_usd",
            "predicted_price_7d",
            "predicted_change_7d_pct",
            "discount_vs_30_observation_median_pct",
            "median_rating",
            "in_stock_share",
            "deal_score",
        ]

        st.dataframe(
            filtered_deals[
                display_columns
            ],
            use_container_width=True,
            hide_index=True,
        )

        top_deals = filtered_deals.head(20)

        figure = px.bar(
            top_deals,
            x="deal_score",
            y="model_name",
            color="platform",
            orientation="h",
            title="Top Buy-Now Deal Scores",
            labels={
                "deal_score": "Deal Score",
                "model_name": "Product",
                "platform": "Platform",
            },
        )

        figure.update_layout(
            yaxis={
                "categoryorder": "total ascending"
            }
        )

        st.plotly_chart(
            figure,
            use_container_width=True,
        )


# ==========================================
# DATA QUALITY
# ==========================================

with tabs[6]:

    st.subheader("Data-Quality Report")

    if quality_report:

        quality_table = pd.DataFrame({
            "Metric": list(
                quality_report.keys()
            ),
            "Value": list(
                quality_report.values()
            ),
        })

        st.dataframe(
            quality_table,
            use_container_width=True,
            hide_index=True,
        )

    missing_values = pd.DataFrame({
        "column": df.columns,
        "missing_count": df.isna().sum().values,
        "missing_percentage": (
            df.isna().mean().values
            * 100
        ),
    })

    missing_values = missing_values.loc[
        missing_values["missing_count"] > 0
    ].sort_values(
        "missing_percentage",
        ascending=False,
    )

    st.subheader("Missing Values")

    if missing_values.empty:
        st.success(
            "No missing values were found "
            "in the cleaned dataset."
        )
    else:
        st.dataframe(
            missing_values,
            use_container_width=True,
        )

    st.subheader("Dataset Preview")

    st.dataframe(
        filtered_df.head(100),
        use_container_width=True,
    )