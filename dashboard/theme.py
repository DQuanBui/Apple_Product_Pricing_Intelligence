"""Chart palette and Plotly template.

Colours follow the entity, never its rank: a category or platform keeps its
colour in every chart and under every filter. The category order and the
platform pair were checked for colour-vision-deficiency separation.
"""

import plotly.graph_objects as go
import plotly.io as pio

INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SURFACE = "#fcfcfb"

CATEGORY_COLORS = {
    "iPhone": "#2a78d6",
    "iPad": "#eb6834",
    "Mac": "#1baf7a",
    "Watch": "#eda100",
}
CATEGORY_ORDER = list(CATEGORY_COLORS)

PLATFORM_COLORS = {"Amazon": "#4a3aa7", "Flipkart": "#e87ba4"}

# Generic series slots for charts comparing measures rather than entities.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]

RECOMMENDATION_ICONS = {"Buy now": "🟢 Buy now", "Wait": "🟠 Wait", "No rush": "⚪ No rush"}

FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'

pio.templates["apple_pricing"] = go.layout.Template(
    layout=go.Layout(
        font=dict(family=FONT, color=INK_SECONDARY, size=13),
        title=dict(font=dict(color=INK, size=16), x=0, xanchor="left", y=0.98, yanchor="top", yref="container"),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        colorway=SERIES,
        xaxis=dict(gridcolor=GRID, linecolor=AXIS, zeroline=False, ticks="", tickfont=dict(color=INK_MUTED), automargin=True),
        yaxis=dict(gridcolor=GRID, linecolor=AXIS, zeroline=False, ticks="", tickfont=dict(color=INK_MUTED), automargin=True),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title_text=""),
        hoverlabel=dict(bgcolor="white", font=dict(family=FONT, color=INK), bordercolor=AXIS),
        hovermode="closest",
        margin=dict(l=16, r=16, t=88, b=16),
        bargap=0.25,
        bargroupgap=0.08,
    ),
    data=dict(
        scatter=[go.Scatter(line=dict(width=2), marker=dict(size=8))],
        bar=[go.Bar(marker=dict(cornerradius=4, line=dict(width=0)))],
    ),
)
pio.templates.default = "apple_pricing"


def reference_line(figure, y: float, label: str) -> None:
    """Solid hairline reference (e.g. MSRP = 100) with a muted label."""
    figure.add_hline(y=y, line=dict(color=AXIS, width=1))
    figure.add_annotation(
        x=1, xref="paper", y=y, text=label, showarrow=False, xanchor="right", yanchor="bottom",
        font=dict(color=INK_MUTED, size=11),
    )
