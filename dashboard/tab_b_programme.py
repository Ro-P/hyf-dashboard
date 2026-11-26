"""
B · Programme & inclusion: students supported, country of origin, education level.
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


def country_section(d, sel, ex):
    org = d.get("origin", pd.DataFrame())
    if org.empty:
        return
    o = org[sel.ymask(org["start_year"])]
    st.markdown("##### Country of origin")
    if o.empty:
        st.info("No country data for the selected years.")
        return
    known = o[~o["origin_country"].astype(str).str.lower().isin(["not recorded", "nan"])]
    total_all, answered = nz(o["trainees"]), nz(known["trainees"])
    by = known.groupby("origin_country", as_index=False)["trainees"].sum()
    by["share"] = [pct(t, answered) for t in by["trainees"]]
    other_mask = by["origin_country"].str.lower().str.startswith("other")
    by = pd.concat([by[~other_mask].sort_values("trainees", ascending=False), by[other_mask]])
    c = st.columns(2)
    top = by[~by["origin_country"].str.lower().str.startswith("other")].head(1)
    kpi(c[0], ex, "origin", None if top.empty else top["share"].iloc[0], fmt_pct,
        f"{top['origin_country'].iloc[0]} · largest group" if not top.empty else "", label="Largest group")
    kpi(c[1], ex, "origin", float(len(by[~by["origin_country"].str.lower().str.startswith("other")])), fmt_int,
        "With 5 or more trainees", label="Countries shown")
    fig = px.bar(by, x="share", y="origin_country", orientation="h", text=[f"{v:.1f}%" for v in by["share"]], color_discrete_sequence=[COLORS[0]],
                 hover_data={"trainees": True, "share": ":.1f"})
    fig.update_layout(height=max(260, 28 * len(by) + 60), margin=dict(l=10, r=10, t=15, b=10), showlegend=False)
    fig.update_yaxes(categoryorder="array", categoryarray=list(by["origin_country"])[::-1], title=None)
    fig.update_xaxes(ticksuffix="%", title=None, rangemode="tozero")
    st.markdown(f"**Share of trainees per country of origin ({sel.label.split(' · ')[0]})**")
    st.plotly_chart(fig, width="stretch", key="pr-country")
    ex.fig("Share of trainees per country of origin", fig)
    n = (f"Share of trainees who recorded a country, by the year their class started. Countries with fewer than {SUPPRESS_BELOW} trainees in a year "
         "are grouped under “Other”. Covers all classes; the cohort filter doesn't apply to this chart.")
    st.caption(n)
    ex.note(n)


def page_programme(d, sel, internal, today, ex):
    ex.section("Programme & inclusion", f"Students supported, countries of origin and education level · {sel.label}")
    shown = False
    sample_flag(any(bool(d.get(t, pd.DataFrame()).get("is_sample", pd.Series(dtype=str)).astype(str).str.upper().isin(["TRUE", "1"]).any())
                    for t in ("students_supported", "students_by_cohort", "origin_range", "education")))
    # ---- 1. country of origin: every country, with the number of trainees
    r, scope = _pick(d, sel, "origin_range", "origin_by_cohort", "country", "trainees", "class started")
    if r is not None:
        shown = True
        st.markdown("##### Country of origin")
        if r.empty:
            st.info("No country data for this selection.")
        else:
            st.markdown(f"**{len(r)} {'country' if len(r) == 1 else 'countries'}** · {scope}")
            _hbar(r, "country", "pr-country", "Trainees per country of origin", ex)
            n = (f"Number of trainees per country of origin, by the year their class started (or by cohort when cohorts are picked). "
                 f"“<{SUPPRESS_BELOW}” means fewer than {SUPPRESS_BELOW} trainees, not shown exactly to protect their privacy"
                 + (f"; per cohort, countries with fewer than {SUPPRESS_BELOW} trainees are grouped as “Other”." if sel.cohorts else "."))
            st.caption(n)
            ex.note(n)
    elif not d.get("origin", pd.DataFrame()).empty:
        shown = True
        country_section(d, sel, ex)
    # ---- 2. education level of trainees who answered
    r, scope = _pick(d, sel, "education", "education_by_cohort", "education", "trainees", "class started")
    if r is not None:
        shown = True
        st.markdown("##### Education level")
        answered = r.loc[r["education"] == "_answered", "trainees"] if not r.empty else pd.Series(dtype=float)
        total = r.loc[r["education"] == "_trainees", "trainees"] if not r.empty else pd.Series(dtype=float)
        body = r[~r["education"].astype(str).str.startswith("_")] if not r.empty else r
        if answered.empty or not nz(answered):
            st.info("Nobody answered the education question in this selection.")
        else:
            st.markdown(f"**{fmt_int(nz(answered))} of {fmt_int(nz(total))} trainees answered** · {scope}")
            _hbar(body, "education", "pr-education", "Education level (trainees who answered)", ex, color="#5E1600")
            n = (f"Number of trainees per education level, among trainees who answered, by the year their class started (or by cohort when cohorts are picked). "
                 f"Answers given by fewer than {SUPPRESS_BELOW} trainees in total are grouped as “Other”; “<{SUPPRESS_BELOW}” means fewer than {SUPPRESS_BELOW}.")
            st.caption(n)
            ex.note(n)
    # ---- 3. students supported (at the end of the page): distinct students per year, split by cohort
    ss, sc = d.get("students_supported", pd.DataFrame()), d.get("students_by_cohort", pd.DataFrame())
    if not ss.empty or not sc.empty:
        shown = True
        st.markdown("##### Students supported")
        r, lo, hi = _range_row(ss, sel)
        cl = d.get("classes", pd.DataFrame())
        if sel.cohorts and not cl.empty:
            n_c = nz(cl.loc[sel.cmask(cl["cohort"]), "started"])
            st.markdown(f"**{fmt_int(n_c)} students** started in {_cohort_scope(sel)}.")
        elif not r.empty:
            st.markdown(f"**{fmt_int(r['students'].iloc[0])} different students** were in class or in job support in {lo}–{hi}." if lo != hi
                        else f"**{fmt_int(r['students'].iloc[0])} different students** were in class or in job support in {lo}.")
        if not sc.empty:
            c = sc[sel.ymask(sc["year"]) & sel.cmask(sc["cohort"])].copy()
            c = c.dropna(subset=["students"])
            if c.empty:
                st.info("No students in this selection.")
            else:
                c["year"] = c["year"].astype(int).astype(str)
                per = {}
                for y in c["year"].unique():                          # distinct students per year (not the sum of cohorts)
                    yr, _, _ = _range_row(ss, Sel(int(y), int(y))) if not ss.empty else (pd.DataFrame(), None, None)
                    per[y] = int(yr["students"].iloc[0]) if not yr.empty and not sel.cohorts else int(c.loc[c["year"] == y, "students"].sum())
                order = sorted(c["cohort"].unique(), key=lambda x: int(str(x)[1:]) if str(x)[1:].isdigit() else 0)
                gap = [{"year": y, "cohort": f"Small groups (<{SUPPRESS_BELOW})", "students": per[y] - c.loc[c["year"] == y, "students"].sum()}
                       for y in per if per[y] - c.loc[c["year"] == y, "students"].sum() > 0]
                c = pd.concat([c, pd.DataFrame(gap)], ignore_index=True)
                pal = ["#B12900", "#5E1600", "#E0745A", "#8C2F1B", "#F2A285", "#FFD43B"]
                cmap = {k: pal[i % len(pal)] for i, k in enumerate(order)}
                cmap[f"Small groups (<{SUPPRESS_BELOW})"] = "#FFF09E"
                fig = px.bar(c, x="year", y="students", color="cohort", text="cohort", color_discrete_map=cmap,
                             category_orders={"cohort": order + [f"Small groups (<{SUPPRESS_BELOW})"], "year": sorted(per)})
                fig.update_traces(textposition="inside", insidetextanchor="middle", textfont_size=10,
                                  hovertemplate="%{x} · %{fullData.name}: %{y} students<extra></extra>")
                fig.add_scatter(x=list(per), y=list(per.values()), mode="text", text=[str(v) for v in per.values()],
                                textposition="top center", showlegend=False, hoverinfo="skip", textfont=dict(size=14, color="#5E1600"))
                fig.update_layout(barmode="stack", showlegend=False, uniformtext_minsize=8, uniformtext_mode="hide")
                show(style(fig, height=420), ex, "Students supported per year, by cohort", "pr-students")
        n = ("A student counts in every year they were in class, or in job support (up to 12 months after graduating). "
             "The number on top of each bar is the number of different students that year; the colours show their cohorts "
             f"(cohorts with fewer than {SUPPRESS_BELOW} students in a year are added together as “small groups”). Hover over a block to see its cohort.")
        st.caption(n)
        ex.note(n)
    if not shown:
        st.info("No programme data yet. Run tools/update_from_sheet.py.")
