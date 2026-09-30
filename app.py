"""Apple Product Pricing Intelligence - Streamlit dashboard.

Reads the Parquet exports of the dbt marts in data/marts/ (rebuild them with
`python -m apple_pricing.pipeline`).
"""

import pandas as pd
import streamlit as st

from dashboard import views
from dashboard.data import load
from dashboard.theme import CATEGORY_ORDER

st.set_page_config(page_title="Apple Pricing Intelligence", page_icon="🍎", layout="wide")

daily = load("fct_daily_market_prices")
if daily.empty:
    st.error("Mart exports not found in data/marts/. Run `python -m apple_pricing.pipeline` first.")
    st.stop()

st.title("Apple Product Pricing Intelligence")

with st.sidebar:
    st.header("Filters")
    categories = st.multiselect(
        "Category",
        [c for c in CATEGORY_ORDER if c in set(daily["product_category"])],
        default=[c for c in CATEGORY_ORDER if c in set(daily["product_category"])],
    )
    platforms = st.multiselect("Platform", sorted(daily["platform"].unique()), default=sorted(daily["platform"].unique()))
    conditions = st.multiselect("Condition", sorted(daily["condition"].unique()), default=sorted(daily["condition"].unique()))
    minimum, maximum = daily["price_date"].min().date(), daily["price_date"].max().date()
    date_range = st.date_input("Date range", value=(minimum, maximum), min_value=minimum, max_value=maximum)
    st.caption("Filters apply wherever the underlying table has the column.")

filters = {
    "categories": categories or CATEGORY_ORDER,
    "platforms": platforms,
    "conditions": conditions,
    "date_range": date_range if isinstance(date_range, tuple) and len(date_range) == 2 else (minimum, maximum),
}
filters["date_range"] = tuple(pd.Timestamp(d) for d in filters["date_range"])

tabs = st.tabs(
    [
        "Overview",
        "Price Explorer",
        "Depreciation & Launches",
        "Sale Events",
        "Platforms & Condition",
        "Forecasts",
        "Buy or Wait",
        "AI Analyst",
        "Data & Pipeline",
    ]
)

with tabs[0]:
    views.overview(filters)
with tabs[1]:
    views.price_explorer(filters)
with tabs[2]:
    views.depreciation(filters)
with tabs[3]:
    views.sale_events(filters)
with tabs[4]:
    views.platforms(filters)
with tabs[5]:
    views.forecasts(filters)
with tabs[6]:
    views.buy_or_wait(filters)
with tabs[7]:
    views.analyst()
with tabs[8]:
    views.data_pipeline()
