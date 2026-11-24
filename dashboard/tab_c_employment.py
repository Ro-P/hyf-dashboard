"""
C · Employment: where graduates are now, how they found their job, IT roles, top companies.
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


# How graduates found their job: fixed figures (not from the data files, so the filters don't change them).
# Change the numbers here when there is a new count.
PATHWAYS = [("Pathway 1", "Placed via HYF", "54%", "#A3341A"), ("Pathway 2", "Found independently", "46%", "#561A0A")]


def pathways_section(ex):
    st.markdown("##### How our graduates found their job")
    cards = "".join(
        f'<div style="background:{bg};border-radius:16px;padding:26px 34px 30px;min-height:190px">'
        f'<div style="color:#FFF09E;font-weight:700;font-size:15px;letter-spacing:.04em">{html.escape(tag.upper())}</div>'
        f'<div style="color:#FFFFFF;font-weight:700;font-size:30px;margin:34px 0 10px">{html.escape(title)}</div>'
        f'<div style="color:#FFF09E;font-weight:800;font-size:72px;line-height:1">{html.escape(val)}</div></div>'
        for tag, title, val, bg in PATHWAYS)
    st.markdown(f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:20px;margin:6px 0 8px">{cards}</div>',
                unsafe_allow_html=True)
    n = "Fixed figures: share of graduates who were placed via HYF or found their job themselves. These don't change with the filters."
    st.caption(n)
    for tag, title, val, _ in PATHWAYS:
        ex.kpi(f"{tag} · {title}", val, "")
    ex.note(n)


def job_path_section(d, sel, ex):
    """Where graduates are now, from the Job path column (current status, all programmes): numbers, not percentages."""
    jp = d.get("job_paths", pd.DataFrame())
    if jp.empty:
        return
    ex.section("Where our graduates are now", f"Current job path of graduates, all programmes · {sel.label.split(' · ')[0]}")
    st.markdown("##### Where our graduates are now · all programmes")
    yrs = jp[jp["graduation_year"].astype(str) != "All"].copy()
    gy = pd.to_numeric(yrs["graduation_year"], errors="coerce")
    whole = gy.notna().any() and sel.y0 <= gy.min() and sel.y1 >= gy.max()
    r = jp[jp["graduation_year"].astype(str) == "All"] if whole else yrs[sel.ymask(yrs["graduation_year"])]
    jpc = d.get("job_paths_by_cohort", pd.DataFrame())
    by_cohort = bool(sel.cohorts) and not jpc.empty
    if by_cohort:                                         # graduates of the selected cohorts
        r, whole = jpc[sel.cmask(jpc["cohort"])], False
    elif sel.cohorts:
        st.caption("Per cohort not in the data yet: run tools/update_from_sheet.py again. Showing the selected years.")
    if r.empty:
        st.info("No graduates in this selection.")
        return
    sample_flag(bool(r["is_sample"].astype(str).str.upper().isin(["TRUE", "1"]).any())
                or any(bool(d.get(t, pd.DataFrame()).get("is_sample", pd.Series(dtype=str)).astype(str).str.upper().isin(["TRUE", "1"]).any())
                       for t in ("it_roles", "employers")))
    grads = nz(r["graduates"])
    v = {c: nz(r[c]) if c in r else None for c in JOB_LABELS}
    in_it = (v["tech_job"] or 0) + (v["internship"] or 0) if v["tech_job"] is not None or v["internship"] is not None else None
    of = f"of {fmt_int(grads)} graduates"
    hid = lambda k: (not whole) and k in r and r[k].isna().any()          # some years / cohorts with 1–4 are hidden
    of_k = lambda k: of + (f" · {'cohorts' if by_cohort else 'years'} under {SUPPRESS_BELOW} hidden" if hid(k) else "")
    c = st.columns(3)
    kpi(c[0], ex, "em_it", in_it, fmt_int, f"Tech job or internship, {of}", label="Working in IT")
    kpi(c[1], ex, "em_nontech", v["non_tech_job"], fmt_int, of_k("non_tech_job"), label="In a non-tech job")
    kpi(c[2], ex, "em_search", v["searching"], fmt_int, of_k("searching"), label="Still searching")
    n = ("Current status from the Job path column (tech job, internship, non-tech job, searching), not measured at a fixed time after graduation. "
         f"With some years or cohorts selected, groups of 1 to {SUPPRESS_BELOW - 1} are hidden for privacy; the cards include everyone when all years are selected.")
    st.caption(n)
    ex.note(n)


def top_companies_section(d, sel, ex, top_n=10):
    """Top companies that hired our graduates, with the number of graduates hired (jobs and internships). Follows the years."""
    e = d.get("employers", pd.DataFrame())
    if e.empty or "company" not in e:
        return
    rng = d.get("employers_range", pd.DataFrame())
    scope = "all years"
    if not rng.empty:
        a, b = pd.to_numeric(rng["from_year"]), pd.to_numeric(rng["to_year"])
        if not (sel.y0 <= a.min() and sel.y1 >= b.max()):            # part of the years: by job start year
            e, lo, hi = _range_row(rng, sel)
            scope = f"jobs that started in {lo}–{hi}"
    named = e[~e["company"].astype(str).str.lower().str.startswith("other")].copy()
    named["hires"] = pd.to_numeric(named["hires"], errors="coerce")
    named = named.dropna(subset=["hires"]).sort_values("hires", ascending=False).head(top_n)
    if named.empty:
        st.markdown("##### Top companies that hired our graduates")
        st.info(f"No company with 3 or more hires in {scope}.")
        return
    st.markdown(f"##### Top {len(named)} companies that hired our graduates")
    fig = px.bar(named, x="hires", y="company", orientation="h", text=named["hires"].astype(int).astype(str),
                 color_discrete_sequence=["#B12900"],
                 hover_data={c: True for c in ("jobs", "internships") if c in named})
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_layout(height=max(280, 36 * len(named) + 60), margin=dict(l=10, r=40, t=10, b=10), showlegend=False)
    fig.update_yaxes(categoryorder="array", categoryarray=list(named["company"])[::-1], title=None)
    fig.update_xaxes(title=None, rangemode="tozero")
    st.plotly_chart(fig, width="stretch", key="em-top")
    ex.fig(f"Top {len(named)} companies that hired our graduates", fig)
    n = (f"Number of graduates hired per company (jobs and internships, first and second job), {scope}. "
         "Hover over a bar to see jobs and internships separately. Companies with fewer than 3 hires are not shown."
         + (" The employment records are not linked to cohorts, so the cohort filter doesn't apply here." if sel.cohorts else ""))
    st.caption(n)
    ex.note(n)


def it_roles_section(d, sel, ex):
    """Which IT roles our graduates work in: jobs and internships per kind of role (follows the filters)."""
    r = d.get("it_roles", pd.DataFrame())
    if r.empty:
        return
    st.markdown("##### Which IT roles our graduates work in")
    rng = d.get("it_roles_range", pd.DataFrame())
    scope = "all years"
    if sel.cohorts and not d.get("it_roles_by_cohort", pd.DataFrame()).empty:
        t = d["it_roles_by_cohort"]
        r = t[sel.cmask(t["cohort"])].groupby("role_group", as_index=False)[["jobs", "internships", "total"]].sum(min_count=1)
        scope = _cohort_scope(sel)
    elif not rng.empty:
        a, b = pd.to_numeric(rng["from_year"]), pd.to_numeric(rng["to_year"])
        if not (sel.y0 <= a.min() and sel.y1 >= b.max()):            # part of the years: by job start year
            r, lo, hi = _range_row(rng, sel)
            scope = f"jobs that started in {lo}–{hi}"
    if sel.cohorts and d.get("it_roles_by_cohort", pd.DataFrame()).empty:
        scope += " (per cohort not in the data yet: run tools/update_from_sheet.py again)"
    r = r.copy()
    for c in ("jobs", "internships", "total"):
        r[c] = pd.to_numeric(r[c], errors="coerce")
    r = r.dropna(subset=["total"])
    if r.empty:
        st.info(f"Fewer than {SUPPRESS_BELOW} jobs per role in this selection, so nothing can be shown.")
        return
    st.caption(f"Showing {scope}.")
    order = list(r[r["role_group"] != "Other roles"].sort_values("total", ascending=False)["role_group"]) + \
        (["Other roles"] if (r["role_group"] == "Other roles").any() else [])
    long = r.melt(id_vars="role_group", value_vars=["jobs", "internships"], var_name="kind", value_name="n")
    long["kind"] = long["kind"].map({"jobs": "Job", "internships": "Internship"})
    fig = px.bar(long, x="n", y="role_group", color="kind", orientation="h",
                 color_discrete_map={"Job": "#B12900", "Internship": "#5E1600"},
                 hover_data={"n": True, "kind": True})
    fig.add_scatter(x=r["total"], y=r["role_group"], mode="text", text=r["total"].astype(int).astype(str),
                    textposition="middle right", showlegend=False, hoverinfo="skip", textfont=dict(color="#5E1600", size=13))
    fig.update_layout(barmode="stack", height=max(280, 38 * len(r) + 80), margin=dict(l=10, r=40, t=10, b=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None))
    fig.update_yaxes(categoryorder="array", categoryarray=order[::-1], title=None)
    fig.update_xaxes(title=None, rangemode="tozero")
    st.plotly_chart(fig, width="stretch", key="em-roles")
    ex.fig("Which IT roles our graduates work in", fig)
    n = (f"Jobs and internships per kind of role ({scope}). Roles with fewer than {SUPPRESS_BELOW} in the selection are left out. Job titles from the role column are sorted into groups by keywords "
         "(for example “React developer” → front-end). Titles that match no group, and groups with fewer than 5, are counted as other roles.")
    st.caption(n)
    ex.note(n)


def page_employment(d, sel, internal, today, ex):
    if any(bool(d.get(t, pd.DataFrame()).get("is_sample", pd.Series(dtype=str)).astype(str).str.upper().isin(["TRUE", "1"]).any())
           for t in ("it_roles", "employers")) and d.get("job_paths", pd.DataFrame()).empty:
        sample_flag(True)
    job_path_section(d, sel, ex)
    top_companies_section(d, sel, ex)
    pathways_section(ex)
    it_roles_section(d, sel, ex)
    if internal:
        with st.expander("Definitions used on this page"):
            definitions_table(["em_it", "em_nontech", "em_search"])
