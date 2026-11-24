"""
H · Volunteers.
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


def page_volunteers(d, sel, internal, ex):
    ex.section("Volunteers", f"The mentors, coaches and hosts who teach and support our trainees · {sel.label.split(' · ')[0]}")
    team, vs_t, ve_t = d["team"], d.get("volunteer_status", pd.DataFrame()), d.get("volunteer_expertise", pd.DataFrame())
    no_cohort_note(sel)
    sample_flag(any(bool(x["is_sample"].any()) for x in (team, vs_t, ve_t) if not x.empty))
    st.markdown("##### Volunteers")
    vs = latest_in(vs_t, sel) if not vs_t.empty else vs_t
    if not vs.empty:
        vs = vs.sort_values("volunteers", ascending=False)
        c = st.columns(max(3, len(vs) + 1))
        kpi(c[0], ex, "volunteers_total", float(vs["volunteers"].sum()), fmt_int,
            " + ".join(f"{int(r.volunteers)} {str(r.status).lower()}" for r in vs.itertuples()), label="Total volunteers")
        for col, r in zip(c[1:], vs.itertuples()):
            kpi(col, ex, "volunteers", float(r.volunteers), fmt_int, f"Snapshot {r.period}", label=f"{r.status} volunteers")
    else:
        snap = latest_in(team, sel)
        c = st.columns(3)
        kpi(c[0], ex, "volunteers", None if snap.empty or pd.isna(snap["active_volunteers"].iloc[0]) else float(snap["active_volunteers"].iloc[0]), fmt_int,
            f"Snapshot {snap['period'].iloc[0]}" if not snap.empty else "No snapshot in this selection", label="Active volunteers")
    ve = latest_in(ve_t, sel) if not ve_t.empty else ve_t
    if not ve.empty:
        st.markdown("##### Active volunteers by expertise")
        ve = ve.sort_values("volunteers", ascending=False)
        fig = px.bar(ve, x="volunteers", y="expertise", orientation="h", text=ve["volunteers"].astype(int).astype(str),
                     color_discrete_sequence=["#B12900"])
        fig.update_traces(textposition="outside", cliponaxis=False, hovertemplate="%{y}: %{x} volunteers<extra></extra>")
        fig.update_layout(height=max(280, 36 * len(ve) + 60), margin=dict(l=10, r=40, t=10, b=10), showlegend=False)
        fig.update_yaxes(categoryorder="array", categoryarray=list(ve["expertise"])[::-1], title=None)
        fig.update_xaxes(title=None, rangemode="tozero")
        st.plotly_chart(fig, width="stretch", key="vo-expertise")
        ex.fig("Active volunteers by expertise", fig)
        n = (f"Active volunteers per area of expertise ({ve['period'].iloc[0]}). One volunteer can have several areas "
             "(for example Backend and Data), so the numbers add up to more than the active volunteers.")
        st.caption(n)
        ex.note(n)
    if internal:
        with st.expander("Definitions used on this page"):
            definitions_table(["volunteers", "volunteer_expertise"])
