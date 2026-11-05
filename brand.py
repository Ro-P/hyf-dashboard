"""HackYourFuture brand: colours, logo and page header. Change the brand here, in one place.

Colours come from "Color codes used on the website" (HYF). The chart palette adds a few
darker/greyer tones of those colours so that charts with several series stay readable.
Also update .streamlit/config.toml if you change the main colours.
"""
from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

ASSETS = Path(__file__).parent / "assets"
LOGO_DARK = ASSETS / "hyf_mark_darkred.png"   # for light backgrounds
LOGO_LIGHT = ASSETS / "hyf_mark_beige.png"    # for dark backgrounds
ICON = ASSETS / "hyf_icon.png"                # browser tab

# Official website colours
WHITE = "#FFFFFF"
DARK_RED = "#5E1600"
BEIGE = "#FAF5D9"
LIGHT_RED = "#B12900"
YELLOW = "#FFF09E"

# Text and lines (warm tones that sit well next to the brand colours)
TEXT = "#2B1A12"
TEXT_MUTED = "#6B5A4E"
BORDER = "#E8DFC4"

# Charts: brand reds first, then warm supporting tones. All have at least 3:1 contrast on white.
CHART_COLORS = ["#B12900", "#B07D00", "#5E1600", "#7A6A5C", "#D9653F", "#2F2A26", "#A08A6E"]
MUTED = "#DCD3BC"   # "other" / secondary bars


@lru_cache(maxsize=None)
def data_uri(path: Path) -> str:
    """The image as a data: URI, so it also works inside exported HTML files."""
    try:
        return "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode()
    except OSError:
        return ""


def page_icon():
    return str(ICON) if ICON.exists() else "📊"


def plotly_layout() -> dict:
    """Shared Plotly look: brand font colour, light gridlines, HYF palette."""
    return dict(
        font=dict(family="Arial, Helvetica, sans-serif", color=TEXT),
        colorway=CHART_COLORS,
        title=dict(font=dict(color=DARK_RED)),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )


def apply_plotly_theme() -> None:
    """Make HYF the default look for every Plotly chart in the app."""
    import plotly.express as px
    import plotly.io as pio
    import plotly.graph_objects as go

    tpl = go.layout.Template(pio.templates["plotly_white"])
    tpl.layout.update(plotly_layout())
    tpl.layout.xaxis.gridcolor = tpl.layout.yaxis.gridcolor = "#EFE8D2"
    pio.templates["hyf"] = tpl
    pio.templates.default = "hyf"
    px.defaults.template = "hyf"
    px.defaults.color_discrete_sequence = CHART_COLORS


CSS = f"""
<style>
.hyf-header {{display:flex;align-items:center;gap:18px;background:{BEIGE};border-radius:14px;
  padding:18px 22px;margin:0 0 12px;border-left:8px solid {LIGHT_RED}}}
.hyf-header img {{height:52px;width:auto}}
.hyf-header h1 {{margin:0;padding:0;font-size:1.9rem;line-height:1.15;color:{DARK_RED};font-weight:800}}
.hyf-header p {{margin:4px 0 0;color:{TEXT_MUTED};font-size:.95rem}}
@media (max-width:640px) {{ .hyf-header img {{height:36px}} .hyf-header h1 {{font-size:1.35rem}} }}
h2, h3 {{color:{DARK_RED}}}
[data-testid="stMetricValue"] {{color:{LIGHT_RED}}}
[data-testid="stMetric"] {{background:{WHITE}}}
</style>
"""


def header(title: str = "Impact & data", subtitle: str = "") -> None:
    """HYF logo + page title, in brand colours."""
    import html as _html
    import streamlit as st

    st.markdown(CSS, unsafe_allow_html=True)
    logo = data_uri(LOGO_DARK)
    img = f'<img src="{logo}" alt="HackYourFuture">' if logo else ""
    sub = f"<p>{_html.escape(subtitle)}</p>" if subtitle else ""
    st.markdown(f'<div class="hyf-header">{img}<div><h1>{_html.escape(title)}</h1>{sub}</div></div>',
                unsafe_allow_html=True)


def sidebar_logo() -> None:
    import streamlit as st

    if LOGO_DARK.exists():
        st.logo(str(LOGO_DARK), size="large", link="https://hackyourfuture.net", icon_image=str(ICON) if ICON.exists() else None)


# Exported HTML files (shared by the app and the Impact dashboard export)
def export_css() -> str:
    return f"""
body{{font-family:Arial,Helvetica,sans-serif;margin:0;background:{BEIGE};color:{TEXT}}}
header{{background:{DARK_RED};color:{BEIGE};padding:24px max(16px,4vw);display:flex;align-items:center;gap:18px}}
header img{{height:46px;width:auto}} header h1{{margin:0;font-size:26px;color:{WHITE}}} header p{{margin:6px 0 0;opacity:.85}}
h2,h3{{color:{DARK_RED}}}
.kpi .v{{color:{LIGHT_RED}!important}}
"""


def export_header(title: str, subtitle: str) -> str:
    import html as _html
    logo = data_uri(LOGO_LIGHT)
    img = f'<img src="{logo}" alt="HackYourFuture">' if logo else ""
    return f"<header>{img}<div><h1>{_html.escape(title)}</h1><p>{_html.escape(subtitle)}</p></div></header>"
