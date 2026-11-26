"""
F · Finance.
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


def page_finance(d, sel, internal, ex):
    ex.section("Finance", f"Annual financial indicators · {sel.label.split(' · ')[0]}")
    fin = d["finance"].copy()
    no_cohort_note(sel)
    if fin.empty:
        st.info("No finance data in the workbook yet.")
        return
    sample_flag(bool(fin["is_sample"].any()))
    if "status" not in fin:
        fin["status"] = "actual"
    fin["status"] = fin["status"].fillna("actual").astype(str).str.lower()
    if "grants_eur" not in fin:
        fin["grants_eur"] = None
    f = fin[sel.ymask(fin["year"])]
    act = f[f["status"] == "actual"]                       # cards: actual figures only, no forecast or budget
    tot = nz(act["total_income_eur"]) if not act.empty else None
    op = nz(act["operational_income_eur"]) if not act.empty else None
    gr = nz(act["grants_eur"]) if not act.empty and act["grants_eur"].notna().any() else None
    yrs = sorted(act["year"].astype(int).unique()) if not act.empty else []
    span = (f"Financial year {yrs[0]}" if len(yrs) == 1 else f"Financial years {yrs[0]}–{yrs[-1]}, added up") if yrs else ""
    euro = lambda v: NA if v is None else f"€{v:,.0f}"
    c = st.columns(3)
    kpi(c[0], ex, "income", tot, euro, span or "No closed financial year in this selection")
    tgt = None
    if not d["targets"].empty:
        t = d["targets"][d["targets"]["indicator"] == "operational_income_pct"]
        tgt = None if t.empty else (int(t["year"].iloc[0]), float(t["target"].iloc[0]))
    kpi(c[1], ex, "op_income", pct(op, tot), fmt_pct,
        (f"{euro(op)} from operations" if op else "Not reported yet") + (f" · target {tgt[0]}: {tgt[1]:g}%" if tgt else ""))
    kpi(c[2], ex, "grants", gr, euro, span or "", label="Placement fees")
    if not f.empty:
        fl = f.copy()
        fl["label"] = [f"{int(y)}" + ("" if s == "actual" else f" ({s})") for y, s in zip(fl["year"], fl["status"])]
        fl["other_eur"] = (fl["total_income_eur"] - fl["operational_income_eur"] - fl["grants_eur"].fillna(0)).clip(lower=0)
        fl["operational_pct"] = [pct(a, b) for a, b in zip(fl["operational_income_eur"], fl["total_income_eur"])]
        a, b = st.columns(2)
        parts = [("operational_income_eur", "Operational income", "#B12900"), ("grants_eur", "Placement fees", "#5E1600"), ("other_eur", "Other income", "#FFD43B")]
        fig = go.Figure()
        for colname, name, colr in parts:
            if fl[colname].fillna(0).sum() > 0:
                fig.add_bar(x=fl["label"], y=fl[colname], name=name, marker_color=colr,
                            marker_pattern_shape=["" if s == "actual" else "/" for s in fl["status"]])
        fig.add_scatter(x=fl["label"], y=fl["total_income_eur"], mode="text", showlegend=False, hoverinfo="skip",
                        text=[f"€{v / 1000:,.0f}k" for v in fl["total_income_eur"]], textposition="top center", textfont=dict(color="#5E1600"))
        fig.update_layout(barmode="stack")
        fig.update_yaxes(tickprefix="€")
        with a:
            show(style(fig), ex, "Income by year", "fi-income")
        fig = px.line(fl, x="label", y="operational_pct", markers=True, color_discrete_sequence=["#B12900"])
        if tgt:
            fig.add_hline(y=tgt[1], line_dash="dash", line_color="#888", annotation_text=f"Target {tgt[0]}: {tgt[1]:g}%")
        with b:
            show(style(fig, y_pct=True), ex, "Operational income as % of total", "fi-op")
    n = ("Cards add up closed financial years only. In the charts, forecast and budget years are labelled and striped. "
         "Finance is reported per financial year, so the half-year choice doesn't change these figures.")
    st.caption(n)
    ex.note(n)
    if internal:
        with st.expander("Definitions used on this page"):
            definitions_table(["income", "op_income", "grants"])
