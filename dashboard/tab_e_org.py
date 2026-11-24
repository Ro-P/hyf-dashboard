"""
E · Organisation & community.
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


def _per_year(df, sel):
    """Last snapshot of every year in the selection (half-years 2025-H1 / 2025-H2 → 2025)."""
    if df.empty:
        return df
    x = df[sel.ymask(df["year"])].copy()
    if x.empty:
        return x
    last = x.groupby("year")["period"].transform("max")
    return x[x["period"] == last]


def page_org(d, sel, internal, ex):
    ex.section("Organisation & community", f"Team and community · {sel.label.split(' · ')[0]}")
    team, comm = d["team"], d["community"]
    no_cohort_note(sel)
    sample_flag(any(bool(x["is_sample"].any()) for x in (team, comm) if not x.empty))
    roles = (("fixed_staff", "Team members", "#B12900", "staff"), ("zzp_experts", "Experts", "#5E1600", "zzp"), ("interns", "Interns", "#FFD43B", "interns"))
    # ---- team: cards (latest snapshot) + chart over the years
    st.markdown("##### Team")
    c = st.columns(3)
    for col, (colname, label, _, k) in zip(c, roles):
        snap = latest_in(team[team[colname].notna()], sel) if colname in team else team.iloc[0:0]
        p = snap["period"].iloc[0] if not snap.empty else None
        kpi(col, ex, k, None if snap.empty else float(snap[colname].iloc[0]), fmt_int,
            f"Snapshot {p}" if p else "No snapshot in this selection", label=label)
    ty = _per_year(team, sel)
    if not ty.empty:
        long = ty.melt(id_vars="year", value_vars=[r[0] for r in roles if r[0] in ty], var_name="role", value_name="people").dropna()
        long["role"] = long["role"].map({r[0]: r[1] for r in roles})
        long["year"] = long["year"].astype(int).astype(str)
        fig = px.bar(long, x="year", y="people", color="role", barmode="group", text="people",
                     color_discrete_map={r[1]: r[2] for r in roles}, category_orders={"role": [r[1] for r in roles]})
        fig.update_traces(textposition="outside", cliponaxis=False)
        fig.update_layout(bargap=0.55 if long["year"].nunique() < 3 else 0.2)       # narrower bars while there are few years
        show(style(fig, height=340), ex, "Team over the years", "or-team")
    # ---- community: cards (latest) + growth chart per platform
    cs = latest_in(comm, sel)
    if not cs.empty:
        st.markdown("##### Community")
        c = st.columns(max(2, len(cs)))
        for col, (_, r) in zip(c, cs.iterrows()):
            kpi(col, ex, "community", float(r["members"]), fmt_int, f"Snapshot {r['period']}", label=str(r["platform"]))
    cy = _per_year(comm, sel)
    if not cy.empty:
        cy = cy.sort_values("year").copy()
        cy["year"] = cy["year"].astype(int).astype(str)
        est = cy["estimate"].astype(str).str.upper().isin(["TRUE", "1"]) if "estimate" in cy else pd.Series(False, index=cy.index)
        colors = {p: c for p, c in zip(sorted(cy["platform"].unique()), ["#B12900", "#5E1600", "#FFD43B"])}
        fig = go.Figure()
        for plat, part in cy.groupby("platform"):
            e = est.loc[part.index]
            fig.add_scatter(x=part["year"], y=part["members"], mode="lines", name=plat, line=dict(color=colors[plat], width=3, dash="dot"),
                            hoverinfo="skip", showlegend=True)
            for is_est, sub in ((True, part[e]), (False, part[~e])):
                if sub.empty:
                    continue
                fig.add_scatter(x=sub["year"], y=sub["members"], mode="markers+text", showlegend=False,
                                text=[f"{v:,.0f}" for v in sub["members"]], textposition="top center",
                                marker=dict(size=9 if is_est else 13, color="#FFFFFF" if is_est else colors[plat], line=dict(color=colors[plat], width=2)),
                                hovertemplate=f"{plat} · %{{x}}: %{{y:,.0f}}" + (" (estimate)" if is_est else "") + "<extra></extra>")
        fig.update_yaxes(rangemode="tozero")
        fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None))
        show(style(fig, height=360), ex, "Community growth", "or-comm")
        if est.any():
            yrs = sorted(cy.loc[est, "year"])
            m = (f"Open dots ({yrs[0]}–{yrs[-1]}) are estimates, not measured numbers, to show the gradual growth; "
                 "filled dots are real numbers. Replace the estimates in update_from_sheet.py when real numbers are known.")
            st.caption(m)
            ex.note(m)
        elif cy["year"].nunique() == 1:
            st.caption("Only one year so far. Each run of update_from_sheet.py adds the current numbers; "
                       "earlier years can be added in the script (COMMUNITY_HISTORY) or in a Community tab with a Year column.")
    n = ("Cards show the last snapshot in the selection; charts show the last snapshot of each year. Snapshots are never added up, "
         "and each platform is shown separately (one person can follow on LinkedIn and be in Slack).")
    st.caption(n)
    ex.note(n)
    if internal:
        with st.expander("Definitions used on this page"):
            definitions_table(["staff", "zzp", "interns", "community"])
