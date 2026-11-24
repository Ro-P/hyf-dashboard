"""
D · Historic programme (classes before C55).
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


def page_historic(d, sel, internal, today, ex):
    h = d["historic"].copy()
    hg = d.get("historic_gender", pd.DataFrame())
    ex.section("Historic programme (before C55)", f"Old definitions; not added to or compared with new-programme figures · {sel.label}")
    st.info(f"Historic programme (classes before C55), graduation years up to {HISTORIC_LAST_YEAR}. These results use the old definitions and are not compared with new-programme figures. "
            "Years filter by graduation year; the half-year choice doesn't apply here.")
    if h.empty:
        return
    full_h = h
    h = h[sel.cmask(h["cohort"]) & (sel.ymask(h["graduation_year"]) | h["graduation_year"].isna())]
    if h.empty:
        st.info("No historic classes in this selection.")
        return
    sample_flag(bool(h["is_sample"].any()))
    has = lambda col: col in h.columns and h[col].notna().any()
    grads = nz(h["graduates"]) or 0
    c = st.columns(3)
    kpi(c[0], ex, "h_grad", grads, fmt_int, f"{len(h)} classes · {fmt_int(nz(h['started']))} started")
    if has("working_in_it"):
        kpi(c[1], ex, "h_it", pct(nz(h["working_in_it"]), grads), fmt_pct, f"{fmt_int(nz(h['working_in_it']))} graduates with a tech job or internship (current status)")
    else:
        h["eligible"] = h["graduation_date"].notna() & ((h["graduation_date"] + pd.DateOffset(months=6)) <= pd.Timestamp(today)) & (h["graduates"] > 0)
        el = h[h["eligible"]]
        kpi(c[1], ex, "h_m6", pct(nz(el["placed_6m_confirmed"]), nz(el["graduates"])), fmt_pct,
            f"{fmt_int(nz(el['placed_6m_confirmed']))} of {fmt_int(nz(el['graduates']))} graduates")
    # gender is only available per graduation year (counts under 5 hidden)
    if hg.empty:
        kpi(c[2], ex, "h_women", pct(nz(h.get("women_graduates")), nz(h.get("gender_responses"))), fmt_pct, "Gender was not recorded in this data")
    elif sel.cohorts:
        kpi(c[2], ex, "h_women", None, fmt_pct, "Gender is only available per year, not per cohort")
    else:
        yrs = hg[hg["graduation_year"].astype(str) != "All"]
        all_years = sorted(pd.to_numeric(full_h["graduation_year"], errors="coerce").dropna().astype(int).unique())
        whole = bool(all_years) and sel.y0 <= all_years[0] and sel.y1 >= all_years[-1]
        if whole and not hg.attrs.get("capped"):
            r = hg[hg["graduation_year"].astype(str) == "All"]
            w, n = (float(r["women"].iloc[0]), float(r["gender_responses"].iloc[0])) if not r.empty else (None, None)
        else:
            r = yrs[sel.ymask(yrs["graduation_year"])]
            w, n = nz(r["women"]), nz(r["gender_responses"])
        kpi(c[2], ex, "h_women", pct(w, n) if n else None, fmt_pct,
            f"{fmt_int(w)} of {fmt_int(n)} graduates who answered the gender question" if n else "No gender answers in these years")
    yr = h.groupby("graduation_year", as_index=False)[[x for x in ("graduates", "working_in_it", "placed_6m_confirmed") if x in h.columns]].sum(min_count=1)
    yr = yr.dropna(subset=["graduation_year"])
    yr["graduation_year"] = yr["graduation_year"].astype(int).astype(str)
    a, b = st.columns(2)
    with a:
        show(style(px.bar(yr, x="graduation_year", y="graduates", color_discrete_sequence=COLORS)), ex, "Graduates per year", "hi-grad")
    with b:
        if has("working_in_it"):
            yr["Working in IT"] = [pct(x, g) for x, g in zip(yr["working_in_it"], yr["graduates"])]
            show(style(px.line(yr, x="graduation_year", y="Working in IT", markers=True, color_discrete_sequence=COLORS), y_pct=True), ex, "Graduates working in IT, by graduation year", "hi-it")
        else:
            yr["6-month placement"] = [pct(x, g) for x, g in zip(yr["placed_6m_confirmed"], yr["graduates"])]
            show(style(px.line(yr, x="graduation_year", y="6-month placement", markers=True, color_discrete_sequence=COLORS), y_pct=True), ex, "Historic 6-month placement rate per year", "hi-rate")
    if not hg.empty and not sel.cohorts:
        gy = hg[hg["graduation_year"].astype(str) != "All"].copy()
        gy = gy[sel.ymask(gy["graduation_year"])]
        gy["% women"] = [pct(w, n) if pd.notna(n) and n >= 5 else None for w, n in zip(gy["women"], gy["gender_responses"])]
        gy = gy[gy["% women"].notna()]
        if not gy.empty:
            show(style(px.bar(gy, x="graduation_year", y="% women", color_discrete_sequence=[COLORS[3]]), y_pct=True), ex, "Women among graduates who answered, by graduation year", "hi-women")
    notes = []
    if has("working_in_it"):
        notes.append("“Working in IT” is each graduate's current status (tech job or internship), not a 6- or 12-month measurement. The 6-month placement rate is not shown because job start dates are not in this data.")
    if not hg.empty:
        notes.append("Gender was mostly not recorded before 2020. Counts under 5 are hidden, so shares can differ slightly from the full data.")
    for n in notes:
        st.caption(n)
        ex.note(n)
    if internal:
        st.markdown("**Per class (internal)**")
        st.dataframe(h.drop(columns=[x for x in ("eligible",) if x in h.columns]), hide_index=True, width="stretch")
        with st.expander("Definitions used on this page"):
            definitions_table(["h_grad", "h_it", "h_women"])
