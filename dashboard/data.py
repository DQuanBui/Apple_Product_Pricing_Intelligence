"""Cached loaders for the Parquet mart exports in data/marts/."""

import json
from pathlib import Path

import pandas as pd
import streamlit as st

MARTS_DIR = Path(__file__).resolve().parents[1] / "data" / "marts"


@st.cache_data(show_spinner=False)
def load(name: str) -> pd.DataFrame:
    path = MARTS_DIR / f"{name}.parquet"
    if not path.exists():
        return pd.DataFrame()
    data = pd.read_parquet(path)
    for column in data.columns:
        if column.endswith("date") or column == "price_date":
            data[column] = pd.to_datetime(data[column])
    return data


@st.cache_data(show_spinner=False)
def load_metrics() -> dict:
    path = MARTS_DIR / "model_metrics.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def filter_frame(data: pd.DataFrame, filters: dict) -> pd.DataFrame:
    """Apply the sidebar filters to any frame that has the matching columns."""
    mask = pd.Series(True, index=data.index)
    for column, key in (
        ("product_category", "categories"),
        ("platform", "platforms"),
        ("condition", "conditions"),
    ):
        if column in data.columns and filters.get(key):
            mask &= data[column].isin(filters[key])

    if "price_date" in data.columns and filters.get("date_range"):
        start, end = filters["date_range"]
        mask &= data["price_date"].between(pd.Timestamp(start), pd.Timestamp(end))

    return data.loc[mask]
