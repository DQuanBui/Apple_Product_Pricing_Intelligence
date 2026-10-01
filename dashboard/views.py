"""Dashboard pages. Each page leads with its finding, then the charts that carry it."""

import html

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard import ai_analyst
from dashboard.data import MARTS_DIR, load, load_metrics
from dashboard.sql_sandbox import TABLE_DESCRIPTIONS, build_connection
from dashboard.theme import (
    ACCENT,
    AXIS,
    CATEGORY_COLORS,
    CATEGORY_ORDER,
    INK,
    INK_MUTED,
    PLATFORM_COLORS,
    RULE,
    SEQUENTIAL_BLUE,
    STATUS,
    reference_line,
)

REPO_URL = "https://github.com/DQuanBui/Apple_Product_Pricing_Intelligence"
REPORT_URL = f"{REPO_URL}/blob/main/reports/final_report.pdf"
CHART_CONFIG = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"]}
LIGHT_GRAY, MID_GRAY = "#C9D0DA", "#8C96A6"


# --------------------------------------------------------------------------- layout helpers


def page_header(title: str, lead: str) -> None:
    st.markdown(f'<h1 class="pg-title">{title}</h1><p class="pg-lead">{lead}</p>', unsafe_allow_html=True)


def section(title: str, lead: str | None = None) -> None:
    body = f'<h2 class="sec-title">{title}</h2>'
    if lead:
        body += f'<p class="sec-lead">{lead}</p>'
    st.markdown(body, unsafe_allow_html=True)


def stat_band(items: list[tuple[str, str, str | None]]) -> None:
    cells = "".join(
        f'<div class="stat"><div class="stat-value">{value}</div><div class="stat-label">{label}</div>'
        + (f'<div class="stat-context">{context}</div>' if context else "")
        + "</div>"
        for value, label, context in items
    )
    st.markdown(f'<div class="stat-band" style="--n:{len(items)}">{cells}</div>', unsafe_allow_html=True)


def show(figure, height: int = 380) -> None:
    figure.update_layout(height=height)
    st.plotly_chart(figure, width="stretch", config=CHART_CONFIG)


def chart_card(title: str, note: str | None, figure, height: int = 360) -> None:
    with st.container(border=True):
        st.markdown(
            f'<div class="card-title">{title}</div>' + (f'<p class="card-note">{note}</p>' if note else ""),
            unsafe_allow_html=True,
        )
        show(figure, height)


def category_filter(key: str) -> list[str]:
    chosen = st.pills("Category", CATEGORY_ORDER, selection_mode="multi", default=CATEGORY_ORDER, key=key)
    return chosen or CATEGORY_ORDER


def weighted(data: pd.DataFrame, value: str, weight: str = "series_days") -> float:
    return float(np.average(data[value], weights=data[weight])) if len(data) and data[weight].sum() else float("nan")


def pct(value: float, digits: int = 1, sign: bool = False) -> str:
    text = f"{value:+.{digits}f}%" if sign else f"{value:.{digits}f}%"
    return text.replace("-", "\u2212")


def below_normal(value: float) -> str:
    return f"{abs(value):.1f}% {'below' if value >= 0 else 'above'} its normal price"


def caveat() -> None:
    st.markdown(
        '<p class="caveat">Data: public Kaggle dataset of Amazon and Flipkart listings, September 2020 to July 2026, '
        "prices in USD. Parts of it look simulated, so the effects describe this dataset; the pipeline runs unchanged "
        f'on real scraped prices. <a href="{REPORT_URL}" target="_blank">Read the full report</a>.</p>',
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- cached data shaping


@st.cache_data(show_spinner=False)
def curve(condition: str) -> pd.DataFrame:
    data = load("mart_depreciation_curve")
    data = data[(data["condition"] == condition) & (data["models"] >= 2) & (data["series_days"] >= 60)]
    return data.sort_values("months_since_release")


@st.cache_data(show_spinner=False)
def model_age_matrix() -> pd.DataFrame:
    daily = load("fct_daily_market_prices")
    new = daily[(daily["condition"] == "New") & daily["months_since_release"].between(0, 48)]
    return new.groupby(["model_name", "months_since_release"])["price_index"].median().unstack()


@st.cache_data(show_spinner=False)
def event_by_year() -> pd.DataFrame:
    daily = load("fct_daily_market_prices")
    events = daily[(daily["is_sale_event"] == 1) & daily["savings_vs_baseline_pct"].notna()]
    return events.assign(year=events["price_date"].dt.year).pivot_table(
        index="sale_event", columns="year", values="savings_vs_baseline_pct", aggfunc="mean"
    )


def depreciation_figure(data: pd.DataFrame, categories: list[str], annotate: bool = False) -> go.Figure:
    figure = go.Figure()
    for category in [c for c in CATEGORY_ORDER if c in categories]:
        part = data[data["product_category"] == category]
        figure.add_trace(
            go.Scatter(
                x=part["months_since_release"], y=part["median_price_index"], mode="lines", name=category,
                line=dict(color=CATEGORY_COLORS[category], width=2.5, shape="linear"),
                hovertemplate=f"<b>{category}</b><br>Month %{{x:.0f}} after release<br>%{{y:.1f}}% of launch price<extra></extra>",
            )
        )
    reference_line(figure, 100, "Launch price")
    if annotate:
        for month in (12, 24, 36):
            figure.add_vline(x=month, line=dict(color=RULE, width=1))
        figure.add_annotation(
            x=12, y=103, text="Next generation ships", showarrow=False, xanchor="left", yanchor="bottom",
            xshift=4, font=dict(color=INK_MUTED, size=11),
        )
    figure.update_layout(
        xaxis=dict(title="Months since release", dtick=12, range=[0, 58]),
        yaxis=dict(title="Price, % of launch price", range=[50, 108]),
        hovermode="x unified",
    )
    return figure


# --------------------------------------------------------------------------- 1. Overview


def overview() -> None:
    successor = load("mart_successor_launch_impact")
    events = load("mart_sale_event_impact")
    gaps = load("mart_platform_price_gap")
    scorecard = load("mart_model_scorecard")
    deals = load("mart_deal_scores")
    dbt_results = load("dbt_run_results")
    metrics = load_metrics().get("horizons", {})

    page_header(
        "Apple prices hold for a year, then drop when the next model ships",
        "What 80,000 Amazon and Flipkart listings for 31 Apple models, from September 2020 to July 2026, "
        "show about launches, sale events, marketplaces and the right time to buy.",
    )

    by_category = successor.groupby("product_category")["price_change_pct"].mean()
    left, right = st.columns([4, 7], gap="large")
    with left:
        st.markdown(
            f'<div class="hero-figure">{pct(by_category.get("iPhone", np.nan), 0)}</div>'
            '<p class="hero-caption">Average fall in a previous-generation iPhone\'s price within 60 days '
            "of its successor's release.</p>"
            f'<div class="hero-figure" style="font-size:2.4rem">{pct(by_category.get("Watch", np.nan), 0)}</div>'
            '<p class="hero-caption">The same drop for Apple Watch, the steepest of the four categories.</p>'
            f'<div class="hero-figure" style="font-size:2.4rem">{pct(by_category.get("Mac", np.nan), 1, sign=True)}</div>'
            '<p class="hero-caption">Mac barely reacts to launches; it loses value gradually instead.</p>',
            unsafe_allow_html=True,
        )
    with right:
        with st.container(border=True):
            st.markdown(
                '<div class="card-title">Value retention after release, new units</div>'
                '<p class="card-note">Median price as a share of launch price. Each step lines up with a new generation.</p>',
                unsafe_allow_html=True,
            )
            show(depreciation_figure(curve("New"), CATEGORY_ORDER, annotate=True), 400)

    tests = dbt_results[dbt_results["resource_type"].str.contains("test")] if not dbt_results.empty else pd.DataFrame()
    passed = int((tests["status"].str.lower() == "pass").sum()) if len(tests) else 0
    seven = metrics.get("7d", {})
    stat_band(
        [
            ("80,000", "listing snapshots", "Amazon and Flipkart"),
            ("31", "Apple models", "iPhone, iPad, Mac, Watch"),
            ("124", "price series tracked", "model, platform and condition"),
            (f"{passed} / {len(tests)}", "automated data checks passing", "dbt tests on every build"),
            (f"{seven.get('model', {}).get('WAPE_pct', float('nan')):.1f}%", "7-day forecast error", "share of price, unseen data"),
        ]
    )

    section("What the data shows", "Four findings, each measured on matched or controlled comparisons rather than raw averages.")
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        data = successor.groupby("product_category", as_index=False)["price_change_pct"].mean()
        data = data.set_index("product_category").loc[[c for c in CATEGORY_ORDER if c in data["product_category"].values]].reset_index()
        figure = go.Figure(
            go.Bar(
                x=data["price_change_pct"], y=data["product_category"], orientation="h",
                marker_color=[CATEGORY_COLORS[c] for c in data["product_category"]],
                text=[pct(v, 1) for v in data["price_change_pct"]], textposition="outside",
                textfont=dict(color=INK, size=12), cliponaxis=False,
                hovertemplate="%{y}: %{x:.1f}%<extra></extra>",
            )
        )
        figure.update_layout(xaxis=dict(title="Price change, 60 days after vs 60 days before", range=[-26, 4]), yaxis=dict(autorange="reversed"), margin=dict(t=10))
        chart_card("A new launch cuts the old model's price", "Average across the 21 models with a tracked successor.", figure, 260)
    with c2:
        rows = events[events["sale_event"] != "No Event"]
        summary = rows.groupby("sale_event").apply(
            lambda g: pd.Series({"advertised": weighted(g, "avg_discount_vs_msrp_pct"), "real": weighted(g, "avg_savings_vs_baseline_pct")}),
            include_groups=False,
        ).sort_values("real")
        chart_card(
            "Sale events save less than they advertise",
            "Discount vs launch price compared with the saving vs each product's normal price.",
            dumbbell_figure(summary), 260,
        )
    c3, c4 = st.columns(2, gap="medium")
    with c3:
        figure = go.Figure(
            go.Histogram(
                x=gaps.loc[gaps["gap_pct"].between(-12, 12), "gap_pct"], xbins=dict(start=-12, end=12, size=0.5),
                marker=dict(color=ACCENT, line=dict(width=0)), hovertemplate="%{x}%: %{y:,} days<extra></extra>",
            )
        )
        figure.add_vline(x=0, line=dict(color=INK, width=1))
        figure.update_layout(xaxis=dict(title="Amazon price vs Flipkart, same product and day (%)"), yaxis=dict(title="Days"), bargap=0.05, margin=dict(t=10))
        chart_card(
            "Neither marketplace is cheaper overall",
            f"Amazon is cheaper on {(gaps['cheaper_platform'] == 'Amazon').mean():.1%} of {len(gaps):,} matched days, "
            f"but the two differ by {gaps['gap_pct'].abs().mean():.1f}% on a typical day.",
            figure, 260,
        )
    with c4:
        refurb = scorecard.groupby("product_category", as_index=False)["refurbished_discount_pct"].mean()
        refurb = refurb.set_index("product_category").loc[CATEGORY_ORDER].reset_index()
        figure = go.Figure(
            go.Bar(
                x=refurb["product_category"], y=refurb["refurbished_discount_pct"],
                marker_color=[CATEGORY_COLORS[c] for c in refurb["product_category"]],
                text=[pct(v) for v in refurb["refurbished_discount_pct"]], textposition="outside",
                textfont=dict(color=INK, size=12), cliponaxis=False, hovertemplate="%{x}: %{y:.1f}%<extra></extra>",
            )
        )
        figure.update_layout(yaxis=dict(title="Discount vs new (%)", range=[0, 28]), margin=dict(t=10))
        chart_card("Refurbished units are about 22% cheaper", "Same model, same platform, same day.", figure, 260)

    section("Best deals right now", "Series whose price sits below its forecast range or its normal level. The full list is on Buy or wait.")
    deal_tiles(deals[deals["recommendation"] == "Buy now"].nlargest(4, "deal_score"))
    caveat()


def dumbbell_figure(summary: pd.DataFrame) -> go.Figure:
    figure = go.Figure()
    for event, row in summary.iterrows():
        figure.add_trace(
            go.Scatter(x=[row["real"], row["advertised"]], y=[event, event], mode="lines",
                       line=dict(color=LIGHT_GRAY, width=3), showlegend=False, hoverinfo="skip")
        )
    figure.add_trace(
        go.Scatter(
            x=summary["advertised"], y=summary.index, mode="markers+text", name="Advertised (vs launch price)",
            marker=dict(size=13, color=SURFACE_WHITE, line=dict(color=MID_GRAY, width=2.5)),
            text=[pct(v) for v in summary["advertised"]], textposition="middle right", textfont=dict(color=INK_MUTED, size=11),
            hovertemplate="%{y}<br>Advertised: %{x:.1f}%<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=summary["real"], y=summary.index, mode="markers+text", name="Real saving (vs normal price)",
            marker=dict(size=13, color=INK), text=[pct(v) for v in summary["real"]], textposition="middle left",
            textfont=dict(color=INK, size=11), hovertemplate="%{y}<br>Real saving: %{x:.1f}%<extra></extra>",
        )
    )
    figure.update_layout(xaxis=dict(title="Saving (%)", range=[8, 46]), margin=dict(t=30))
    return figure


SURFACE_WHITE = "#FFFFFF"


def deal_tiles(rows: pd.DataFrame) -> None:
    if rows.empty:
        st.info("No series match these filters.")
        return
    columns = st.columns(len(rows), gap="medium")
    for column, (_, row) in zip(columns, rows.iterrows()):
        call = row["recommendation"]
        column.markdown(
            f'<div class="deal"><span class="deal-call" style="background:{STATUS[call]}">{call}</span>'
            f'<div class="deal-model">{html.escape(row["model_name"])}</div>'
            f'<div class="deal-meta">{row["condition"]} on {row["platform"]}</div>'
            f'<div class="deal-price">${row["current_price_usd"]:,.0f}</div>'
            f'<div class="deal-range">30-day range ${row["forecast_30d_p10_usd"]:,.0f} to ${row["forecast_30d_p90_usd"]:,.0f}</div>'
            f'<div class="deal-why">{html.escape(row["recommendation_reason"])}. '
            f'Now {below_normal(row["discount_vs_normal_pct"])}.</div></div>',
            unsafe_allow_html=True,
        )


# --------------------------------------------------------------------------- 2. Price explorer


def price_explorer() -> None:
    products = load("dim_product").sort_values(["product_category", "product_line", "release_date"])
    daily = load("fct_daily_market_prices")
    scorecard = load("mart_model_scorecard").set_index("model_name")

    page_header("Price explorer", "Follow any model from launch day to today, on both marketplaces, new and refurbished.")

    names = products["model_name"].tolist()
    c1, c2, c3 = st.columns([3, 2, 2], gap="medium")
    model = c1.selectbox("Model", names, index=names.index("iPhone 16 Pro 256GB") if "iPhone 16 Pro 256GB" in names else 0)
    condition = c2.segmented_control("Condition", ["New", "Refurbished", "Both"], default="New") or "New"
    platforms = c3.pills("Platform", ["Amazon", "Flipkart"], selection_mode="multi", default=["Amazon", "Flipkart"]) or ["Amazon", "Flipkart"]

    product = products.set_index("model_name").loc[model]
    card = scorecard.loc[model]
    stat_band(
        [
            (f"${product['msrp_usd']:,.0f}", "launch price", f"released {product['release_date']:%b %Y}"),
            (f"${card['current_price_usd']:,.0f}", "current price, new", "median of the last 30 days"),
            (pct(card["current_price_index"] - 100, 1, sign=True), "vs launch price", None),
            (f"{card['avg_monthly_depreciation_pts']:.2f}", "points lost per month", "price index, on average"),
            (pct(card["refurbished_discount_pct"]), "refurbished discount", "same platform and day"),
            (product["successor_model_name"] if pd.notna(product["successor_model_name"]) else "None yet", "successor", None),
        ]
    )

    series = daily[(daily["model_name"] == model) & daily["platform"].isin(platforms)]
    if condition != "Both":
        series = series[series["condition"] == condition]
    series = series.sort_values("price_date")

    figure = go.Figure()
    for (platform, cond), part in series.groupby(["platform", "condition"]):
        figure.add_trace(
            go.Scatter(
                x=part["price_date"], y=part["median_price_usd"], mode="lines", name=f"{platform}, {cond.lower()}",
                line=dict(color=PLATFORM_COLORS[platform], width=2 if cond == "New" else 1.5, dash="solid" if cond == "New" else "dot"),
                hovertemplate="%{x|%d %b %Y}: $%{y:,.0f}<extra>" + f"{platform}, {cond.lower()}</extra>",
            )
        )
    events = series[series["is_sale_event"] == 1]
    if not events.empty:
        figure.add_trace(
            go.Scatter(
                x=events["price_date"], y=events["median_price_usd"], mode="markers", name="Sale-event day",
                marker=dict(size=7, color="rgba(0,0,0,0)", line=dict(color=INK, width=1.2)),
                customdata=events[["sale_event"]], hovertemplate="%{customdata[0]}: $%{y:,.0f}<extra></extra>",
            )
        )
    reference_line(figure, product["msrp_usd"], "Launch price")
    if pd.notna(product["successor_release_date"]):
        figure.add_vline(x=product["successor_release_date"], line=dict(color=AXIS, width=1))
        figure.add_annotation(
            x=product["successor_release_date"], y=1, yref="paper", text=f"{product['successor_model_name']} released",
            showarrow=False, xanchor="left", yanchor="top", xshift=4, font=dict(color=INK_MUTED, size=11),
        )
    figure.update_layout(yaxis=dict(title="Daily median price (USD)", tickprefix="$"), hovermode="x unified")
    chart_card(f"{model}: daily price", "Circles mark sale-event days.", figure, 430)

    c1, c2 = st.columns(2, gap="medium")
    with c1:
        new = daily[daily["condition"] == "New"]
        monthly = (
            new.assign(month=new["price_date"].dt.to_period("M").dt.to_timestamp())
            .pipe(lambda d: pd.concat([
                d[d["model_name"] == model].groupby("month")["price_index"].mean().rename(model),
                d[d["product_category"] == product["product_category"]].groupby("month")["price_index"].mean().rename(f"All {product['product_category']} models"),
            ], axis=1))
            .dropna(subset=[model])
        )
        figure = go.Figure(
            [
                go.Scatter(x=monthly.index, y=monthly.iloc[:, 1], name=monthly.columns[1], line=dict(color=LIGHT_GRAY, width=2)),
                go.Scatter(x=monthly.index, y=monthly.iloc[:, 0], name=model, line=dict(color=CATEGORY_COLORS[product["product_category"]], width=2.5)),
            ]
        )
        reference_line(figure, 100, "Launch price")
        figure.update_layout(yaxis=dict(title="% of launch price"), hovermode="x unified")
        chart_card("Against its category", "Monthly average price index, new units.", figure, 320)
    with c2:
        model_rows = daily[(daily["model_name"] == model) & daily["savings_vs_baseline_pct"].notna() & (daily["is_sale_event"] == 1)]
        by_event = model_rows.groupby("sale_event")["savings_vs_baseline_pct"].mean().sort_values()
        figure = go.Figure(
            go.Bar(
                x=by_event.values, y=by_event.index, orientation="h", marker_color=INK,
                text=[pct(v) for v in by_event.values], textposition="outside", textfont=dict(color=INK, size=12), cliponaxis=False,
                hovertemplate="%{y}: %{x:.1f}% below normal<extra></extra>",
            )
        )
        figure.update_layout(xaxis=dict(title="Saving vs normal price (%)", range=[0, max(30, by_event.max() * 1.25) if len(by_event) else 30]))
        chart_card("What each sale event saved on this model", "Average saving vs the model's recent non-event price.", figure, 320)


# --------------------------------------------------------------------------- 3. Life cycle


def life_cycle() -> None:
    successor = load("mart_successor_launch_impact")
    products = load("dim_product")

    page_header(
        "Life cycle and launches",
        "Prices fall in steps at each new generation and settle near 60% of launch price after about three years. "
        "Mac is the exception: smaller steps and slower decline.",
    )
    categories = category_filter("life_categories")

    c1, c2 = st.columns(2, gap="medium")
    with c1:
        chart_card("New units", "Median price as a share of launch price.", depreciation_figure(curve("New"), categories), 330)
    with c2:
        chart_card("Refurbished units", "Starts about 22 points lower and follows the same steps.", depreciation_figure(curve("Refurbished"), categories), 330)

    matrix = model_age_matrix()
    order = products[products["product_category"].isin(categories)].sort_values(["product_category", "release_date"])
    order = order.assign(rank=pd.Categorical(order["product_category"], CATEGORY_ORDER)).sort_values(["rank", "release_date"])
    matrix = matrix.reindex([m for m in order["model_name"] if m in matrix.index])
    figure = go.Figure(
        go.Heatmap(
            z=matrix.values, x=matrix.columns, y=matrix.index, zmin=55, zmax=102,
            colorscale=[[i / (len(SEQUENTIAL_BLUE) - 1), c] for i, c in enumerate(SEQUENTIAL_BLUE)],
            colorbar=dict(title=dict(text="% of launch", font=dict(size=11, color=INK_MUTED)), thickness=10, tickfont=dict(color=INK_MUTED)),
            hovertemplate="%{y}<br>Month %{x:.0f}: %{z:.1f}% of launch price<extra></extra>", xgap=1, ygap=1,
        )
    )
    figure.update_layout(xaxis=dict(title="Months since release", dtick=6, gridcolor="rgba(0,0,0,0)"), yaxis=dict(autorange="reversed", gridcolor="rgba(0,0,0,0)"), margin=dict(t=10))
    chart_card(
        "Every model, month by month",
        "Each row is one model (new units), each cell its median price that month. Dark means close to launch price; the colour breaks line up with each new generation.",
        figure, max(320, 24 * len(matrix) + 90),
    )

    data = successor[successor["product_category"].isin(categories)].sort_values("price_change_pct")
    figure = go.Figure(
        go.Bar(
            x=data["price_change_pct"], y=data["model_name"], orientation="h",
            marker_color=[CATEGORY_COLORS[c] for c in data["product_category"]],
            customdata=data[["successor_model_name", "index_60d_before", "index_0_59d_after"]],
            hovertemplate="<b>%{y}</b><br>Successor: %{customdata[0]}<br>%{customdata[1]:.1f}% → %{customdata[2]:.1f}% of launch price<br>Change %{x:.1f}%<extra></extra>",
        )
    )
    figure.add_vline(x=0, line=dict(color=INK, width=1))
    figure.update_layout(yaxis=dict(autorange="reversed"), xaxis=dict(title="Price change, 60 days after vs 60 days before"), margin=dict(t=10))
    c1, c2 = st.columns([3, 2], gap="medium")
    with c1:
        chart_card("The drop when the successor ships, by model", "Wilcoxon signed-rank test across 21 models: p = 0.0001.", figure, 560)
    with c2:
        milestones = []
        full = curve("New")
        for category in [c for c in CATEGORY_ORDER if c in categories]:
            part = full[full["product_category"] == category].set_index("months_since_release")["median_price_index"]
            milestones.append(
                {
                    "Category": category,
                    "12 months": part.get(12.0),
                    "24 months": part.get(24.0),
                    "36 months": part.get(36.0),
                    "Below 90%": f"month {int(part[part < 90].index.min())}" if (part < 90).any() else "",
                }
            )
        with st.container(border=True):
            st.markdown('<div class="card-title">Milestones</div><p class="card-note">% of launch price, new units.</p>', unsafe_allow_html=True)
            st.dataframe(
                pd.DataFrame(milestones), hide_index=True, width="stretch",
                column_config={c: st.column_config.NumberColumn(c, format="%.1f") for c in ["12 months", "24 months", "36 months"]},
            )
            st.markdown(
                '<p class="card-note" style="margin-top:.8rem">For iPhone and Watch the best time to buy last year\'s model '
                "is the two months after the new one ships. Mac buyers can ignore launch timing.</p>",
                unsafe_allow_html=True,
            )


# --------------------------------------------------------------------------- 4. Sale events


def sale_events() -> None:
    events = load("mart_sale_event_impact")
    page_header(
        "Sale events",
        "Advertised discounts are measured against launch price, so they include depreciation the product had already taken. "
        "Against each product's normal price, events save 16 to 25%.",
    )
    categories = category_filter("event_categories")
    rows = events[events["product_category"].isin(categories)]
    event_rows = rows[rows["sale_event"] != "No Event"]
    summary = event_rows.groupby("sale_event").apply(
        lambda g: pd.Series(
            {
                "advertised": weighted(g, "avg_discount_vs_msrp_pct"),
                "real": weighted(g, "avg_savings_vs_baseline_pct"),
                "days_5": weighted(g, "pct_days_saving_5pct_plus"),
                "usd": weighted(g, "avg_savings_usd"),
            }
        ),
        include_groups=False,
    ).sort_values("real")
    best = summary["real"].idxmax()
    stat_band(
        [
            (pct(weighted(event_rows, "avg_discount_vs_msrp_pct")), "advertised discount", "vs launch price"),
            (pct(weighted(event_rows, "avg_savings_vs_baseline_pct")), "real saving", "vs the product's normal price"),
            (pct(weighted(event_rows, "pct_days_saving_5pct_plus")), "of event days save 5% or more", None),
            (best, "strongest event", f"{summary.loc[best, 'real']:.1f}% real saving"),
        ]
    )

    c1, c2 = st.columns([3, 2], gap="medium")
    with c1:
        chart_card("Advertised vs real saving, by event", "Hollow: advertised discount. Solid: saving vs normal price.", dumbbell_figure(summary), 330)
    with c2:
        pivot = event_rows.pivot_table(index="sale_event", columns="product_category", values="avg_savings_vs_baseline_pct")
        pivot = pivot.reindex(index=summary.index[::-1], columns=[c for c in CATEGORY_ORDER if c in pivot.columns])
        figure = go.Figure(
            go.Heatmap(
                z=pivot.values, x=pivot.columns, y=pivot.index, colorscale=[[i / (len(SEQUENTIAL_BLUE) - 1), c] for i, c in enumerate(SEQUENTIAL_BLUE)],
                text=np.round(pivot.values, 1), texttemplate="%{text}%", textfont=dict(size=12), showscale=False, xgap=2, ygap=2,
                hovertemplate="%{y}, %{x}: %{z:.1f}% saving<extra></extra>",
            )
        )
        figure.update_layout(xaxis=dict(side="top", gridcolor="rgba(0,0,0,0)"), yaxis=dict(gridcolor="rgba(0,0,0,0)"), margin=dict(t=30))
        chart_card("Real saving by event and category", None, figure, 330)

    c1, c2 = st.columns([3, 2], gap="medium")
    with c1:
        years = event_by_year().reindex(summary.index[::-1])
        figure = go.Figure(
            go.Heatmap(
                z=years.values, x=[str(c) for c in years.columns], y=years.index,
                colorscale=[[i / (len(SEQUENTIAL_BLUE) - 1), c] for i, c in enumerate(SEQUENTIAL_BLUE)],
                text=[["" if pd.isna(v) else f"{v:.1f}" for v in row] for row in years.values], texttemplate="%{text}", textfont=dict(size=12), showscale=False, xgap=2, ygap=2,
                hovertemplate="%{y} %{x}: %{z:.1f}% saving<extra></extra>",
            )
        )
        figure.update_layout(xaxis=dict(side="top", gridcolor="rgba(0,0,0,0)"), yaxis=dict(gridcolor="rgba(0,0,0,0)"), margin=dict(t=30))
        chart_card("Real saving by year", "Average % below normal price on event days, all categories.", figure, 300)
    with c2:
        usd = summary["usd"].sort_values()
        figure = go.Figure(
            go.Bar(
                x=usd.values, y=usd.index, orientation="h", marker_color=INK,
                text=[f"${v:,.0f}" for v in usd.values], textposition="outside", textfont=dict(color=INK, size=12), cliponaxis=False,
                hovertemplate="%{y}: $%{x:,.0f}<extra></extra>",
            )
        )
        figure.update_layout(xaxis=dict(title="Average saving per event day (USD)", tickprefix="$", range=[0, usd.max() * 1.3]), margin=dict(t=10))
        chart_card("Saving in dollars", "Normal price minus event price, per series-day.", figure, 300)
    caveat()


# --------------------------------------------------------------------------- 5. Marketplaces & condition


def marketplaces() -> None:
    gaps = load("mart_platform_price_gap")
    scorecard = load("mart_model_scorecard")
    page_header(
        "Amazon vs Flipkart, new vs refurbished",
        "Same product, same day. Neither marketplace is cheaper overall, so the saving comes from checking both on the day. "
        "Refurbished units are a steady 22% below new.",
    )
    c1, c2 = st.columns([3, 2], gap="medium")
    with c1:
        categories = category_filter("market_categories")
    with c2:
        condition = st.segmented_control("Condition", ["New", "Refurbished", "Both"], default="Both", key="market_condition") or "Both"
    data = gaps[gaps["product_category"].isin(categories)]
    if condition != "Both":
        data = data[data["condition"] == condition]

    stat_band(
        [
            (f"{len(data):,}", "matched product-days", "same model, condition and day"),
            (f"{(data['cheaper_platform'] == 'Amazon').mean():.1%}", "of days Amazon is cheaper", "Wilcoxon p = 0.24"),
            (pct(data["gap_pct"].median(), 2, sign=True), "median gap", "Amazon minus Flipkart"),
            (pct(data["gap_pct"].abs().mean()), "typical daily gap", "in either direction"),
        ]
    )

    c1, c2 = st.columns(2, gap="medium")
    with c1:
        figure = go.Figure(
            go.Histogram(x=data.loc[data["gap_pct"].between(-12, 12), "gap_pct"], xbins=dict(start=-12, end=12, size=0.5), marker=dict(color=ACCENT, line=dict(width=0)),
                         hovertemplate="%{x}%: %{y:,} days<extra></extra>")
        )
        figure.add_vline(x=0, line=dict(color=INK, width=1))
        figure.update_layout(xaxis=dict(title="Amazon vs Flipkart (%), negative = Amazon cheaper"), yaxis=dict(title="Days"), bargap=0.05, margin=dict(t=10))
        outside = (~data["gap_pct"].between(-12, 12)).mean()
        chart_card("How far apart the prices are", f"Gaps beyond \u00b112% ({outside:.1%} of days) are not drawn.", figure, 320)
    with c2:
        quarterly = data.assign(month=data["price_date"].dt.to_period("Q").dt.to_timestamp()).groupby("month")["cheaper_platform"]
        sizes = quarterly.size()
        monthly = quarterly.apply(lambda s: (s == "Amazon").mean() * 100)[sizes >= 0.5 * sizes.median()]
        figure = go.Figure(go.Scatter(x=monthly.index, y=monthly.values, mode="lines+markers", line=dict(color=PLATFORM_COLORS["Amazon"]), marker=dict(size=6),
                                      hovertemplate="%{x|%b %Y}: Amazon cheaper on %{y:.0f}% of days<extra></extra>"))
        reference_line(figure, 50, "Even")
        figure.update_layout(yaxis=dict(title="Days Amazon is cheaper (%)", range=[30, 70]), margin=dict(t=10))
        chart_card("Share of days Amazon is cheaper, by quarter", "It hovers around 50% throughout: no lasting advantage. Partial quarters (under half the usual number of matched days) are left out.", figure, 320)

    c1, c2 = st.columns([2, 3], gap="medium")
    with c1:
        by_category = data.groupby("product_category")["gap_pct"].apply(lambda s: s.abs().mean()).reindex([c for c in CATEGORY_ORDER if c in categories])
        figure = go.Figure(go.Bar(x=by_category.index, y=by_category.values, marker_color=[CATEGORY_COLORS[c] for c in by_category.index],
                                  text=[pct(v) for v in by_category.values], textposition="outside", textfont=dict(color=INK, size=12), cliponaxis=False,
                                  hovertemplate="%{x}: %{y:.2f}%<extra></extra>"))
        figure.update_layout(yaxis=dict(title="Typical daily gap (%)", range=[0, max(4, by_category.max() * 1.3)]), margin=dict(t=10))
        chart_card("Typical gap by category", None, figure, 340)
    with c2:
        refurb = scorecard[scorecard["product_category"].isin(categories)].sort_values("refurbished_discount_pct")
        figure = go.Figure(go.Scatter(x=refurb["refurbished_discount_pct"], y=refurb["model_name"], mode="markers",
                                      marker=dict(size=10, color=[CATEGORY_COLORS[c] for c in refurb["product_category"]], line=dict(color="#FFFFFF", width=1.5)),
                                      hovertemplate="%{y}: %{x:.1f}% cheaper refurbished<extra></extra>"))
        figure.update_layout(xaxis=dict(title="Refurbished discount vs new (%)", range=[20.5, 24], dtick=0.5), yaxis=dict(gridcolor="#EEF1F5"), margin=dict(t=10))
        chart_card("Refurbished discount by model", "Remarkably stable across models: 22 to 23%.", figure, max(340, 18 * len(refurb) + 60))


# --------------------------------------------------------------------------- 6. Forecasts


def forecasts() -> None:
    metrics = load_metrics().get("horizons", {})
    backtest = load("mart_forecast_backtest")
    page_header(
        "Price forecasts",
        "CatBoost models predict each series' price 7 and 30 days ahead with an 80% range. "
        "They are scored on the final 180 days, which the models never saw.",
    )
    if not metrics:
        st.warning("Model metrics not found. Run `python -m apple_pricing.pipeline` to train the models.")
        return
    seven, thirty = metrics["7d"], metrics["30d"]
    stat_band(
        [
            (f"${seven['model']['MAE']:.2f}", "7-day average error", f"{seven['model']['WAPE_pct']:.1f}% of price"),
            (pct(-seven["mae_improvement_vs_naive_pct"], 0), "vs assuming today's price holds", "7-day horizon"),
            (pct(-seven["mae_improvement_vs_trailing_30d_pct"], 0), "vs a 30-day average", "7-day horizon"),
            (f"${thirty['model']['MAE']:.2f}", "30-day average error", f"{pct(-thirty['mae_improvement_vs_naive_pct'], 0)} vs today's price"),
            (pct(seven["p10_p90_interval_coverage_pct"], 0), "inside the 80% range", "7-day, after calibration"),
        ]
    )

    c1, c2 = st.columns([3, 2], gap="medium")
    with c1, st.container(border=True):
        st.markdown('<div class="card-title">Error by category, against two simple baselines</div><p class="card-note">Lower is better. The model wins in every category at both horizons.</p>', unsafe_allow_html=True)
        horizon = st.segmented_control("Horizon", [7, 30], default=7, format_func=lambda h: f"{h} days ahead", key="fc_horizon", label_visibility="collapsed") or 7
        part = backtest[backtest["horizon_days"] == horizon]
        mae = part.groupby("product_category")[["model_abs_error_usd", "trailing_abs_error_usd", "naive_abs_error_usd"]].mean().reindex(CATEGORY_ORDER)
        figure = go.Figure()
        for column, name, colour in [
            ("naive_abs_error_usd", "Today's price", LIGHT_GRAY),
            ("trailing_abs_error_usd", "30-day average", MID_GRAY),
            ("model_abs_error_usd", "CatBoost model", INK),
        ]:
            figure.add_trace(go.Bar(x=mae.index, y=mae[column], name=name, marker_color=colour,
                                    hovertemplate="%{x}: $%{y:.2f}<extra>" + name + "</extra>"))
        figure.update_layout(barmode="group", yaxis=dict(title="Average error (USD)", tickprefix="$"))
        show(figure, 330)
    with c2:
        importance = pd.Series(seven["top_features"]).sort_values().tail(10)
        labels = {
            "week_of_year": "Week of year", "month": "Month", "roll_std_30d_pct": "30-day volatility", "condition": "Condition",
            "sale_event": "Sale event name", "is_sale_event": "Sale event on", "vs_roll_mean_30d": "Price vs 30-day mean",
            "days_since_release": "Days since release", "vs_baseline_30obs": "Price vs normal price", "price_index": "Price index",
            "vs_roll_mean_7d": "Price vs 7-day mean", "vs_roll_max_90d": "Price vs 90-day high", "model_name": "Model",
            "vs_other_platform": "Price vs other marketplace", "spread_pct": "Listing spread", "launch_price_usd": "Launch price",
            "log_price": "Price level", "day_of_week": "Day of week", "vs_roll_min_90d": "Price vs 90-day low",
            "platform": "Marketplace", "product_category": "Category", "listing_count": "Listings that day",
            "ret_7d": "7-day price change", "ret_30d": "30-day price change", "days_since_successor_release": "Days since successor launch",
        }
        figure = go.Figure(go.Bar(x=importance.values, y=[labels.get(i, i) for i in importance.index], orientation="h", marker_color=ACCENT,
                                  hovertemplate="%{y}: %{x:.1f}<extra></extra>"))
        figure.update_layout(xaxis=dict(title="Importance (7-day model)"), margin=dict(t=10))
        chart_card("What the model relies on", "Timing (sale seasons, the launch cycle) and how far the price sits from normal.", figure, 380)

    with st.container(border=True):
        st.markdown('<div class="card-title">Forecast vs what happened</div><p class="card-note">Pick a series. The line is the forecast made 7 or 30 days earlier; dots are the actual prices.</p>', unsafe_allow_html=True)
        s1, s2, s3 = st.columns([3, 2, 2])
        models = sorted(backtest["model_name"].unique())
        model = s1.selectbox("Model", models, index=models.index("Apple Watch Series 6 (44mm)") if "Apple Watch Series 6 (44mm)" in models else 0, key="fc_model")
        platform = s2.selectbox("Platform", ["Amazon", "Flipkart"], key="fc_platform")
        condition = s3.selectbox("Condition", ["New", "Refurbished"], key="fc_condition")
        part = backtest[(backtest["horizon_days"] == horizon) & (backtest["model_name"] == model) & (backtest["platform"] == platform) & (backtest["condition"] == condition)].sort_values("price_date")
        if part.empty:
            st.info("No test-period rows for this series.")
        else:
            target = part["price_date"] + pd.Timedelta(days=int(horizon))
            figure = go.Figure(
                [
                    go.Scatter(x=target, y=part["pred_p90_usd"], mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"),
                    go.Scatter(x=target, y=part["pred_p10_usd"], mode="lines", line=dict(width=0), fill="tonexty", fillcolor="rgba(36,87,214,0.14)", name="80% range", hoverinfo="skip"),
                    go.Scatter(x=target, y=part["pred_p50_usd"], mode="lines", name="Forecast", line=dict(color=ACCENT, width=2)),
                    go.Scatter(x=target, y=part["actual_price_usd"], mode="markers", name="Actual", marker=dict(size=6, color=INK)),
                ]
            )
            figure.update_layout(yaxis=dict(title="Price (USD)", tickprefix="$"), hovermode="x unified")
            show(figure, 360)


# --------------------------------------------------------------------------- 7. Buy or wait


def buy_or_wait() -> None:
    deals = load("mart_deal_scores")
    page_header(
        "Buy now or wait",
        "Every model, platform and condition, scored on the latest price, its normal level, and the calibrated 30-day forecast.",
    )
    counts = deals["recommendation"].value_counts()
    stat_band(
        [
            (str(counts.get("Buy now", 0)), "buy now", "price below its forecast range or normal level"),
            (str(counts.get("Wait", 0)), "wait", "price above its range or a drop expected"),
            (str(counts.get("No rush", 0)), "no rush", "close to normal, expected to stay flat"),
            (f"{deals['as_of_date'].max():%d %b %Y}", "prices as of", None),
        ]
    )
    c1, c2 = st.columns([3, 2], gap="medium")
    with c1:
        categories = category_filter("deal_categories")
    with c2:
        calls = st.pills("Recommendation", ["Buy now", "Wait", "No rush"], selection_mode="multi", default=["Buy now"], key="deal_calls") or ["Buy now", "Wait", "No rush"]
    view = deals[deals["product_category"].isin(categories) & deals["recommendation"].isin(calls)].sort_values("deal_score", ascending=False)

    section("Top picks")
    deal_tiles(view.head(4))
    if len(view) > 4:
        deal_tiles(view.iloc[4:8])

    section("All series", f"{len(view)} series match. Sorted by deal score, which weighs the expected 30-day change, the discount vs normal price, rating and stock.")
    st.dataframe(
        view[["recommendation", "model_name", "platform", "condition", "current_price_usd", "discount_vs_normal_pct",
              "forecast_30d_usd", "forecast_30d_p10_usd", "forecast_30d_p90_usd", "recommendation_reason", "deal_score"]],
        hide_index=True, width="stretch", height=420,
        column_config={
            "recommendation": "Call", "model_name": "Model", "platform": "Platform", "condition": "Condition",
            "current_price_usd": st.column_config.NumberColumn("Price", format="$%.0f"),
            "discount_vs_normal_pct": st.column_config.NumberColumn("Below normal", format="%.1f%%", help="Positive means cheaper than the series' normal price"),
            "forecast_30d_usd": st.column_config.NumberColumn("30-day forecast", format="$%.0f"),
            "forecast_30d_p10_usd": st.column_config.NumberColumn("Low (P10)", format="$%.0f"),
            "forecast_30d_p90_usd": st.column_config.NumberColumn("High (P90)", format="$%.0f"),
            "recommendation_reason": "Why",
            "deal_score": st.column_config.ProgressColumn("Deal score", min_value=0, max_value=100, format="%.0f"),
        },
    )


# --------------------------------------------------------------------------- 8. Ask the data


@st.cache_resource(show_spinner=False)
def _sandbox():
    return build_connection(MARTS_DIR)


def analyst() -> None:
    page_header(
        "Ask the data",
        "Ask a question in plain English. Claude writes read-only SQL against the data marts, runs it in a sandbox, "
        "and answers with the numbers it found. Every query is shown so you can check the answer.",
    )
    api_key = ai_analyst.get_api_key(st.secrets)
    examples = [
        "Which iPhone lost the most value after its successor launched?",
        "Which sale event saves the most on Macs compared with the normal price?",
        "Top 5 buy-now deals under $500, and why",
        "How accurate is the 30-day forecast for Apple Watch?",
    ]
    history = st.session_state.setdefault("analyst_history", [])
    if not api_key:
        st.info("The analyst needs an Anthropic API key. Add ANTHROPIC_API_KEY to the app's secrets to turn it on.")
    if not history:
        st.markdown('<p class="card-note">Try one of these:</p>', unsafe_allow_html=True)
        picked = st.pills("Examples", examples, label_visibility="collapsed", key="analyst_example")
    else:
        picked = None

    for turn in history:
        with st.chat_message(turn["role"]):
            st.markdown(turn["content"])
            for sql, outcome in turn.get("queries", []):
                with st.expander(f"SQL ({outcome})"):
                    st.code(sql, language="sql")

    question = st.chat_input("Ask about prices, launches, sale events or forecasts", disabled=not api_key) or (picked if api_key else None)
    if not question:
        return
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.spinner("Querying the data marts"):
            try:
                result = ai_analyst.ask(question, [{"role": t["role"], "content": t["content"]} for t in history], _sandbox(), api_key)
            except Exception as error:
                st.error(ai_analyst.describe_error(error))
                return
        st.markdown(result["answer"])
        for sql, outcome in result["queries"]:
            with st.expander(f"SQL ({outcome})"):
                st.code(sql, language="sql")
    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": result["answer"], "queries": result["queries"]})


# --------------------------------------------------------------------------- 9. About


def about() -> None:
    page_header(
        "About this project",
        "Apple's new CEO, John Ternus, spent 25 years building Apple's hardware. That made me curious about the other side "
        "of the product cycle: what happens to a product's price after launch, once the market decides what it is worth.",
    )
    st.image("reports/figures/architecture.png", width="stretch")

    c1, c2 = st.columns(2, gap="large")
    with c1:
        section("How it is built")
        st.markdown(
            "- **AWS S3** stores the raw data as year-partitioned Parquet.\n"
            "- **Snowflake** loads it through a storage integration and `COPY INTO`.\n"
            "- **dbt** models it into a tested star schema and analytics marts.\n"
            "- **CatBoost** forecasts each series 7 and 30 days ahead with calibrated 80% ranges.\n"
            "- **Streamlit** and **Power BI** present the results; **Claude** answers questions in plain English.\n"
            "- **GitHub Actions** rebuilds and tests every dbt model on each push."
        )
        st.markdown(f"[Source code on GitHub]({REPO_URL})  \n[Full project report (PDF)]({REPORT_URL})")
    with c2:
        section("Data quality")
        results = load("dbt_run_results")
        if not results.empty:
            results = results.assign(type=results["resource_type"].str.replace("NodeType.", "", regex=False).str.capitalize())
            summary = results.groupby("type").agg(nodes=("name", "size"), passing=("status", lambda s: s.str.lower().isin(["pass", "success"]).sum()))
            summary.index.name = "Check"
            st.dataframe(summary.rename(columns={"nodes": "Checked", "passing": "Passing"}), width="stretch")
        st.markdown(
            '<p class="card-note">Tests cover uniqueness of every table\'s grain, allowed values, numeric ranges, '
            "links between tables, and business rules such as the reported discount matching the prices.</p>",
            unsafe_allow_html=True,
        )

    section("Data marts")
    st.dataframe(
        pd.DataFrame([{"Table": name, "Rows": len(load(name)), "What it holds": text} for name, text in TABLE_DESCRIPTIONS.items()]),
        hide_index=True, width="stretch", column_config={"Rows": st.column_config.NumberColumn("Rows", format="localized")},
    )
    caveat()
