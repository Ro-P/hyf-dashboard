"""
G · Partners.
Every chart here filters its rows with `sel` (the filters at the top of the dashboard).
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

from .common import *  # noqa: F401,F403  (shared helpers, settings and Sel)
from .common import _cohort_scope, _hbar, _help, _icon, _pick, _range_row  # noqa: F401


def page_partners(d, sel, internal, ex):
    ex.section("Partners", f"Companies and organisations that work with HYF and hire our graduates · {sel.label.split(' · ')[0]}")
    part = d.get("partners", pd.DataFrame())
    no_cohort_note(sel)
    if not part.empty:
        sample_flag(bool(part["is_sample"].any()))
        pr = part[sel.ymask(part["year"])]
        last = pr[pr["year"] == pr["year"].max()] if not pr.empty else pr
        lastval = lambda col: None if last.empty or col not in last or pd.isna(last[col].iloc[0]) else float(last[col].iloc[0])
        ly = int(last["year"].iloc[0]) if not last.empty else sel.year
        cards = [  # only the cards that have a number (new partners, for example, isn't in the sheet yet)
            ("partners_active", lastval("active_partners"), f"In {ly}" if not last.empty else ""),
            ("partners_new", nz(pr["new_partners"]) if not pr.empty else None, f"Joined in {sel.y0}" if sel.single else f"Joined {sel.y0}–{sel.y1}"),
        ]
        cards = [x for x in cards if x[1] is not None and not pd.isna(x[1])]
        if cards:
            c = st.columns(max(3, len(cards)))
            for col, (k, v, ctx) in zip(c, cards):
                kpi(col, ex, k, v, fmt_int, ctx)
        else:
            st.info("No partner numbers for these years yet.")
    # ---- partners by type of partnership (funding, employment, volunteers, events)
    pt = d.get("partner_types", pd.DataFrame())
    if not pt.empty:
        p = pt[sel.ymask(pt["year"])]
        p = p[p["year"] == p["year"].max()] if not p.empty else p
        st.markdown("##### Partners by type of partnership")
        if p.empty:
            st.info("No partnership types for these years yet.")
        else:
            p = p.sort_values("organisations", ascending=False)
            c = st.columns(len(p))
            for col, r in zip(c, p.itertuples()):
                kpi(col, ex, "partner_type", float(r.organisations), fmt_int, f"Active partners, {int(r.year)}", label=str(r.partnership_type))
            n = "One organisation can have several types (for example employment and events), so the numbers can add up to more than the active partners."
            st.caption(n)
            ex.note(n)
    top_employers(d, ex)
    if internal:
        with st.expander("Definitions used on this page"):
            definitions_table(["partners_active", "partners_new", "partner_type"])


def top_employers(d, ex, top_n=10):
    e = d.get("employers", pd.DataFrame())
    if e.empty or "company" not in e:
        return
    named = e[~e["company"].astype(str).str.lower().str.startswith("other")].sort_values("hires", ascending=False).head(top_n)
    if named.empty:
        return
    long = named.melt(id_vars="company", value_vars=[c for c in ("jobs", "internships") if c in named], var_name="type", value_name="graduates")
    long["type"] = long["type"].map({"jobs": "Job", "internships": "Internship"})
    fig = px.bar(long, x="graduates", y="company", color="type", orientation="h", color_discrete_sequence=[COLORS[0], COLORS[1]])
    fig.update_layout(barmode="stack", height=max(280, 40 * len(named) + 80), margin=dict(l=10, r=10, t=15, b=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None))
    fig.update_yaxes(categoryorder="array", categoryarray=list(named["company"])[::-1], title=None)
    fig.update_xaxes(title=None, rangemode="tozero")
    st.markdown("**Top hiring companies (all years)**")
    st.plotly_chart(fig, width="stretch", key="pa-top")
    ex.fig("Top hiring companies (all years)", fig)
    n = (f"Graduates hired per company, jobs and internships, from the employment records (first and second job). "
         f"Companies with fewer than 3 hires are not shown. Not filtered by year.")
    st.caption(n)
    ex.note(n)
