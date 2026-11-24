"""
I · Visibility.
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


def page_visibility(d, sel, internal, ex):
    ex.section("Visibility & exposure", f"Reach and audience · {sel.label.split(' · ')[0]}")
    v = d["visibility"]
    no_cohort_note(sel)
    if v.empty:
        st.info("No visibility data in the workbook yet.")
        return
    sample_flag(bool(v["is_sample"].any()))
    rows = v[sel.pmask(v["period"])]
    last = latest_in(v, sel)
    one_half = sel.single and bool(sel.half)
    c = st.columns(3)
    kpi(c[0], ex, "followers", None if last.empty else float(last["linkedin_followers"].iloc[0]), fmt_int, f"At the end of {last['period'].iloc[0]}" if not last.empty else "No data yet")
    kpi(c[1], ex, "views", nz(rows["website_views"]) if not rows.empty else None, fmt_int, "Includes repeat views; added up over the selection")
    users = nz(rows["unique_website_users"]) if one_half and not rows.empty else None
    kpi(c[2], ex, "users", users, fmt_int, "Estimated by the analytics service" if one_half else "Pick one year and H1 or H2: unique users can’t be added across half-years")
    if not rows.empty:
        a, b = st.columns(2)
        with a:
            show(style(px.line(rows, x="period", y="linkedin_followers", markers=True, color_discrete_sequence=COLORS)), ex, "LinkedIn followers", "vi-li")
        long = rows.melt(id_vars="period", value_vars=["website_views", "unique_website_users"], var_name="measure", value_name="count")
        with b:
            show(style(px.bar(long, x="period", y="count", color="measure", barmode="group", color_discrete_sequence=COLORS)), ex, "Website traffic", "vi-web")
    if internal:
        with st.expander("Definitions used on this page"):
            definitions_table(["followers", "views", "users"])
