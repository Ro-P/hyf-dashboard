"""
HYF Impact Dashboard: the filters and the tabs.

How it fits together:
  1. render() loads the workbook and draws the filters (years, months, cohorts, audience).
  2. Your choices become one Sel object, `sel`.
  3. Every tab is called with the same data `d` and the same `sel`, so a filter change reaches all tabs.
     (Streamlit runs this script again from the top after every change.)

The code of each tab is in dashboard/tab_*.py; shared helpers are in dashboard/common.py.
"""
from __future__ import annotations

import html
import os
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard.common import *  # noqa: F401,F403
from dashboard.tab_a_overview import page_overview
from dashboard.tab_b_programme import page_programme
from dashboard.tab_c_employment import page_employment
from dashboard.tab_d_historic import page_historic
from dashboard.tab_e_org import page_org
from dashboard.tab_f_finance import page_finance
from dashboard.tab_g_partners import page_partners
from dashboard.tab_h_volunteers import page_volunteers
from dashboard.tab_i_visibility import page_visibility


# --------------------------------------------------------------------------- #
# Export (public view → one HTML file)
# --------------------------------------------------------------------------- #
def export_html(ex: Export, period_label: str, has_sample: bool) -> str:
    esc = html.escape
    parts, first = [], True
    for s in ex.sections:
        block = [f"<section><h2>{esc(s['title'])}</h2>"]
        if s["intro"]:
            block.append(f"<p class='intro'>{esc(s['intro'])}</p>")
        if s["kpis"]:
            block.append("<div class='kpis'>" + "".join(
                f"<div class='kpi'><div class='l'>{esc(l)}</div><div class='v'>{esc(v)}</div><div class='c'>{esc(c or '')}</div></div>" for l, v, c in s["kpis"]) + "</div>")
        if s["figs"]:
            block.append("<div class='figs'>")
            for title, fig in s["figs"]:
                f2 = go.Figure(fig)
                f2.update_layout(height=340)
                block.append(f"<div class='fig'><h3>{esc(title)}</h3>" + f2.to_html(full_html=False, include_plotlyjs=first, default_width="100%", default_height="340px", config={"displaylogo": False, "responsive": True}) + "</div>")
                first = False
            block.append("</div>")
        for n in s["notes"]:
            block.append(f"<p class='note'>{esc(n)}</p>")
        block.append("</section>")
        parts.append("".join(block))
    banner = "<div class='banner'>Contains sample placeholder data — not for external use.</div>" if has_sample else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>HYF Impact Dashboard · {esc(period_label)}</title><style>
{brand.export_css()}
main{{max-width:1200px;margin:0 auto;padding:24px 16px;display:flex;flex-direction:column;gap:20px}}
section{{background:#fff;border:1px solid #E8DFC4;border-radius:12px;padding:20px;overflow:hidden}}
h2{{margin:0 0 4px;font-size:20px}} h3{{margin:0 0 6px;font-size:14px}} .intro{{margin:0 0 14px;color:#6B5A4E}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,200px),1fr));gap:12px;margin-bottom:12px}}
.kpi{{border:1px solid #E8DFC4;border-radius:10px;padding:12px}} .kpi .l{{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:#6B5A4E}}
.kpi .v{{font-size:28px;font-weight:700;margin:6px 0}} .kpi .c{{font-size:12px;color:#6B5A4E}}
.figs{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,460px),1fr));gap:12px}} .fig{{min-width:0}}
.note{{font-size:12px;color:#6B5A4E;margin:8px 0 0}} .banner{{background:#FFF09E;padding:10px 16px;text-align:center;font-weight:700}}
footer{{text-align:center;font-size:12px;color:#6B5A4E;padding:16px}}
</style></head><body>{banner}{brand.export_header("HackYourFuture · Impact Dashboard", f"{period_label} · Definitions: HYF Indicator Overview & Measurement Dictionary v1.3 · Generated {datetime.now():%d %B %Y}")}
<main>{''.join(parts)}</main><footer>Aggregate figures only; groups smaller than {SUPPRESS_BELOW} people are hidden.</footer>
<script>function f(){{document.querySelectorAll('.plotly-graph-div').forEach(d=>window.Plotly&&Plotly.Plots.resize(d))}}addEventListener('load',f);addEventListener('resize',f)</script></body></html>"""


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def render(indicators_path: Path, today: date | None = None) -> None:
    today = today or date.today()
    if not indicators_path.exists():
        st.error(f"Indicator workbook not found: {indicators_path}. Put HYF_indicators.xlsx in the data folder or set HYF_INDICATORS_FILE in .env.")
        return
    d = load_indicators(str(indicators_path), indicators_path.stat().st_mtime, show_sample(), SAMPLE_TABS)
    yrs = set()
    for name in ("inclusion", "team", "visibility", "students_annual", "finance", "partners", "community", "volunteers"):
        yrs |= {int(y) for y in pd.to_numeric(d[name].get("year", pd.Series(dtype=float)), errors="coerce").dropna()}
    yrs |= {int(y) for y in pd.to_numeric(d["historic"].get("graduation_year", pd.Series(dtype=float)), errors="coerce").dropna()}
    yrs |= {int(y) for y in pd.to_numeric(d.get("origin", pd.DataFrame()).get("start_year", pd.Series(dtype=float)), errors="coerce").dropna()}
    yrs |= {int(y) for y in pd.to_numeric(d.get("impact_origin", pd.DataFrame()).get("start_year", pd.Series(dtype=float)), errors="coerce").dropna()}
    yrs |= {int(str(p)[:4]) for p in d.get("impact_graduates", pd.DataFrame()).get("period", pd.Series(dtype=str)).dropna() if str(p)[:4].isdigit()}
    years = sorted(y for y in yrs if 2015 <= y <= today.year + 1) or [today.year]
    cohorts = sorted({str(c) for name in ("inclusion", "outcomes", "historic", "impact_graduates", "classes") for c in d.get(name, pd.DataFrame()).get("cohort", pd.Series(dtype=str)).dropna() if str(c) not in ("nan", "None")},
                     key=lambda c: (len(c), c))

    st.markdown("##### Filters")
    f1, f2, f3, f4 = st.columns([1, 1, 1.2, 2.6])
    y_from = f1.selectbox("From year", years, index=0, key="imp_from")
    y_to = f2.selectbox("To year", years, index=len(years) - 1, key="imp_to")
    if y_from > y_to:
        y_from, y_to = y_to, y_from
        st.caption("“From” was after “To”, so the two years were swapped.")
    half = f3.selectbox("Months", ["Full year", "H1 · Jan–Jun", "H2 · Jul–Dec"], key="imp_half",
                        help="H1 = January–June, H2 = July–December. With several years, H1 means the first half of each year.")
    picked = f4.multiselect("Cohorts", cohorts, default=[], key="imp_cohorts", placeholder="All cohorts",
                            help="Leave empty for all cohorts. Applies to pages A–D; other pages are not organised by cohort.")
    sel = Sel(y_from, y_to, None if half == "Full year" else half[:2], list(picked))
    c3, c4 = st.columns([2, 1])
    audience = c3.segmented_control("Audience", ["Public", "Internal"], default="Public", key="imp_aud") or "Public"
    internal = audience == "Internal"
    st.caption(f"Showing **{sel.label}**")
    if sel.half:
        st.caption("Pages A–D use whole years, so the Months choice doesn't change them; it applies to pages with half-year data (E–I).")
    ex = Export()
    has_sample = any(bool(df["is_sample"].any()) for df in d.values() if "is_sample" in df and not df.empty)
    has = lambda *names: any(not d.get(n, pd.DataFrame()).empty for n in names)
    pages = [
        ("A · Impact overview", has("impact_summary", "classes", "inclusion", "outcomes"), lambda: page_overview(d, sel, internal, today, ex)),
        ("B · Programme & inclusion", has("students_supported", "students_by_cohort", "origin_range", "education", "origin"), lambda: page_programme(d, sel, internal, today, ex)),
        ("C · Employment", True, lambda: page_employment(d, sel, internal, today, ex)),
        ("D · Historic programme", has("historic"), lambda: page_historic(d, sel, internal, today, ex)),
        ("E · Organisation & community", has("community") or (not d["team"].empty and d["team"][[c for c in ("fixed_staff", "zzp_experts", "interns") if c in d["team"]]].notna().any().any()),
         lambda: page_org(d, sel, internal, ex)),
        ("F · Finance", has("finance"), lambda: page_finance(d, sel, internal, ex)),
        ("G · Partners", has("partners", "employers", "partner_types"), lambda: page_partners(d, sel, internal, ex)),
        ("H · Volunteers", has("volunteers", "volunteer_status", "volunteer_expertise") or ("active_volunteers" in d["team"] and d["team"]["active_volunteers"].notna().any()),
         lambda: page_volunteers(d, sel, internal, ex)),
        ("I · Visibility", has("visibility"), lambda: page_visibility(d, sel, internal, ex)),
    ]
    pages = [(name, fn) for name, ok, fn in pages if ok]
    if not pages:
        st.info("There is no data in the workbook yet. Run tools/update_from_sheet.py and upload the files.")
        return
    for tab, (_, fn) in zip(st.tabs([name for name, _ in pages]), pages):
        with tab:
            fn()
    with c4:
        st.download_button(
            "⬇ Download public HTML", data=export_html(ex, sel.label, has_sample), file_name=f"HYF_impact_{sel.key}.html", mime="text/html",
            help="One file with the public view of all pages for this selection. Email it or open it offline. Internal details are never included.",
            disabled=internal, width="stretch",
        )
        if internal:
            st.caption("Switch to Public to export.")
