"""One render function per dashboard tab."""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard import ai_analyst
from dashboard.data import MARTS_DIR, filter_frame, load, load_metrics
from dashboard.sql_sandbox import TABLE_DESCRIPTIONS, build_connection
from dashboard.theme import (
    AXIS,
    CATEGORY_COLORS,
    CATEGORY_ORDER,
    INK,
    INK_MUTED,
    PLATFORM_COLORS,
    RECOMMENDATION_ICONS,
    SERIES,
    reference_line,
)

CHART_CONFIG = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]}


def show(figure, height: int = 420) -> None:
    figure.update_layout(height=height, legend_title_text="")
    st.plotly_chart(figure, width="stretch", config=CHART_CONFIG)


def data_view(data: pd.DataFrame, label: str = "View data") -> None:
    with st.expander(label):
        st.dataframe(data, width="stretch", hide_index=True)


def weighted_mean(data: pd.DataFrame, value: str, weight: str) -> float:
    return float(np.average(data[value], weights=data[weight])) if len(data) else float("nan")


# --------------------------------------------------------------------------- overview


def overview(filters: dict) -> None:
    products = load("dim_product")
    daily = filter_frame(load("fct_daily_market_prices"), filters)
    successor = load("mart_successor_launch_impact")
    events = load("mart_sale_event_impact")
    gaps = load("mart_platform_price_gap")
    scorecard = load("mart_model_scorecard")
    metrics = load_metrics().get("horizons", {})
    dbt_results = load("dbt_run_results")

    st.markdown(
        "How Apple products are priced on **Amazon** and **Flipkart** from launch to end of life, "
        "what sale events and new launches really do to prices, and whether to **buy now or wait**."
    )

    cols = st.columns(5)
    cols[0].metric("Listing snapshots", f"{int(products['listing_snapshots'].sum()):,}")
    cols[1].metric("Apple models", f"{len(products)}")
    cols[2].metric("Series-days (filtered)", f"{len(daily):,}")
    cols[3].metric(
        "Observation window",
        f"{products['first_observed_date'].min():%b %Y} – {products['last_observed_date'].max():%b %Y}",
    )
    if not dbt_results.empty:
        tests = dbt_results[dbt_results["resource_type"].str.contains("test")]
        passed = (tests["status"].str.lower() == "pass").sum()
        cols[4].metric("dbt data tests passing", f"{passed}/{len(tests)}")

    st.subheader("Key findings")
    by_category = successor.groupby("product_category")["price_change_pct"].mean()
    event_rows = events[events["sale_event"] != "No Event"]
    headline = weighted_mean(event_rows, "avg_discount_vs_msrp_pct", "series_days")
    real = weighted_mean(event_rows, "avg_savings_vs_baseline_pct", "series_days")
    typical_gap = gaps["gap_pct"].abs().mean()
    refurb = scorecard["refurbished_discount_pct"].mean()

    f = st.columns(4)
    f[0].metric(
        "iPhone price after successor launch",
        f"{by_category.get('iPhone', np.nan):.1f}%",
        help="Average change in price index, 60 days before vs the 60 days after the next model is released.",
    )
    f[0].caption(
        f"Watch {by_category.get('Watch', np.nan):.1f}% · iPad {by_category.get('iPad', np.nan):.1f}% · "
        f"Mac {by_category.get('Mac', np.nan):+.1f}%. Prices hold near MSRP until the successor ships, then step down."
    )
    f[1].metric("Real saving during sale events", f"{real:.1f}%", help="Versus the product's normal (non-event) price.")
    f[1].caption(f"The headline discount vs launch MSRP is {headline:.1f}% - most of it existed before the sale.")
    f[2].metric("Typical Amazon vs Flipkart gap", f"{typical_gap:.1f}%")
    f[2].caption(
        f"Neither platform is systematically cheaper (Amazon cheaper on {(gaps['cheaper_platform'] == 'Amazon').mean():.0%} "
        "of matched days), so checking both pays off per purchase."
    )
    f[3].metric("Refurbished vs new, same day", f"-{refurb:.1f}%")
    if metrics:
        seven = metrics["7d"]
        f[3].caption(
            f"7-day forecast MAE ${seven['model']['MAE']:.2f}: {seven['mae_improvement_vs_naive_pct']:.0f}% better than "
            f"last price, {seven['mae_improvement_vs_trailing_30d_pct']:.0f}% better than a 30-day average."
        )

    curve = load("mart_depreciation_curve")
    curve = curve[
        (curve["condition"] == "New") & (curve["models"] >= 2) & (curve["series_days"] >= 60) & curve["product_category"].isin(filters["categories"])
    ]
    figure = px.line(
        curve.sort_values("months_since_release"),
        x="months_since_release",
        y="median_price_index",
        color="product_category",
        color_discrete_map=CATEGORY_COLORS,
        category_orders={"product_category": CATEGORY_ORDER},
        title="Value retention after release (New units)",
        labels={"months_since_release": "Months since release", "median_price_index": "Price index (MSRP = 100)"},
    )
    reference_line(figure, 100, "Launch MSRP")
    show(figure)
    st.caption("Mac depreciates gradually; iPhone, iPad and Watch hold MSRP for about a year, then drop when the next generation launches.")
    data_view(curve)


# --------------------------------------------------------------------------- price explorer


def price_explorer(filters: dict) -> None:
    products = load("dim_product").sort_values(["product_category", "product_line", "release_date"])
    products = products[products["product_category"].isin(filters["categories"])]
    if products.empty:
        st.info("No models match the selected categories.")
        return

    model = st.selectbox("Model", products["model_name"], index=len(products) - 1)
    product = products.set_index("model_name").loc[model]
    daily = filter_frame(load("fct_daily_market_prices"), filters)
    series = daily[daily["model_name"] == model].sort_values("price_date")

    card = load("mart_model_scorecard").set_index("model_name").loc[model]
    cols = st.columns(5)
    cols[0].metric("Launch MSRP", f"${product['msrp_usd']:,.0f}")
    cols[1].metric("Current price (New)", f"${card['current_price_usd']:,.0f}", f"{card['current_price_index'] - 100:.1f}% vs MSRP")
    cols[2].metric("Months since release", f"{card['months_since_release']:.0f}")
    cols[3].metric("Avg. loss per month", f"{card['avg_monthly_depreciation_pts']:.2f} pts")
    cols[4].metric("Refurbished discount", f"{card['refurbished_discount_pct']:.1f}%")

    figure = go.Figure()
    for (platform, condition), part in series.groupby(["platform", "condition"]):
        figure.add_trace(
            go.Scatter(
                x=part["price_date"],
                y=part["median_price_usd"],
                mode="lines",
                name=f"{platform} · {condition}",
                line=dict(color=PLATFORM_COLORS[platform], width=2 if condition == "New" else 1.5,
                          dash="solid" if condition == "New" else "dot"),
                hovertemplate="%{x|%d %b %Y}<br>$%{y:,.2f}<extra>" + f"{platform} · {condition}</extra>",
            )
        )
    events = series[series["is_sale_event"] == 1]
    if not events.empty:
        figure.add_trace(
            go.Scatter(
                x=events["price_date"],
                y=events["median_price_usd"],
                mode="markers",
                name="Sale-event day",
                marker=dict(size=8, color="rgba(0,0,0,0)", line=dict(color=INK, width=1.5)),
                customdata=events[["sale_event", "platform"]],
                hovertemplate="%{customdata[0]} (%{customdata[1]})<br>$%{y:,.2f}<extra></extra>",
            )
        )
    reference_line(figure, product["msrp_usd"], "Launch MSRP")
    if pd.notna(product["successor_release_date"]):
        figure.add_vline(x=product["successor_release_date"], line=dict(color=AXIS, width=1))
        figure.add_annotation(
            x=product["successor_release_date"], y=1, yref="paper", text=f"{product['successor_model_name']} released",
            showarrow=False, xanchor="left", yanchor="top", font=dict(color=INK_MUTED, size=11),
        )
    figure.update_layout(title=f"Daily median price · {model}", yaxis_title="Price (USD)", xaxis_title=None, hovermode="x unified")
    show(figure, 460)
    data_view(series[["price_date", "platform", "condition", "median_price_usd", "listing_count", "sale_event", "price_index"]])


# --------------------------------------------------------------------------- depreciation


def depreciation(filters: dict) -> None:
    condition = st.radio("Condition", ["New", "Refurbished"], horizontal=True)
    curve = load("mart_depreciation_curve")
    curve = curve[
        (curve["condition"] == condition) & (curve["models"] >= 2) & (curve["series_days"] >= 60) & curve["product_category"].isin(filters["categories"])
    ]

    figure = px.line(
        curve.sort_values("months_since_release"),
        x="months_since_release",
        y="median_price_index",
        color="product_category",
        color_discrete_map=CATEGORY_COLORS,
        category_orders={"product_category": CATEGORY_ORDER},
        title=f"Depreciation curve · {condition}",
        labels={"months_since_release": "Months since release", "median_price_index": "Price index (MSRP = 100)"},
    )
    reference_line(figure, 100, "Launch MSRP")
    show(figure)

    st.subheader("The successor-launch cliff")
    impact = load("mart_successor_launch_impact")
    impact = impact[impact["product_category"].isin(filters["categories"])].sort_values("price_change_pct")
    figure = px.bar(
        impact,
        x="price_change_pct",
        y="model_name",
        color="product_category",
        orientation="h",
        color_discrete_map=CATEGORY_COLORS,
        category_orders={"product_category": CATEGORY_ORDER},
        title="Price change in the 60 days after the successor's release vs the 60 days before",
        labels={"price_change_pct": "Change in price index (%)", "model_name": ""},
        hover_data={"successor_model_name": True, "index_60d_before": ":.1f", "index_0_59d_after": ":.1f"},
    )
    figure.update_yaxes(categoryorder="array", categoryarray=impact["model_name"].tolist()[::-1])
    figure.add_vline(x=0, line=dict(color=AXIS, width=1))
    show(figure, 620)
    st.caption(
        "For iPhone and Apple Watch, the best time to buy the previous generation is right after the new one launches. "
        "Mac prices do not react to successor launches - they depreciate steadily instead."
    )
    data_view(impact)


# --------------------------------------------------------------------------- sale events


def sale_events(filters: dict) -> None:
    events = load("mart_sale_event_impact")
    events = events[events["product_category"].isin(filters["categories"])]
    summary = (
        events.groupby("sale_event")
        .apply(
            lambda g: pd.Series(
                {
                    "series_days": g["series_days"].sum(),
                    "Headline discount vs launch MSRP": weighted_mean(g, "avg_discount_vs_msrp_pct", "series_days"),
                    "Real saving vs normal price": weighted_mean(g, "avg_savings_vs_baseline_pct", "series_days"),
                    "Days saving 5%+": weighted_mean(g, "pct_days_saving_5pct_plus", "series_days"),
                }
            ),
            include_groups=False,
        )
        .reset_index()
        .sort_values("Real saving vs normal price", ascending=False)
    )

    event_summary = summary[summary["sale_event"] != "No Event"]
    long = event_summary.melt(
        id_vars="sale_event",
        value_vars=["Headline discount vs launch MSRP", "Real saving vs normal price"],
        var_name="measure",
        value_name="pct",
    )
    figure = px.bar(
        long,
        x="sale_event",
        y="pct",
        color="measure",
        barmode="group",
        color_discrete_sequence=SERIES,
        text=long["pct"].map("{:.1f}%".format),
        title="Headline discount vs what a buyer actually saves",
        labels={"sale_event": "", "pct": "%"},
    )
    figure.update_traces(textposition="outside", textfont=dict(color=INK, size=12), cliponaxis=False)
    show(figure)
    st.caption(
        "The headline discount compares against launch MSRP, so it includes normal depreciation. "
        "Measured against each product's recent non-event price, Big Billion Days gives the biggest real saving "
        "and Black Friday the smallest - but on almost every event day the saving is at least 5%."
    )
    st.dataframe(summary.round(2), width="stretch", hide_index=True)

    st.subheader("By category")
    pivot = events[events["sale_event"] != "No Event"].pivot_table(
        index="sale_event", columns="product_category", values="avg_savings_vs_baseline_pct"
    )
    st.dataframe(pivot.round(1), width="stretch")


# --------------------------------------------------------------------------- platforms & condition


def platforms(filters: dict) -> None:
    gaps = filter_frame(load("mart_platform_price_gap"), filters)
    if gaps.empty:
        st.info("No matched Amazon / Flipkart days for this selection.")
        return

    cols = st.columns(4)
    cols[0].metric("Matched product-days", f"{len(gaps):,}")
    cols[1].metric("Amazon cheaper", f"{(gaps['cheaper_platform'] == 'Amazon').mean():.1%}")
    cols[2].metric("Median gap (Amazon − Flipkart)", f"{gaps['gap_pct'].median():+.2f}%")
    cols[3].metric("Mean absolute gap", f"{gaps['gap_pct'].abs().mean():.2f}%")

    figure = px.histogram(
        gaps.assign(gap_pct=gaps["gap_pct"].clip(-15, 15)),
        x="gap_pct",
        nbins=60,
        color_discrete_sequence=SERIES[:1],
        title="Same product, same day: Amazon price relative to Flipkart",
        labels={"gap_pct": "Amazon vs Flipkart (%) · negative = Amazon cheaper"},
    )
    figure.add_vline(x=0, line=dict(color=INK_MUTED, width=1))
    figure.update_layout(yaxis_title="Matched product-days", bargap=0.08)
    show(figure)
    st.caption(
        "The distribution is centred on zero (a Wilcoxon signed-rank test finds no significant difference), "
        "but individual days differ by a few percent either way - the practical advice is to compare both before buying."
    )

    scorecard = load("mart_model_scorecard")
    scorecard = scorecard[scorecard["product_category"].isin(filters["categories"])].sort_values("refurbished_discount_pct")
    figure = px.bar(
        scorecard,
        x="refurbished_discount_pct",
        y="model_name",
        orientation="h",
        color="product_category",
        color_discrete_map=CATEGORY_COLORS,
        category_orders={"product_category": CATEGORY_ORDER},
        title="Refurbished discount vs a new unit on the same platform and day",
        labels={"refurbished_discount_pct": "Discount (%)", "model_name": ""},
    )
    figure.update_yaxes(categoryorder="array", categoryarray=scorecard["model_name"].tolist())
    show(figure, 700)
    data_view(scorecard[["model_name", "product_category", "refurbished_discount_pct", "pct_days_amazon_cheaper", "avg_amazon_vs_flipkart_pct"]])


# --------------------------------------------------------------------------- forecasts


def forecasts(filters: dict) -> None:
    metrics = load_metrics()
    horizons = metrics.get("horizons", {})
    if not horizons:
        st.warning("Model metrics not found. Run `python -m apple_pricing.pipeline`.")
        return

    cols = st.columns(len(horizons) * 2)
    for index, (name, m) in enumerate(horizons.items()):
        cols[index * 2].metric(
            f"{name} MAE", f"${m['model']['MAE']:.2f}",
            f"{-m['mae_improvement_vs_trailing_30d_pct']:.1f}% vs 30-day avg", delta_color="inverse",
        )
        cols[index * 2 + 1].metric(
            f"{name} P10–P90 coverage", f"{m['p10_p90_interval_coverage_pct']:.1f}%",
            help="Share of test outcomes inside the calibrated 80% interval.",
        )

    comparison = pd.DataFrame(
        [
            {
                "Horizon": name,
                "CatBoost (P50)": m["model"]["MAE"],
                "Trailing 30-day mean": m["baseline_trailing_30d_mean"]["MAE"],
                "Naive last price": m["baseline_naive_last_price"]["MAE"],
                "WAPE %": m["model"]["WAPE_pct"],
                "vs naive": f"{m['mae_improvement_vs_naive_pct']:.1f}% better",
                "vs 30-day mean": f"{m['mae_improvement_vs_trailing_30d_pct']:.1f}% better",
                "Test window": f"{m['split']['test_start']} → {m['split']['test_end']}",
            }
            for name, m in horizons.items()
        ]
    )
    long = comparison.melt(
        id_vars="Horizon", value_vars=["CatBoost (P50)", "Trailing 30-day mean", "Naive last price"],
        var_name="Method", value_name="MAE",
    )
    figure = px.bar(
        long, x="Horizon", y="MAE", color="Method", barmode="group", color_discrete_sequence=SERIES,
        text=long["MAE"].map("${:.2f}".format),
        title="Out-of-sample MAE on the last 180 days (lower is better)", labels={"MAE": "MAE (USD)"},
    )
    figure.update_traces(textposition="outside", textfont=dict(color=INK, size=12), cliponaxis=False)
    show(figure, 380)
    st.dataframe(comparison.round(2), width="stretch", hide_index=True)

    st.subheader("Backtest for one series")
    backtest = filter_frame(load("mart_forecast_backtest"), filters)
    if backtest.empty:
        return
    c1, c2, c3, c4 = st.columns([1, 3, 2, 2])
    horizon = c1.radio("Horizon", sorted(backtest["horizon_days"].unique()), format_func=lambda h: f"{h} days")
    model = c2.selectbox("Model", sorted(backtest["model_name"].unique()), key="backtest_model")
    platform = c3.selectbox("Platform", sorted(backtest["platform"].unique()), key="backtest_platform")
    condition = c4.selectbox("Condition", sorted(backtest["condition"].unique()), key="backtest_condition")
    part = backtest[
        (backtest["horizon_days"] == horizon) & (backtest["model_name"] == model)
        & (backtest["platform"] == platform) & (backtest["condition"] == condition)
    ].sort_values("price_date")
    if part.empty:
        st.info("No test-period rows for this series.")
        return

    target_date = part["price_date"] + pd.Timedelta(days=int(horizon))
    figure = go.Figure(
        [
            go.Scatter(x=target_date, y=part["pred_p90_usd"], mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"),
            go.Scatter(
                x=target_date, y=part["pred_p10_usd"], mode="lines", line=dict(width=0), fill="tonexty",
                fillcolor="rgba(42,120,214,0.15)", name="P10–P90 range", hoverinfo="skip",
            ),
            go.Scatter(x=target_date, y=part["pred_p50_usd"], mode="lines", name="Forecast (P50)", line=dict(color=SERIES[0])),
            go.Scatter(
                x=target_date, y=part["actual_price_usd"], mode="markers", name="Actual",
                marker=dict(size=6, color=INK), hovertemplate="%{x|%d %b %Y}<br>Actual $%{y:,.2f}<extra></extra>",
            ),
        ]
    )
    figure.update_layout(
        title=f"{horizon}-day-ahead forecast vs actual · {platform} · {model} · {condition}",
        yaxis_title="Price (USD)", hovermode="x unified",
    )
    show(figure)

    name = f"{horizon}d"
    importance = pd.Series(horizons[name]["top_features"]).sort_values().tail(12)
    figure = px.bar(
        x=importance.values, y=importance.index, orientation="h", color_discrete_sequence=SERIES[:1],
        title=f"Top features · {name} model (CatBoost importance)", labels={"x": "Importance", "y": ""},
    )
    show(figure, 420)
    st.caption("Calendar features (week of year, month) dominate: sale seasons and the September launch cycle drive most price moves.")


# --------------------------------------------------------------------------- buy or wait


def buy_or_wait(filters: dict) -> None:
    deals = filter_frame(load("mart_deal_scores"), filters)
    if deals.empty:
        st.info("No series match the filters.")
        return

    counts = deals["recommendation"].value_counts()
    cols = st.columns(3)
    for column, label in zip(cols, ["Buy now", "Wait", "No rush"]):
        column.metric(RECOMMENDATION_ICONS[label], f"{counts.get(label, 0)} series")

    choice = st.multiselect("Show", ["Buy now", "Wait", "No rush"], default=["Buy now", "Wait"])
    view = deals[deals["recommendation"].isin(choice)].sort_values("deal_score", ascending=False)
    view = view.assign(recommendation=view["recommendation"].map(RECOMMENDATION_ICONS))

    st.dataframe(
        view[
            [
                "recommendation", "model_name", "platform", "condition", "current_price_usd",
                "discount_vs_normal_pct", "forecast_7d_usd", "forecast_30d_usd", "forecast_30d_p10_usd",
                "forecast_30d_p90_usd", "expected_saving_if_wait_30d_usd", "recommendation_reason", "deal_score", "as_of_date",
            ]
        ],
        width="stretch",
        hide_index=True,
        column_config={
            "recommendation": "Call",
            "model_name": "Model",
            "current_price_usd": st.column_config.NumberColumn("Price", format="$%.0f"),
            "discount_vs_normal_pct": st.column_config.NumberColumn("vs normal price", format="%.1f%%"),
            "forecast_7d_usd": st.column_config.NumberColumn("7-day forecast", format="$%.0f"),
            "forecast_30d_usd": st.column_config.NumberColumn("30-day forecast", format="$%.0f"),
            "forecast_30d_p10_usd": st.column_config.NumberColumn("30d P10", format="$%.0f"),
            "forecast_30d_p90_usd": st.column_config.NumberColumn("30d P90", format="$%.0f"),
            "expected_saving_if_wait_30d_usd": st.column_config.NumberColumn("Saving if you wait 30d", format="$%.0f"),
            "recommendation_reason": "Why",
            "deal_score": st.column_config.ProgressColumn("Deal score", min_value=0, max_value=100, format="%.0f"),
            "as_of_date": st.column_config.DateColumn("Price as of"),
        },
    )
    with st.expander("How the call is made"):
        st.markdown(
            "- **Buy now** if today's price is below the calibrated 30-day P10, the forecast expects a rise of 2%+, "
            "or the price is 5%+ below its normal (non-event) level.\n"
            "- **Wait** if today's price is above the 30-day P90 or the forecast expects a drop of 3%+.\n"
            "- **Deal score** (0–100) ranks series by expected 30-day change (45%), discount vs normal price (35%), "
            "rating (10%) and in-stock share (10%).\n\n"
            "Rules and weights live in the dbt model `mart_deal_scores`, so they are version-controlled and tested."
        )


# --------------------------------------------------------------------------- AI analyst


@st.cache_resource(show_spinner=False)
def _sandbox():
    return build_connection(MARTS_DIR)


def analyst() -> None:
    st.markdown(
        "Ask a question in plain English. Claude writes read-only SQL against the dbt marts, runs it in a sandboxed "
        "in-memory DuckDB, and answers with the numbers it found. Every query it ran is shown below the answer."
    )
    api_key = ai_analyst.get_api_key(st.secrets)
    examples = [
        "Which iPhone lost the most value in the 60 days after its successor launched?",
        "Which sale event saves the most on Macs compared with the normal price?",
        "Top 5 'Buy now' deals under $500 and why",
        "How accurate is the 30-day forecast for Watches compared with the naive baseline?",
    ]
    st.caption("Try: " + " · ".join(f"*{e}*" for e in examples))

    if not api_key:
        st.info("Add `ANTHROPIC_API_KEY` to the app's Streamlit secrets (or environment) to enable the analyst.")
        return

    history = st.session_state.setdefault("analyst_history", [])
    for turn in history:
        with st.chat_message(turn["role"]):
            st.markdown(turn["content"])
            for sql, outcome in turn.get("queries", []):
                with st.expander(f"SQL · {outcome}"):
                    st.code(sql, language="sql")

    question = st.chat_input("Ask about prices, events, depreciation or forecasts")
    if not question:
        return

    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.spinner("Querying the marts..."):
            api_history = [{"role": t["role"], "content": t["content"]} for t in history]
            try:
                result = ai_analyst.ask(question, api_history, _sandbox(), api_key)
            except Exception as error:
                st.error(ai_analyst.describe_error(error))
                return
        st.markdown(result["answer"])
        for sql, outcome in result["queries"]:
            with st.expander(f"SQL · {outcome}"):
                st.code(sql, language="sql")

    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": result["answer"], "queries": result["queries"]})


# --------------------------------------------------------------------------- data & pipeline


PIPELINE_DOT = """
digraph {
  rankdir=LR; bgcolor="transparent";
  node [shape=box, style="rounded,filled", fillcolor="#fcfcfb", color="#c3c2b7", fontname="Helvetica", fontsize=11, fontcolor="#0b0b0b"];
  edge [color="#898781", arrowsize=0.7];
  csv [label="Kaggle CSV\\n80K listings"];
  s3 [label="AWS S3\\nParquet, year= partitions"];
  sf [label="Snowflake RAW\\n(COPY INTO)\\nDuckDB locally"];
  dbt [label="dbt\\nstaging → star schema\\n→ analytics marts\\n78 tested nodes"];
  ml [label="Python / CatBoost\\n7 & 30-day P10–P90\\nforecasts"];
  deals [label="dbt ML marts\\ndeal scores, backtest"];
  app [label="Streamlit\\n+ Claude SQL analyst"];
  bi [label="Power BI\\n(Snowflake marts)"];
  csv -> s3 -> sf -> dbt -> ml -> deals;
  dbt -> app; deals -> app; dbt -> bi; deals -> bi;
}
"""


def data_pipeline() -> None:
    st.graphviz_chart(PIPELINE_DOT, width="stretch")

    results = load("dbt_run_results")
    if not results.empty:
        st.subheader("Latest dbt build")
        results = results.assign(resource_type=results["resource_type"].str.replace("NodeType.", "", regex=False).str.lower())
        summary = results.groupby(["resource_type", "status"]).size().unstack(fill_value=0)
        st.dataframe(summary, width="stretch")
        with st.expander("All dbt nodes"):
            st.dataframe(results, width="stretch", hide_index=True)

    st.subheader("Data marts")
    st.dataframe(
        pd.DataFrame(
            [
                {"table": name, "rows": len(load(name)), "description": description}
                for name, description in TABLE_DESCRIPTIONS.items()
            ]
        ),
        width="stretch",
        hide_index=True,
    )
    st.caption(
        "Source: public Kaggle dataset of Amazon and Flipkart listings (Sep 2020 – Jul 2026, USD). "
        "Parts of the data look simulated (for example, ratings are uncorrelated with review counts and Amazon is "
        "cheaper on almost exactly half of matched days), so findings describe this dataset; the pipeline itself runs "
        "unchanged on scraped data."
    )
