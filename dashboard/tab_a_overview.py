"""
A · Impact overview: cards, gender, countries of origin, jobs within 6 and 12 months.
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


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #
def overview_charts(d, sel, ex):
    """Gender donut and largest countries of origin, in the HYF style (follow the year filter)."""
    st.markdown(IMPACT_CSS, unsafe_allow_html=True)
    left, right = st.columns(2, gap="medium")
    # ---- gender of graduates who answered (all_gender: per graduation year + "All" row)
    ag = d.get("all_gender", pd.DataFrame())
    with left, st.container(border=True):
        st.markdown(f'<h4 style="margin:0;color:#5E1600">Gender{_help("gender")}</h4>', unsafe_allow_html=True)
        gcb = d.get("gender_by_cohort", pd.DataFrame())
        by_cohort = bool(sel.cohorts)
        if by_cohort and gcb.empty:
            st.info("Gender per cohort is not in the data yet: run tools/update_from_sheet.py again.")
        elif ag.empty and not by_cohort:
            st.info("No gender data.")
        else:
            if by_cohort:                                   # graduates of the selected cohorts
                r, whole = gcb[sel.cmask(gcb["cohort"])], False
            else:
                yrs = ag[ag["graduation_year"].astype(str) != "All"]
                gy = pd.to_numeric(yrs["graduation_year"], errors="coerce").dropna()
                whole = not gy.empty and sel.y0 <= gy.min() and sel.y1 >= gy.max()
                r = ag[ag["graduation_year"].astype(str) == "All"] if whole else yrs[sel.ymask(yrs["graduation_year"])]
            vals = [("men", nz(r["men"]) or 0, "#5E1600"), ("women", nz(r["women"]) or 0, "#B12900"),
                    ("non-binary / other", nz(r["nonbinary_or_other"]) or 0, "#FFF09E")]
            n = sum(x[1] for x in vals)
            if not n:
                st.info("No gender answers in this selection (groups under 5 are hidden).")
            else:
                a, b = st.columns([1, 1.2])
                fig = go.Figure(go.Pie(labels=[x[0] for x in vals], values=[x[1] for x in vals], hole=0.55, sort=False,
                                       marker=dict(colors=[x[2] for x in vals], line=dict(color="#FFFFFF", width=2)),
                                       textinfo="none", hovertemplate="%{label}: %{percent}<extra></extra>", direction="clockwise"))
                fig.update_layout(height=230, margin=dict(l=0, r=0, t=0, b=0), showlegend=False)
                with a:
                    st.plotly_chart(fig, width="stretch", key="ov-gender")
                ex.fig("Gender (graduates who answered)", fig)
                # non-binary / other: 1–4 graduates are hidden in the data (privacy), so show "fewer than 5" instead of 0%
                other_hidden = bool(r["nonbinary_or_other"].isna().any())
                def _share(lbl, x):
                    if lbl.startswith("non-binary") and other_hidden:
                        return f"&lt;&nbsp;{SUPPRESS_BELOW}" if not x else f"{round(100 * x / n):.0f}%&nbsp;+"
                    return f"{round(100 * x / n):.0f}%"
                legend = "".join(f'<div><span class="sw" style="background:{col};{"border:1px solid #5E1600;" if col == "#FFF09E" else ""}"></span>'
                                 f'<b>{_share(lbl, x)}</b>&nbsp;{lbl}</div>' for lbl, x, col in vals)
                with b:
                    st.markdown(f'<div class="hyf-legend" style="padding-top:28px">{legend}</div>', unsafe_allow_html=True)
                scope = (f" (cohorts {', '.join(sel.cohorts[:6])}{' …' if len(sel.cohorts) > 6 else ''}; groups of 1–{SUPPRESS_BELOW - 1} in a cohort hidden)" if by_cohort
                         else "" if whole else f" (graduated {sel.y0}–{sel.y1}; groups of 1–{SUPPRESS_BELOW - 1} in a year hidden)")
                st.caption(f"Share of the {fmt_int(n)} graduates who answered the gender question" + scope + "."
                           + (f" Non-binary and other graduates are fewer than {SUPPRESS_BELOW}, so the exact number is not shown to protect their privacy."
                              if other_hidden else ""))
    # ---- largest countries of origin (origin: trainees per start year; small countries grouped)
    org = d.get("origin", pd.DataFrame())
    with right, st.container(border=True):
        st.markdown(f'<h4 style="margin:0 0 8px;color:#5E1600">Largest groups by country of origin{_help("origin")}</h4>', unsafe_allow_html=True)
        obc = d.get("origin_by_cohort", pd.DataFrame())
        if sel.cohorts and not obc.empty:                  # trainees of the selected cohorts
            o = obc[sel.cmask(obc["cohort"])].rename(columns={"country": "origin_country"})
            scope = f"cohorts {', '.join(sel.cohorts[:6])}{' …' if len(sel.cohorts) > 6 else ''}"
        else:
            o = org[sel.ymask(org["start_year"])] if not org.empty else org
            scope = f"started {sel.y0}–{sel.y1}" + ("; per cohort not in the data yet: run tools/update_from_sheet.py again" if sel.cohorts else "")
        o = o[~o["origin_country"].astype(str).str.lower().isin(["not recorded", "nan"])] if not o.empty else o
        if o.empty:
            st.info("No countries recorded for this selection.")
        else:
            by = o.groupby("origin_country", as_index=False)["trainees"].sum()
            recorded = float(by["trainees"].sum())
            named = by[~by["origin_country"].str.lower().str.startswith("other")].sort_values("trainees", ascending=False)
            top = named.head(4)
            mx = float(top["trainees"].max()) if not top.empty else 1
            rows = ""
            for i, r in enumerate(top.itertuples()):
                col = "#B12900" if i < 2 else "#5E1600"
                rows += (f'<div class="hyf-row"><span class="c">{html.escape(str(r.origin_country))}</span>'
                         f'<div class="bar" style="width:{100 * r.trainees / mx:.0f}%;background:{col}"></div>'
                         f'<span class="p" style="color:{col}">{100 * r.trainees / recorded:.0f}%</span></div>')
            rest = recorded - float(top["trainees"].sum())
            pill = f'<span class="hyf-pill">+ other countries · {100 * rest / recorded:.0f}%</span>' if rest > 0 else ""
            st.markdown(rows + pill, unsafe_allow_html=True)
            st.caption(f"Share of the {fmt_int(recorded)} trainees with a recorded country ({scope})."
                       + (f" Countries with fewer than {SUPPRESS_BELOW} trainees in a cohort are counted under other countries." if sel.cohorts and not obc.empty else ""))
            ex.note("Largest groups by country of origin: " + ", ".join(f"{r.origin_country} {100 * r.trainees / recorded:.0f}%" for r in top.itertuples()))


def overview_followup(d, sel, ex):
    """Graduates, and how many had a job or internship within 6 and 12 months of graduating: numbers per graduation year
    (per cohort when cohorts are picked in the filter). Follows the filters."""
    oy = d.get("outcomes_by_year", pd.DataFrame())
    by_year = not oy.empty and not sel.cohorts
    if not by_year and d.get("outcomes", pd.DataFrame()).empty:
        return
    M6, M12 = "Job within 6 months", "Job within 12 months"
    rows, sample = [], False

    def add(x, measure, v):
        ok = v is not None and not pd.isna(v)
        rows.append(dict(x=x, measure=measure, n=float(v) if ok else 0, label=f"{int(v)}" if ok else "<5"))

    if by_year:
        y = oy[sel.ymask(oy["graduation_year"])]
        sample = bool(y["is_sample"].astype(str).str.upper().isin(["TRUE", "1"]).any())
        for _, r in y.iterrows():
            if not (pd.notna(r["m6_graduates"]) and r["m6_graduates"] > 0):
                continue                                   # nobody from this year has reached 6 months yet
            x = str(int(r["graduation_year"]))
            add(x, M6, r["m6_job"])
            if pd.notna(r["m12_graduates"]) and r["m12_graduates"] > 0:
                add(x, M12, r["m12_job"])
        title, xlab = "by graduation year", "graduation year"
    else:
        o = outcomes_in(d, sel, date.today())
        o = o[o["graduation_date"].notna()]
        sample = bool(o["is_sample"].any()) if not o.empty else False
        for _, r in o.iterrows():
            if r["m6_status"] not in ("Reported", "Fewer than 5"):
                continue
            add(r["cohort"], M6, None if r["m6_status"] == "Fewer than 5" else r["m6_placed_confirmed"])
            if r["m12_status"] in ("Reported", "Fewer than 5"):
                add(r["cohort"], M12, None if r["m12_status"] == "Fewer than 5" else r["m12_paid_work_confirmed"])
        title, xlab = "by cohort", "cohort"
    with st.container(border=True):
        st.markdown(f'<h4 style="margin:0;color:#5E1600">Jobs within 6 and 12 months · {title}{_help("followup")}</h4>',
                    unsafe_allow_html=True)
        if not rows:
            st.info("No graduates in this selection have reached 6 months after graduating yet.")
            return
        sample_flag(sample)
        long = pd.DataFrame(rows)
        fig = px.bar(long, x="x", y="n", color="measure", barmode="group", text="label",
                     category_orders={"measure": [M6, M12]},
                     color_discrete_map={M6: "#B12900", M12: "#5E1600"})
        fig.update_traces(textposition="outside", cliponaxis=False, textfont_size=12,
                          hovertemplate="%{x} · %{fullData.name}: %{text}<extra></extra>")
        fig.update_yaxes(rangemode="tozero")
        show(style(fig, height=380), ex, f"Jobs within 6 and 12 months, {title}", "ov-followup")
        n = (f"Per {xlab}: number of graduates whose first job or internship started "
             "within 6 or 12 months after graduating (a job that started before graduating counts too). "
             "The 12-month bar appears once 12 months have passed."
             + (" “<5” means fewer than 5 graduates, not shown to protect privacy." if not by_year else ""))
        st.caption(n)
        ex.note(n)


def overview_all(d, sel, ex):
    """All programmes together (historic classes and C55 onwards): counts and current-status measures only."""
    cl = d.get("classes", pd.DataFrame())
    if cl.empty:
        return
    ex.section("10 years at a glance", f"All programmes, historic and new · {sel.label}")
    st.markdown("##### All programmes · historic and new")
    cl = cl[sel.cmask(cl["cohort"]) & (sel.ymask(cl["graduation_year"]) | cl["graduation_year"].isna())]
    if cl.empty:
        st.info("No classes in this selection.")
        return
    sample_flag(bool(cl["is_sample"].any()))
    started, grads, quit = nz(cl["started"]), nz(cl["graduates"]) or 0, nz(cl["quit"]) or 0
    finished = grads + quit
    rate = pct(grads, finished)
    in_it = nz(cl["working_in_it"])
    # working in or outside IT, from the job paths per graduation year (no cohort split in that table)
    jp = d.get("job_paths", pd.DataFrame())
    working, outside, jp_note = None, None, ""
    jpc = d.get("job_paths_by_cohort", pd.DataFrame())
    if sel.cohorts and not jpc.empty:                 # graduates of the selected cohorts
        r = jpc[sel.cmask(jpc["cohort"])]
        if not r.empty and r[["tech_job", "internship"]].notna().any().any():
            outside = nz(r.get("non_tech_job")) or 0
            working = (nz(r.get("tech_job")) or 0) + (nz(r.get("internship")) or 0) + outside
            if r[["tech_job", "internship", "non_tech_job"]].isna().any().any():
                jp_note = " · groups under 5 per cohort hidden"
        elif not r.empty:
            jp_note = "hidden"
    elif not jp.empty and not sel.cohorts:
        yrs = jp[jp["graduation_year"].astype(str) != "All"]
        gy = pd.to_numeric(yrs["graduation_year"], errors="coerce").dropna()
        whole = not gy.empty and sel.y0 <= gy.min() and sel.y1 >= gy.max()
        r = jp[jp["graduation_year"].astype(str) == "All"] if whole else yrs[sel.ymask(yrs["graduation_year"])]
        if not r.empty:
            it_jp = (nz(r.get("tech_job")) or 0) + (nz(r.get("internship")) or 0)
            outside = nz(r.get("non_tech_job")) or 0
            working = it_jp + outside
            if not whole and r[["tech_job", "internship", "non_tech_job"]].isna().any().any():
                jp_note = " · groups under 5 per year hidden"
    still = nz(cl["still_studying"])
    gctx = (f"{fmt_pct(rate)} graduation rate" if rate is not None else "All classes") + (f" · {fmt_int(still)} still studying" if still else "")
    org = d.get("origin", pd.DataFrame())
    o = org[sel.ymask(org["start_year"])] if not org.empty else org
    names = o["origin_country"].astype(str) if not o.empty else pd.Series(dtype=str)
    known = names[~names.str.lower().str.startswith(("other", "not recorded", "nan"))]
    c = st.columns(3)
    kpi(c[0], ex, "all_grads", grads, fmt_int, gctx, label="Graduates")
    if jp_note == "hidden":
        kpi(c[1], ex, "all_working", None, fmt_int, f"Fewer than {SUPPRESS_BELOW} per group in these cohorts, so not shown", label="Employment")
    elif working is not None:
        kpi(c[1], ex, "all_working", working, fmt_int,
            (f"{fmt_int(working - outside)} in IT · {fmt_int(outside)} outside IT (current status)" if not jp_note or outside
             else f"{fmt_int(working - outside)} in IT (current status) · outside IT: fewer than 5, not shown"), label="Employment")
    else:
        kpi(c[1], ex, "all_working", in_it, fmt_int, "In IT only: jobs outside IT are not split by cohort", label="Employment")
    oc = d.get("origin_countries", pd.DataFrame())
    ck = d.get("country_keys_by_cohort", pd.DataFrame())
    n_countries, cctx = None, "All recorded countries of origin"
    if sel.cohorts:                                    # different countries in the selected cohorts
        if ck.empty:
            cctx = "Per cohort not in the data yet: run tools/update_from_sheet.py again"
        else:
            n_countries = float(ck.loc[sel.cmask(ck["cohort"]), "country_key"].nunique())
            cctx = f"All recorded countries, cohorts {', '.join(sel.cohorts[:6])}{' …' if len(sel.cohorts) > 6 else ''}"
    elif not oc.empty:
        a, b = pd.to_numeric(oc["from_year"]), pd.to_numeric(oc["to_year"])
        lo, hi = max(sel.y0, int(a.min())), min(sel.y1, int(b.max()))
        r = oc[(a == lo) & (b == hi)]
        n_countries = float(r["countries"].iloc[0]) if not r.empty else 0.0
        cctx = f"All recorded countries, trainees who started {lo}–{hi}" if lo <= hi else "No trainees started in these years"
    elif not o.empty:
        n_countries, cctx = float(known.nunique()), "With 5 or more trainees (run update_from_sheet.py again to count all countries)"
    kpi(c[2], ex, "countries_all", n_countries, fmt_int, cctx, label="Countries of origin")
    overview_charts(d, sel, ex)
    overview_followup(d, sel, ex)
    n = "All classes together. Years filter by graduation year (countries of origin: by the year the class started)."
    st.caption(n)
    ex.note(n)


def page_overview(d, sel, internal, today, ex):
    overview_all(d, sel, ex)
    if internal:
        with st.expander("Definitions used on this page"):
            definitions_table(["all_grads", "all_working", "countries_all", "m6", "m12"])
