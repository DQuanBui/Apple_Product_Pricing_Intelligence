"""Apple Product Pricing Intelligence - Streamlit dashboard.

Reads the Parquet exports of the dbt marts in data/marts/ (rebuild them with
`python -m apple_pricing.pipeline`).
"""

import streamlit as st

from dashboard import theme, views
from dashboard.data import load

st.set_page_config(
    page_title="Apple Pricing Intelligence",
    page_icon="🍎",
    layout="wide",
    initial_sidebar_state="collapsed",
)
theme.apply()
st.logo("assets/logo.svg", size="large")

if load("fct_daily_market_prices").empty:
    st.error("The data marts are missing from data/marts/. Run `python -m apple_pricing.pipeline` to build them.")
    st.stop()

pages = [
    st.Page(views.overview, title="Overview", url_path="overview", default=True),
    st.Page(views.price_explorer, title="Price explorer", url_path="explorer"),
    st.Page(views.life_cycle, title="Life cycle", url_path="life-cycle"),
    st.Page(views.sale_events, title="Sale events", url_path="sale-events"),
    st.Page(views.marketplaces, title="Marketplaces", url_path="marketplaces"),
    st.Page(views.forecasts, title="Forecasts", url_path="forecasts"),
    st.Page(views.buy_or_wait, title="Buy or wait", url_path="buy-or-wait"),
    st.Page(views.analyst, title="Ask the data", url_path="ask"),
    st.Page(views.about, title="About", url_path="about"),
]
st.navigation(pages, position="top").run()
