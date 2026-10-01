"""Visual identity: palette, typography, page CSS, and the Plotly template.

Data colours follow the entity, never its rank: a category or platform keeps
its colour in every chart and under every filter. The category order and the
platform pair were checked for colour-vision-deficiency separation.
"""

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# Interface tokens
BACKGROUND = "#F2F4F7"   # aluminium
SURFACE = "#FFFFFF"
INK = "#172033"          # navy graphite
INK_SECONDARY = "#4A5568"
INK_MUTED = "#7A8597"
RULE = "#DDE2E9"
ACCENT = "#2457D6"       # signal blue (interface accent only)

# Chart chrome
GRID = "#E6EAF0"
AXIS = "#C9D0DA"

# Data colours
CATEGORY_COLORS = {"iPhone": "#2A78D6", "iPad": "#EB6834", "Mac": "#1BAF7A", "Watch": "#EDA100"}
CATEGORY_ORDER = list(CATEGORY_COLORS)
PLATFORM_COLORS = {"Amazon": "#4A3AA7", "Flipkart": "#E87BA4"}
SERIES = ["#2A78D6", "#EB6834", "#1BAF7A"]
SEQUENTIAL_BLUE = ["#EAF2FD", "#B7D3F6", "#6DA7EC", "#2A78D6", "#1C5CAB", "#0D366B"]

STATUS = {"Buy now": "#0C8A0C", "Wait": "#C2410C", "No rush": "#7A8597"}

FONT = "Manrope, 'Segoe UI', system-ui, sans-serif"

pio.templates["apple_pricing"] = go.layout.Template(
    layout=go.Layout(
        font=dict(family=FONT, color=INK_SECONDARY, size=13),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        colorway=SERIES,
        xaxis=dict(gridcolor=GRID, linecolor=AXIS, zeroline=False, ticks="", tickfont=dict(color=INK_MUTED), automargin=True, title_font=dict(color=INK_MUTED, size=12)),
        yaxis=dict(gridcolor=GRID, linecolor="rgba(0,0,0,0)", zeroline=False, ticks="", tickfont=dict(color=INK_MUTED), automargin=True, title_font=dict(color=INK_MUTED, size=12)),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0, title_text="", font=dict(color=INK_SECONDARY, size=12)),
        hoverlabel=dict(bgcolor=SURFACE, font=dict(family=FONT, color=INK, size=12), bordercolor=RULE),
        hovermode="closest",
        margin=dict(l=8, r=12, t=36, b=8),
        bargap=0.3,
        bargroupgap=0.1,
    ),
    data=dict(
        scatter=[go.Scatter(line=dict(width=2.25), marker=dict(size=8))],
        bar=[go.Bar(marker=dict(cornerradius=4, line=dict(width=0)))],
    ),
)
pio.templates.default = "apple_pricing"

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap');

html, body, h1, h2, h3, h4, h5, h6, p, li, label, input, textarea, select, button, td, th,
div:not([data-testid="stIconMaterial"]), span:not([data-testid="stIconMaterial"]):not(.material-symbols-rounded) {{
    font-family: {FONT} !important;
}}
code, pre, code * {{ font-family: Consolas, "SF Mono", monospace !important; }}
[data-testid="stAppViewContainer"], [data-testid="stMain"] {{ background: {BACKGROUND}; }}
[data-testid="stHeader"] {{ background: {SURFACE}; border-bottom: 1px solid {RULE}; }}
[data-testid="stToolbarActions"], [data-testid="stMainMenu"], [data-testid="stAppDeployButton"], [data-testid="stDecoration"],
#MainMenu, footer, [data-testid="stStatusWidget"] {{ display: none !important; }}
[data-testid="stHeader"] a {{ color: {INK_SECONDARY} !important; font-weight: 600; }}
[data-testid="stHeader"] a[aria-current="page"], [data-testid="stHeader"] a:hover {{ color: {INK} !important; }}
.block-container, [data-testid="stMainBlockContainer"] {{ max-width: 1240px; padding-top: 5.5rem; padding-bottom: 4rem; }}

h1, h2, h3, h4 {{ color: {INK}; letter-spacing: -0.02em; }}
p, li {{ color: {INK_SECONDARY}; }}

/* Bordered containers are the only "card": used for chart groups, not for every item. */
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {{
    background: {SURFACE};
    border-color: {RULE} !important;
    border-radius: 12px;
}}

.pg-title {{ font-size: 2.35rem; font-weight: 800; line-height: 1.1; color: {INK}; letter-spacing: -0.03em; margin: 0 0 .5rem; max-width: 22ch; }}
.pg-lead {{ font-size: 1.05rem; line-height: 1.6; color: {INK_SECONDARY}; max-width: 68ch; margin: 0 0 1.5rem; }}
.sec-title {{ font-size: 1.35rem; font-weight: 700; color: {INK}; letter-spacing: -0.02em; margin: 2.2rem 0 .25rem; }}
.sec-lead {{ font-size: .95rem; color: {INK_SECONDARY}; max-width: 75ch; margin: 0 0 1rem; line-height: 1.55; }}
.card-title {{ font-size: 1.02rem; font-weight: 700; color: {INK}; margin: .1rem 0 .15rem; letter-spacing: -0.01em; }}
.card-note {{ font-size: .86rem; color: {INK_MUTED}; margin: 0 0 .35rem; line-height: 1.45; }}

/* Stat band: one strip divided by rules, not a grid of identical cards. */
.stat-band {{ display: grid; grid-template-columns: repeat(var(--n), minmax(0, 1fr)); background: {SURFACE};
             border: 1px solid {RULE}; border-radius: 12px; margin: .5rem 0 1rem; }}
.stat {{ padding: 1rem 1.25rem; border-left: 1px solid {RULE}; }}
.stat:first-child {{ border-left: none; }}
.stat-value {{ font-size: 1.75rem; font-weight: 800; color: {INK}; letter-spacing: -0.02em; font-variant-numeric: tabular-nums; line-height: 1.15; }}
.stat-label {{ font-size: .84rem; color: {INK_SECONDARY}; margin-top: .25rem; line-height: 1.35; }}
.stat-context {{ font-size: .78rem; color: {INK_MUTED}; margin-top: .15rem; }}

/* Hero */
.hero-figure {{ font-size: 3.6rem; font-weight: 800; color: {INK}; letter-spacing: -0.04em; line-height: 1; font-variant-numeric: tabular-nums; }}
.hero-caption {{ font-size: .95rem; color: {INK_SECONDARY}; margin: .35rem 0 1.25rem; line-height: 1.5; max-width: 36ch; }}

/* Deal tiles */
.deal {{ background: {SURFACE}; border: 1px solid {RULE}; border-radius: 12px; padding: 1rem 1.1rem; height: 100%; }}
.deal-call {{ display: inline-block; font-size: .78rem; font-weight: 700; padding: .15rem .55rem; border-radius: 999px; color: #fff; }}
.deal-model {{ font-size: 1rem; font-weight: 700; color: {INK}; margin: .55rem 0 .1rem; line-height: 1.3; }}
.deal-meta {{ font-size: .82rem; color: {INK_MUTED}; margin-bottom: .6rem; }}
.deal-price {{ font-size: 1.6rem; font-weight: 800; color: {INK}; font-variant-numeric: tabular-nums; letter-spacing: -0.02em; }}
.deal-range {{ font-size: .84rem; color: {INK_SECONDARY}; margin-top: .2rem; }}
.deal-why {{ font-size: .82rem; color: {INK_SECONDARY}; margin-top: .55rem; line-height: 1.4; }}

.caveat {{ font-size: .82rem; color: {INK_MUTED}; border-top: 1px solid {RULE}; padding-top: .8rem; margin-top: 2rem; line-height: 1.5; }}
a {{ color: {ACCENT}; }}

@media (max-width: 900px) {{
    .stat-band {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .stat:nth-child(odd) {{ border-left: none; }}
    .pg-title {{ font-size: 1.8rem; }}
    .hero-figure {{ font-size: 2.6rem; }}
}}
</style>
"""


def apply() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def reference_line(figure, y: float, label: str) -> None:
    """Solid hairline reference (e.g. launch price = 100) with a muted label."""
    figure.add_hline(y=y, line=dict(color=AXIS, width=1))
    figure.add_annotation(
        x=1, xref="paper", y=y, text=label, showarrow=False, xanchor="right", yanchor="bottom",
        font=dict(color=INK_MUTED, size=11),
    )
