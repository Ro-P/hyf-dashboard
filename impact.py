"""
HYF Impact Dashboard (pages A–F) for the Streamlit app.

Reads data/HYF_indicators.xlsx and calculates every indicator the way the
HYF Indicator Overview & Measurement Dictionary v1.3 defines it.
Public view = aggregate figures for external use; Internal view adds
counts, coverage, data-quality notes and definitions.
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

import brand

COLORS = brand.CHART_COLORS  # HYF palette, set in brand.py
MUTED = brand.MUTED
brand.apply_plotly_theme()
SUPPRESS_BELOW = int(os.getenv("SUPPRESS_BELOW", "5"))  # privacy threshold for small groups
NA = "Not available"

# --------------------------------------------------------------------------- #
# Definitions (Measurement Dictionary v1.3)
# --------------------------------------------------------------------------- #
DEFS = {
    "students": ("Students Supported", "Unique students enrolled or receiving documented job-search support within 12 months of graduation during the period.", "Deduplicated count of eligible students with active enrolment or documented support.", "Annual", "Student administration and alumni support log"),
    "women": ("% Women", "Share identifying as women among valid voluntary gender respondents within the selected population.", "Women responses ÷ valid gender responses × 100.", "Half-yearly", "Intake questionnaire"),
    "lgbtq": ("% LGBTQ+", "Share voluntarily self-identifying as LGBTQ+ among valid responses to that question.", "LGBTQ+ responses ÷ valid LGBTQ+ responses × 100. Hidden when fewer than five people.", "Half-yearly", "Voluntary intake questionnaire"),
    "satisfaction": ("Student Satisfaction", "Average student score for educational session evaluations on a 1–5 scale.", "Sum of valid evaluation scores ÷ number of valid scores.", "Half-yearly", "Session evaluation forms"),
    "m6": ("6-month Placement Rate", "Share entering a paid IT job or internship within six months following graduation.", "Confirmed placements within 6 months ÷ all graduates in eligible cohorts × 100.", "By cohort; half-yearly", "Job placement tracking and graduate follow-up"),
    "m12": ("12-month Job Rate", "Share holding a paid IT job or qualifying paid internship at the 12-month follow-up.", "Confirmed paid work at month 12 ÷ all graduates in eligible cohorts × 100.", "By cohort; half-yearly", "Alumni follow-up / placement records"),
    "coverage": ("Employment Follow-up Coverage", "Share of eligible graduates with a verified employment status at the milestone.", "Graduates with verified status ÷ all eligible graduates × 100.", "6 and 12 months", "Alumni survey and verified follow-up records"),
    "h_m6": ("Historic 6-month Placement Rate", "Share of graduates who found a paid job or internship with documented intent to hire within six months after graduation.", "Confirmed placements within 6 months ÷ all graduates from eligible historic cohorts × 100. Unknown statuses stay in the denominator.", "Annual / cohort", "Historic job placement and alumni records"),
    "h_grad": ("Historic People Graduated", "Unique people successfully completing the historic programme in the reporting period.", "Count unique successful graduates once on completion.", "Annual / cohort", "Historic graduation records"),
    "h_rate": ("Graduation rate", "Share of trainees who finished their course and graduated.", "Graduates ÷ (graduates + quit) × 100. Trainees still studying or on hold are not counted.", "Annual / cohort", "Dojo trainee export"),
    "h_it": ("Graduates working in IT", "Graduates whose current status is a tech job or an internship.", "Graduates with a tech job or internship ÷ all graduates × 100. Current status, not measured at a fixed time after graduation.", "Current status", "Dojo trainee export"),
    "h_women": ("Historic % Women", "Share identifying as women among respondents with valid voluntary gender answers.", "Valid women-identifying responses ÷ all valid gender responses × 100.", "Annual / cohort", "Historic intake records"),
    "op_income": ("Operational Income %", "Share of recognised income earned from operations and qualifying public/private contracts.", "Operational earned income ÷ total recognised income × 100. Grants, gifts and subsidies are excluded from the numerator.", "Annual", "Financial statements"),
    "income": ("Total Income", "All recognised income during the financial year, across revenue types.", "Sum of operational income, grants, subsidies, donations and other income.", "Annual", "Annual accounts"),
    "staff": ("Fixed Staff", "Individuals employed by HYF under an employment contract on the reporting date.", "Active employee headcount; excludes ZZP experts and interns.", "Half-yearly snapshot", "HR records"),
    "zzp": ("External Experts (ZZP)", "Self-employed experts with active HYF contracts on the reporting date.", "Count of active contracted individuals.", "Half-yearly snapshot", "Contract administration"),
    "interns": ("Interns", "Individuals actively interning at HYF on the reporting date.", "Count of people on active internship agreements.", "Half-yearly snapshot", "HR / internship records"),
    "volunteers": ("Active Volunteers", "Unique volunteers with at least one logged activity and required compliance documentation (COC + VOG).", "Unique compliant volunteers with recorded activity in the period.", "H1, H2, annual", "Volunteer activity / VOG records"),
    "partners_active": ("Active partners", "Companies and organisations with an active partnership with HYF during the year (to be agreed).", "Count of partners with an agreement or joint activity in the year.", "Annual", "Partnership records"),
    "partners_new": ("New partners", "Partners that started working with HYF during the year (to be agreed).", "Count of partners whose first agreement or activity falls in the year.", "Annual", "Partnership records"),
    "partners_hiring": ("Hiring partners", "Partners that hired at least one HYF graduate during the year (to be agreed).", "Count of partners with at least one graduate hire (job or internship) in the year.", "Annual", "Placement records"),
    "partners_hired": ("Graduates hired by partners", "Graduates who started a job or internship at a partner during the year (to be agreed).", "Count of graduate hires at partners in the year, each graduate once.", "Annual", "Placement records"),
    "origin": ("Country of origin", "Share of trainees per country of origin, among trainees who recorded a country.", "Trainees from a country ÷ trainees with a recorded country × 100. Countries with fewer than 5 trainees in a year are grouped as Other.", "Annual (by class start year)", "Dojo trainee export"),
    "community": ("Community Members", "Registered members of HYF community platforms such as Dojo and the LinkedIn group.", "Registration count at reporting date, per platform.", "Half-yearly snapshot", "Dojo / LinkedIn community records"),
    "followers": ("LinkedIn Followers", "Followers of HYF's official company page at the reporting date.", "Platform-reported follower total (snapshot, not new follows).", "Half-yearly snapshot", "LinkedIn Analytics"),
    "views": ("Website Views", "All website page views during the period, including repeat views.", "Analytics page-view count for the period. Views are not people.", "Half-yearly", "Website analytics"),
    "users": ("Unique Website Users", "Distinct website users estimated by the analytics service.", "Analytics-reported distinct users. Technical estimate; cannot be added across half-years.", "Half-yearly", "Website analytics"),
}


def help_text(key: str) -> str:
    name, definition, measure, freq, source = DEFS[key]
    return f"**{name}** — {definition}\n\nCalculation: {measure}\n\nFrequency: {freq} · Source: {source}"


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #
SHEETS = ["inclusion", "students_annual", "outcomes", "historic", "historic_gender", "targets", "finance", "team", "community", "visibility", "partners", "volunteers", "origin"]


@st.cache_data(show_spinner=False)
def load_indicators(path: str, mtime: float) -> dict[str, pd.DataFrame]:
    xl = pd.read_excel(path, sheet_name=None)
    out = {}
    for name in SHEETS:
        df = xl.get(name, pd.DataFrame()).copy()
        df.columns = [str(c).strip() for c in df.columns]
        df = df.dropna(how="all")
        if "is_sample" in df.columns:
            df["is_sample"] = df["is_sample"].astype(str).str.upper().isin(["TRUE", "1", "YES"])
        else:
            df["is_sample"] = False
        for c in df.columns:
            if "date" in c:
                df[c] = pd.to_datetime(df[c], errors="coerce")
        if "period" in df.columns:
            df["period"] = df["period"].astype(str).str.strip().str.upper().str.replace(" ", "-")
            df["year"] = df["period"].str[:4].astype(int)
        out[name] = df
    return out


def pct(a, b):
    if a is None or b is None or pd.isna(a) or pd.isna(b) or b == 0:
        return None
    return round(float(a) / float(b) * 100, 1)


def half_of(d) -> str | None:
    if d is None or pd.isna(d):
        return None
    return f"{d.year}-H{1 if d.month <= 6 else 2}"


def nz(series) -> float | None:
    s = pd.to_numeric(series, errors="coerce")
    return None if s.notna().sum() == 0 else float(s.sum())


@dataclass
class Sel:
    """What the filters at the top select: a year range, optionally one half-year, optionally some cohorts."""
    y0: int
    y1: int
    half: str | None = None          # "H1", "H2" or None (full years)
    cohorts: list = field(default_factory=list)

    @property
    def year(self) -> int:           # the year used for targets and annual snapshots
        return self.y1

    @property
    def single(self) -> bool:
        return self.y0 == self.y1

    @property
    def label(self) -> str:
        yrs = str(self.y0) if self.single else f"{self.y0}–{self.y1}"
        lab = (f"{self.half} " if self.half else "") + yrs
        if self.cohorts:
            shown = ", ".join(self.cohorts[:6]) + (f" +{len(self.cohorts) - 6}" if len(self.cohorts) > 6 else "")
            lab += f" · cohorts {shown}"
        return lab

    @property
    def key(self) -> str:
        return (f"{self.y0}" if self.single else f"{self.y0}-{self.y1}") + (f"_{self.half}" if self.half else "") + ("_cohorts" if self.cohorts else "")

    def pmask(self, periods: pd.Series) -> pd.Series:
        """Rows whose period (e.g. 2025-H1) falls inside the selection."""
        y = pd.to_numeric(periods.astype(str).str[:4], errors="coerce")
        m = y.between(self.y0, self.y1)
        if self.half:
            m &= periods.astype(str).str.endswith(self.half)
        return m

    def ymask(self, years: pd.Series) -> pd.Series:
        return pd.to_numeric(years, errors="coerce").between(self.y0, self.y1)

    def date_ok(self, d) -> bool:
        hp = half_of(d)
        return hp is not None and bool(self.pmask(pd.Series([hp])).iloc[0])

    def cmask(self, cohorts: pd.Series) -> pd.Series:
        return cohorts.isin(self.cohorts) if self.cohorts else pd.Series(True, index=cohorts.index)


def latest_in(df: pd.DataFrame, sel: Sel) -> pd.DataFrame:
    """Rows of the last snapshot period inside the selection."""
    if df.empty or "period" not in df:
        return df.iloc[0:0]
    s = df[sel.pmask(df["period"])]
    if s.empty:
        return s
    return s[s["period"] == s["period"].max()]


def no_cohort_note(sel: Sel):
    if sel.cohorts:
        st.caption("ℹ️ The cohort filter doesn't apply to this page; it uses the year filter only.")


# --------------------------------------------------------------------------- #
# Indicator calculations
# --------------------------------------------------------------------------- #
def calc_inclusion(d, sel: Sel):
    inc = d["inclusion"]
    rows = inc[sel.pmask(inc["period"]) & sel.cmask(inc["cohort"])] if not inc.empty else inc
    # each cohort's latest response inside the selection, so nobody is counted twice
    demo = rows.sort_values("period").groupby("cohort").tail(1) if not rows.empty else rows
    res = {"sample": bool(rows["is_sample"].any()) if not rows.empty else False}
    if sel.single and not sel.half and not sel.cohorts:
        sa = d["students_annual"]
        r = sa[sa["year"] == sel.year] if not sa.empty else sa
        res["students"] = None if r.empty or pd.isna(r["students_supported"].iloc[0]) else int(r["students_supported"].iloc[0])
        res["students_note"] = "Annual unique count" if res["students"] is not None else "Annual figure is published after the year closes"
        res["sample"] |= bool(r["is_sample"].any()) if not r.empty else False
    elif sel.single and sel.half:
        res["students"] = None if rows.empty else int(rows["students"].sum())
        res["students_note"] = f"Students active in {sel.half} {sel.year}" if res["students"] is not None else "No data for this period"
    else:
        res["students"] = None if rows.empty else int(rows.groupby("cohort")["students"].max().sum())
        res["students_note"] = ("Students in the selected cohorts, each cohort counted once" if res["students"] is not None
                                else "No data for this selection")
    g, w = nz(demo.get("gender_responses")), nz(demo.get("women"))
    lr, lg = nz(demo.get("lgbtq_responses")), nz(demo.get("lgbtq"))
    res.update(
        gender_responses=g, women_pct=pct(w, g), gender_coverage=pct(g, nz(demo.get("students"))),
        lgbtq_responses=lr, lgbtq_hidden=lg is not None and lg < SUPPRESS_BELOW,
        lgbtq_pct=None if lg is None or lg < SUPPRESS_BELOW else pct(lg, lr),
        lgbtq_coverage=pct(lr, nz(demo.get("students"))),
    )
    ss, sn = nz(rows.get("satisfaction_score_sum")), nz(rows.get("satisfaction_responses"))
    res["satisfaction"] = None if not sn else round(ss / sn, 2)
    res["satisfaction_n"] = sn
    return res


def outcome_table(d, today: date) -> pd.DataFrame:
    o = d["outcomes"].copy()
    if o.empty:
        return o
    o["m6_due"] = o["graduation_date"] + pd.DateOffset(months=6)
    o["m12_due"] = o["graduation_date"] + pd.DateOffset(months=12)
    for m, ok, ver in (("m6", "m6_placed_confirmed", "m6_status_verified"), ("m12", "m12_paid_work_confirmed", "m12_status_verified")):
        elapsed = o[f"{m}_due"].notna() & (o[f"{m}_due"] <= pd.Timestamp(today))
        reported = elapsed & o[ok].notna()
        o[f"{m}_reported"] = reported
        o[f"{m}_rate"] = [pct(a, b) if r else None for a, b, r in zip(o[ok], o["graduates"], reported)]
        o[f"{m}_coverage"] = [pct(a, b) if r else None for a, b, r in zip(o[ver], o["graduates"], reported)]
        o[f"{m}_status"] = [
            "Reported" if r else ("Not yet due" if not e else "Due — not reported yet") if pd.notna(g) else "In programme"
            for r, e, g in zip(reported, elapsed, o["graduation_date"])
        ]
    return o


def outcomes_in(d, sel: Sel, today) -> pd.DataFrame:
    """Cohorts for the charts and tables: selected cohorts, graduating inside the year range (or still in programme)."""
    o = outcome_table(d, today)
    if o.empty:
        return o
    gy = o["graduation_date"].dt.year
    return o[sel.cmask(o["cohort"]) & (gy.between(sel.y0, sel.y1) | gy.isna())]


def calc_employment(d, sel: Sel, today):
    o = outcome_table(d, today)
    if not o.empty:
        o = o[sel.cmask(o["cohort"])]
    res = {}
    for m, ok, ver in (("m6", "m6_placed_confirmed", "m6_status_verified"), ("m12", "m12_paid_work_confirmed", "m12_status_verified")):
        if o.empty:
            res[m] = dict(rate=None, coverage=None, eligible=None, confirmed=None, verified=None, cohorts="", pending="", sample=False)
            continue
        due = o[[sel.date_ok(x) for x in o[f"{m}_due"]]]
        rep = due[due[f"{m}_reported"]]
        eligible = nz(rep["graduates"]) if not rep.empty else None
        res[m] = dict(
            rate=pct(nz(rep[ok]), eligible) if eligible else None,
            coverage=pct(nz(rep[ver]), eligible) if eligible else None,
            eligible=eligible, confirmed=nz(rep[ok]) if eligible else None, verified=nz(rep[ver]) if eligible else None,
            cohorts=", ".join(rep["cohort"]), pending=", ".join(due[~due[f"{m}_reported"]]["cohort"]),
            sample=bool(due["is_sample"].any()),
        )
    return res


def target(d, indicator, year):
    t = d["targets"]
    if t.empty:
        return None
    r = t[(t["indicator"] == indicator) & (t["year"].astype(str) == str(year))]
    return None if r.empty else float(r["target"].iloc[0])


# --------------------------------------------------------------------------- #
# Rendering helpers
# --------------------------------------------------------------------------- #
@dataclass
class Export:
    sections: list = field(default_factory=list)

    def section(self, title, intro=""):
        self.sections.append({"title": title, "intro": intro, "kpis": [], "figs": [], "notes": []})

    def kpi(self, label, value, ctx):
        self.sections[-1]["kpis"].append((label, value, ctx))

    def fig(self, title, fig):
        self.sections[-1]["figs"].append((title, fig))

    def note(self, text):
        self.sections[-1]["notes"].append(text)


def fmt_pct(v):
    return NA if v is None else f"{v:.1f}%"


def fmt_int(v):
    return NA if v is None else f"{int(round(v)):,}"


def kpi(col, ex: Export, key, value, fmt, ctx, tgt=None, unit_pts=True, label=None):
    label = label or DEFS[key][0]
    shown = fmt(value)
    delta = None
    if tgt is not None and value is not None:
        diff = value - tgt
        delta = f"{diff:+.1f} {'pts ' if unit_pts else ''}vs target {tgt:g}{'%' if unit_pts else ''}"
    col.metric(label, shown, delta=delta, help=help_text(key), border=True)
    if ctx:
        col.caption(ctx)
    ex.kpi(label, shown, ctx)


def style(fig, title=None, height=320, y_pct=False):
    fig.update_layout(
        template="hyf", height=height, title=title, margin=dict(l=10, r=10, t=50 if title else 15, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None), hovermode="x unified",
    )
    if y_pct:
        fig.update_yaxes(ticksuffix="%", rangemode="tozero")
    fig.update_xaxes(type="category", title=None, categoryorder="category ascending")
    fig.update_yaxes(title=None)
    return fig


def show(fig, ex: Export, title, key):
    st.markdown(f"**{title}**")
    st.plotly_chart(fig, width="stretch", key=key)
    ex.fig(title, fig)


def sample_flag(is_sample: bool):
    if is_sample:
        st.warning("This page includes **sample placeholder rows** (is_sample = TRUE in the workbook). Do not share it externally until they are replaced.", icon="⚠️")


def definitions_table(keys):
    st.dataframe(
        pd.DataFrame([dict(Indicator=DEFS[k][0], Definition=DEFS[k][1], Calculation=DEFS[k][2], Frequency=DEFS[k][3], Source=DEFS[k][4]) for k in keys]),
        hide_index=True, width="stretch",
    )


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #
def page_overview(d, sel, internal, today, ex):
    inc, emp = calc_inclusion(d, sel), calc_employment(d, sel, today)
    ex.section("Impact overview", f"New programme (C55 onwards) · {sel.label}")
    sample_flag(inc["sample"] or emp["m6"]["sample"] or emp["m12"]["sample"])
    c = st.columns(3)
    kpi(c[0], ex, "students", inc["students"], fmt_int, inc["students_note"])
    kpi(c[1], ex, "women", inc["women_pct"], fmt_pct,
        f"Of {fmt_int(inc['gender_responses'])} valid responses · {fmt_pct(inc['gender_coverage'])} coverage" if inc["gender_responses"] else "No responses in this selection",
        target(d, "women_pct", sel.year))
    kpi(c[2], ex, "lgbtq", inc["lgbtq_pct"], fmt_pct,
        ("Hidden: fewer than five people · " if inc["lgbtq_hidden"] else "Of ") + f"{fmt_int(inc['lgbtq_responses'])} valid responses" if inc["lgbtq_responses"] else "No responses in this selection")
    c = st.columns(3)
    kpi(c[0], ex, "satisfaction", inc["satisfaction"], lambda v: NA if v is None else f"{v:.1f} / 5",
        f"{fmt_int(inc['satisfaction_n'])} valid evaluations" if inc["satisfaction_n"] else "No evaluations in this selection",
        target(d, "satisfaction", sel.year), unit_pts=False)
    for col, m in ((c[1], "m6"), (c[2], "m12")):
        e = emp[m]
        ctx = (f"{fmt_int(e['eligible'])} graduates ({e['cohorts']}) · {fmt_pct(e['coverage'])} followed up" if e["eligible"]
               else f"Pending: {e['pending']}" if e["pending"] else "No cohort reached this point in the selection")
        kpi(col, ex, m, e["rate"], fmt_pct, ctx, target(d, f"{m}_rate", sel.year))
    o = outcomes_in(d, sel, today)
    rep = o[o["m6_reported"]] if not o.empty else o
    if not rep.empty:
        long = rep.melt(id_vars="cohort", value_vars=["m6_rate", "m12_rate"], var_name="measure", value_name="rate")
        long["measure"] = long["measure"].map({"m6_rate": "6-month placement", "m12_rate": "12-month job rate"})
        fig = px.bar(long, x="cohort", y="rate", color="measure", barmode="group", color_discrete_sequence=COLORS)
        show(style(fig, y_pct=True), ex, "Employment results by cohort", "ov-emp")
    st.markdown("**Reading these figures**")
    notes = ["Employment rates only include cohorts whose 6- or 12-month window falls in the selected years and has passed. Cohorts still in the programme are never counted as zero.",
             "Missing data is shown as “Not available”, not 0.",
             "Targets shown are for the last year in the selection.",
             "Historic results (before C55) use different definitions and are on page D."]
    for n in notes:
        st.markdown(f"- {n}")
        ex.note(n)
    if internal:
        with st.expander("Definitions used on this page"):
            definitions_table(["students", "women", "lgbtq", "satisfaction", "m6", "m12"])


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
    c = st.columns(3)
    top = by[~by["origin_country"].str.lower().str.startswith("other")].head(1)
    kpi(c[0], ex, "origin", None if top.empty else top["share"].iloc[0], fmt_pct,
        f"{top['origin_country'].iloc[0]} · largest group" if not top.empty else "", label="Largest group")
    kpi(c[1], ex, "origin", float(len(by[~by["origin_country"].str.lower().str.startswith("other")])), fmt_int,
        "With 5 or more trainees", label="Countries shown")
    kpi(c[2], ex, "origin", pct(answered, total_all), fmt_pct, f"{fmt_int(answered)} of {fmt_int(total_all)} trainees recorded a country", label="Recorded")
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
    inc = d["inclusion"]
    ex.section("Programme & inclusion", f"Reach, inclusion and student experience (C55 onwards) · {sel.label}")
    inc = inc[sel.pmask(inc["period"]) & sel.cmask(inc["cohort"])] if not inc.empty else inc
    if inc.empty:
        st.info("No inclusion data for this selection.")
    else:
        sample_flag(bool(inc["is_sample"].any()))
        fig = px.bar(inc, x="period", y="students", color="cohort", color_discrete_sequence=COLORS)
        a, b = st.columns(2)
        with a:
            show(style(fig), ex, "Students by cohort per half-year", "pr-stack")
        rows = []
        for p in sorted(inc["period"].unique()):
            r = inc[inc["period"] == p]
            lg = nz(r["lgbtq"])
            rows.append(dict(period=p, women=pct(nz(r["women"]), nz(r["gender_responses"])),
                             lgbtq=None if lg is None or lg < SUPPRESS_BELOW else pct(lg, nz(r["lgbtq_responses"])),
                             satisfaction=None if not nz(r["satisfaction_responses"]) else nz(r["satisfaction_score_sum"]) / nz(r["satisfaction_responses"])))
        pr = pd.DataFrame(rows)
        fig = go.Figure()
        fig.add_scatter(x=pr["period"], y=pr["women"], name="Women", mode="lines+markers", line=dict(color=COLORS[0], width=2))
        fig.add_scatter(x=pr["period"], y=pr["lgbtq"], name="LGBTQ+", mode="lines+markers", line=dict(color=COLORS[1], width=2))
        with b:
            show(style(fig, y_pct=True), ex, "Women and LGBTQ+ (share of valid responses)", "pr-incl")
        fig = px.line(pr, x="period", y="satisfaction", markers=True, color_discrete_sequence=COLORS)
        fig.update_yaxes(range=[1, 5])
        t = target(d, "satisfaction", sel.year)
        if t:
            fig.add_hline(y=t, line_dash="dash", line_color="#888", annotation_text=f"Target {sel.year}: {t:g}")
        show(style(fig), ex, "Student satisfaction (1–5)", "pr-sat")
        note = f"LGBTQ+ shares are hidden when fewer than {SUPPRESS_BELOW} people identify, to protect privacy."
        st.caption(note)
        ex.note(note)
    country_section(d, sel, ex)
    if internal and not inc.empty:
        st.markdown("**Cohort detail (internal)**")
        t = inc.copy()
        t["% women"] = [pct(a, b) for a, b in zip(t["women"], t["gender_responses"])]
        t["% LGBTQ+"] = [None if (l is None or pd.isna(l) or l < SUPPRESS_BELOW) else pct(l, r) for l, r in zip(t["lgbtq"], t["lgbtq_responses"])]
        t["satisfaction"] = (t["satisfaction_score_sum"] / t["satisfaction_responses"]).round(2)
        st.dataframe(t[["period", "cohort", "students", "gender_responses", "% women", "lgbtq_responses", "% LGBTQ+", "satisfaction", "satisfaction_responses", "is_sample"]],
                     hide_index=True, width="stretch")


def page_employment(d, sel, internal, today, ex):
    emp = calc_employment(d, sel, today)
    o = outcomes_in(d, sel, today)
    ex.section("Employment outcomes", f"New-programme graduates: placement within six months, and paid work confirmed at month twelve · {sel.label}")
    if o.empty:
        st.info("No outcome data for this selection.")
        return
    sample_flag(bool(o["is_sample"].any()))
    c = st.columns(4)
    for i, m in enumerate(("m6", "m12")):
        e = emp[m]
        kpi(c[i * 2], ex, m, e["rate"], fmt_pct,
            f"{fmt_int(e['confirmed'])} of {fmt_int(e['eligible'])} graduates ({e['cohorts']})" if e["eligible"] else (f"Pending: {e['pending']}" if e["pending"] else "No cohort reached this point in the selection"),
            target(d, f"{m}_rate", sel.year))
        kpi(c[i * 2 + 1], ex, "coverage", e["coverage"], fmt_pct,
            f"{fmt_int(e['verified'])} of {fmt_int(e['eligible'])} statuses verified" if e["eligible"] else "Nothing to follow up in this selection",
            label=f"{'6' if m == 'm6' else '12'}-month follow-up coverage")
    rep = o[o["graduation_date"].notna()]
    if not rep.empty:
        long = rep.melt(id_vars="cohort", value_vars=["m6_rate", "m12_rate"], var_name="measure", value_name="rate")
        long["measure"] = long["measure"].map({"m6_rate": "6-month placement", "m12_rate": "12-month job rate"})
        a, b = st.columns(2)
        with a:
            show(style(px.bar(long, x="cohort", y="rate", color="measure", barmode="group", color_discrete_sequence=COLORS), y_pct=True), ex, "Outcome rates by cohort", "em-rates")
        long = rep.melt(id_vars="cohort", value_vars=["m6_coverage", "m12_coverage"], var_name="measure", value_name="coverage")
        long["measure"] = long["measure"].map({"m6_coverage": "6-month follow-up", "m12_coverage": "12-month follow-up"})
        with b:
            show(style(px.bar(long, x="cohort", y="coverage", color="measure", barmode="group", color_discrete_sequence=COLORS), y_pct=True), ex, "Follow-up coverage by cohort", "em-cov")
    st.markdown("**Cohort detail**")
    table = o[["cohort", "graduation_date", "graduates", "m6_status", "m6_rate", "m6_coverage", "m12_status", "m12_rate", "m12_coverage"]].copy()
    table["graduation_date"] = table["graduation_date"].dt.date
    if internal:
        table.insert(4, "m6_confirmed", o["m6_placed_confirmed"])
        table.insert(8, "m12_confirmed", o["m12_paid_work_confirmed"])
    st.dataframe(table, hide_index=True, width="stretch",
                 column_config={c: st.column_config.NumberColumn(format="%.1f%%") for c in ["m6_rate", "m6_coverage", "m12_rate", "m12_coverage"]})
    for n in ("Denominator: all graduates of the cohort. Unverified graduates count as not placed, so coverage is shown beside every rate.",
              "A cohort is reported only after its full 6- or 12-month window has passed. The table shows cohorts graduating in the selected years, plus cohorts still in the programme."):
        st.caption(n)
        ex.note(n)
    if internal:
        with st.expander("Definitions used on this page"):
            definitions_table(["m6", "m12", "coverage"])


def page_historic(d, sel, internal, today, ex):
    h = d["historic"].copy()
    hg = d.get("historic_gender", pd.DataFrame())
    ex.section("Historic programme (before C55)", f"Old definitions; not added to or compared with new-programme figures · {sel.label}")
    st.info("Historic programme (classes before C55). These results use the old definitions and are not compared with new-programme figures. "
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
    c = st.columns(4)
    kpi(c[0], ex, "h_grad", grads, fmt_int, f"{len(h)} classes · {fmt_int(nz(h['started']))} started")
    if has("quit"):
        finished = grads + (nz(h["quit"]) or 0)
        still = nz(h["still_studying"]) if has("still_studying") else 0
        kpi(c[1], ex, "h_rate", pct(grads, finished), fmt_pct,
            f"{fmt_int(grads)} of {fmt_int(finished)} who finished their course" + (f" · {fmt_int(still)} still studying, not counted" if still else ""))
    else:
        kpi(c[1], ex, "h_rate", pct(grads, nz(h["started"])), fmt_pct, "Graduates ÷ trainees started")
    if has("working_in_it"):
        kpi(c[2], ex, "h_it", pct(nz(h["working_in_it"]), grads), fmt_pct, f"{fmt_int(nz(h['working_in_it']))} graduates with a tech job or internship (current status)")
    else:
        h["eligible"] = h["graduation_date"].notna() & ((h["graduation_date"] + pd.DateOffset(months=6)) <= pd.Timestamp(today)) & (h["graduates"] > 0)
        el = h[h["eligible"]]
        kpi(c[2], ex, "h_m6", pct(nz(el["placed_6m_confirmed"]), nz(el["graduates"])), fmt_pct,
            f"{fmt_int(nz(el['placed_6m_confirmed']))} of {fmt_int(nz(el['graduates']))} graduates")
    # gender is only available per graduation year (counts under 5 hidden)
    if hg.empty:
        kpi(c[3], ex, "h_women", pct(nz(h.get("women_graduates")), nz(h.get("gender_responses"))), fmt_pct, "Gender was not recorded in this data")
    elif sel.cohorts:
        kpi(c[3], ex, "h_women", None, fmt_pct, "Gender is only available per year, not per cohort")
    else:
        yrs = hg[hg["graduation_year"].astype(str) != "All"]
        all_years = sorted(pd.to_numeric(full_h["graduation_year"], errors="coerce").dropna().astype(int).unique())
        whole = bool(all_years) and sel.y0 <= all_years[0] and sel.y1 >= all_years[-1]
        if whole:
            r = hg[hg["graduation_year"].astype(str) == "All"]
            w, n = (float(r["women"].iloc[0]), float(r["gender_responses"].iloc[0])) if not r.empty else (None, None)
        else:
            r = yrs[sel.ymask(yrs["graduation_year"])]
            w, n = nz(r["women"]), nz(r["gender_responses"])
        kpi(c[3], ex, "h_women", pct(w, n) if n else None, fmt_pct,
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
            definitions_table(["h_grad", "h_rate", "h_it", "h_women"])


def page_finance(d, sel, internal, ex):
    ex.section("Finance", f"Annual financial indicators · {sel.label.split(' · ')[0]}")
    fin = d["finance"]
    no_cohort_note(sel)
    if fin.empty:
        st.info("No finance data in the workbook yet.")
        return
    sample_flag(bool(fin["is_sample"].any()))
    f = fin[sel.ymask(fin["year"])]
    tot = nz(f["total_income_eur"]) if not f.empty else None
    op = nz(f["operational_income_eur"]) if not f.empty else None
    span = f"Financial year {sel.y0}" if sel.single else f"Financial years {sel.y0}–{sel.y1}, added up"
    c = st.columns(3)
    euro = lambda v: NA if v is None else f"€{v:,.0f}"
    kpi(c[0], ex, "income", tot, euro, span if tot else "Published after the accounts are closed")
    tgt = None
    if not d["targets"].empty:
        t = d["targets"][d["targets"]["indicator"] == "operational_income_pct"]
        tgt = None if t.empty else (int(t["year"].iloc[0]), float(t["target"].iloc[0]))
    kpi(c[1], ex, "op_income", pct(op, tot), fmt_pct,
        (f"{euro(op)} from operations" if op else "Not reported yet") + (f" · Theory of Change target {tgt[0]}: {tgt[1]:g}%" if tgt else ""))
    kpi(c[2], ex, "income", None if tot is None or op is None else tot - op, euro, "Grants, gifts, subsidies and other income", label="Other income")
    fl = fin[sel.ymask(fin["year"])].assign(other_income_eur=lambda x: x["total_income_eur"] - x["operational_income_eur"])
    if not fl.empty:
        fl["year"] = fl["year"].astype(int).astype(str)
        fl["operational_pct"] = [pct(a, b) for a, b in zip(fl["operational_income_eur"], fl["total_income_eur"])]
        a, b = st.columns(2)
        long = fl.melt(id_vars="year", value_vars=["operational_income_eur", "other_income_eur"], var_name="type", value_name="eur")
        long["type"] = long["type"].map({"operational_income_eur": "Operational", "other_income_eur": "Grants, gifts & other"})
        fig = px.bar(long, x="year", y="eur", color="type", color_discrete_sequence=[COLORS[0], MUTED])
        fig.update_yaxes(tickprefix="€")
        with a:
            show(style(fig), ex, "Income by year", "fi-income")
        fig = px.line(fl, x="year", y="operational_pct", markers=True, color_discrete_sequence=[COLORS[1]])
        if tgt:
            fig.add_hline(y=tgt[1], line_dash="dash", line_color="#888", annotation_text=f"Target {tgt[0]}: {tgt[1]:g}%")
        with b:
            show(style(fig, y_pct=True), ex, "Operational income as % of total", "fi-op")
    n = "Finance is reported per financial year, so the half-year choice doesn't change these figures."
    st.caption(n)
    ex.note(n)
    if internal:
        with st.expander("Definitions used on this page"):
            definitions_table(["income", "op_income"])


def page_org(d, sel, internal, ex):
    ex.section("Organisation & community", f"Team and community as half-yearly snapshots · {sel.label.split(' · ')[0]}")
    team, comm = d["team"], d["community"]
    no_cohort_note(sel)
    sample_flag(any(bool(x["is_sample"].any()) for x in (team, comm) if not x.empty))
    st.markdown("##### Team · snapshot")
    snap = latest_in(team, sel)
    p = snap["period"].iloc[0] if not snap.empty else None
    ctx = f"Snapshot {p} (last in selection)" if p else "No snapshot in this selection"
    c = st.columns(3)
    for col, k, colname in ((c[0], "staff", "fixed_staff"), (c[1], "zzp", "zzp_experts"), (c[2], "interns", "interns")):
        kpi(col, ex, k, None if snap.empty else float(snap[colname].iloc[0]), fmt_int, ctx)
    cs = latest_in(comm, sel)
    if not cs.empty:
        st.markdown("##### Community · snapshot")
        c = st.columns(max(1, len(cs)))
        for col, (_, r) in zip(c, cs.iterrows()):
            kpi(col, ex, "community", float(r["members"]), fmt_int, f"Snapshot {r['period']}", label=f"Community · {r['platform']}")
    a, b = st.columns(2)
    t2 = team[sel.pmask(team["period"])] if not team.empty else team
    c2 = comm[sel.pmask(comm["period"])] if not comm.empty else comm
    if not t2.empty:
        long = t2.melt(id_vars="period", value_vars=["fixed_staff", "zzp_experts", "interns"], var_name="role", value_name="people")
        long["role"] = long["role"].map({"fixed_staff": "Fixed staff", "zzp_experts": "ZZP experts", "interns": "Interns"})
        with a:
            show(style(px.bar(long, x="period", y="people", color="role", barmode="group", color_discrete_sequence=COLORS)), ex, "Team", "or-team")
    if not c2.empty:
        with b:
            show(style(px.line(c2, x="period", y="members", color="platform", markers=True, color_discrete_sequence=COLORS)), ex, "Community members per platform", "or-comm")
    n = "Snapshots are never added up; community platforms are shown separately until members can be deduplicated."
    st.caption(n)
    ex.note(n)
    if internal:
        with st.expander("Definitions used on this page"):
            definitions_table(["staff", "zzp", "interns", "community"])


def page_partners(d, sel, internal, ex):
    ex.section("Partners", f"Companies and organisations that work with HYF and hire our graduates · {sel.label.split(' · ')[0]}")
    part = d.get("partners", pd.DataFrame())
    no_cohort_note(sel)
    if part.empty:
        st.info("No partner data in the workbook yet.")
        return
    sample_flag(bool(part["is_sample"].any()))
    pr = part[sel.ymask(part["year"])]
    last = pr[pr["year"] == pr["year"].max()] if not pr.empty else pr
    lastval = lambda col: None if last.empty or col not in last or pd.isna(last[col].iloc[0]) else float(last[col].iloc[0])
    ly = int(last["year"].iloc[0]) if not last.empty else sel.year
    c = st.columns(4)
    kpi(c[0], ex, "partners_active", lastval("active_partners"), fmt_int, f"In {ly}" if not last.empty else "No partner data for these years yet")
    kpi(c[1], ex, "partners_new", nz(pr["new_partners"]) if not pr.empty else None, fmt_int,
        (f"Joined in {sel.y0}" if sel.single else f"Joined {sel.y0}–{sel.y1}") if not pr.empty else "")
    kpi(c[2], ex, "partners_hiring", lastval("hiring_partners"), fmt_int, f"Hired at least one graduate in {ly}" if not last.empty else "")
    kpi(c[3], ex, "partners_hired", nz(pr["graduates_hired"]) if not pr.empty else None, fmt_int,
        ("Jobs and internships at partners" + ("" if sel.single else f", {sel.y0}–{sel.y1} added up")) if not pr.empty else "")
    if not pr.empty:
        p2 = pr.copy()
        p2["year"] = p2["year"].astype(int).astype(str)
        p2["hiring_share"] = [pct(h, a) for h, a in zip(p2["hiring_partners"], p2["active_partners"])]
        a, b = st.columns(2)
        fig = go.Figure()
        fig.add_bar(x=p2["year"], y=p2["active_partners"], name="Active partners", marker_color=COLORS[0])
        fig.add_bar(x=p2["year"], y=p2["new_partners"], name="New partners", marker_color=COLORS[1])
        fig.add_bar(x=p2["year"], y=p2["hiring_partners"], name="Hiring partners", marker_color=COLORS[2])
        fig.update_layout(barmode="group")
        with a:
            show(style(fig), ex, "Partners per year", "pa-partners")
        with b:
            show(style(px.bar(p2, x="year", y="graduates_hired", color_discrete_sequence=[COLORS[1]])), ex, "Graduates hired by partners per year", "pa-hired")
    n = ("Partner indicators are not yet in the Measurement Dictionary v1.3; their definitions still need to be agreed. "
         "Active and hiring partners show the last year in the selection; new partners and graduates hired are added up.")
    st.caption(n)
    ex.note(n)
    if internal:
        with st.expander("Definitions used on this page"):
            definitions_table(["partners_active", "partners_new", "partners_hiring", "partners_hired"])


def page_volunteers(d, sel, internal, ex):
    ex.section("Volunteers", f"The mentors, coaches and hosts who teach and support our trainees · {sel.label.split(' · ')[0]}")
    team, vol = d["team"], d.get("volunteers", pd.DataFrame())
    no_cohort_note(sel)
    sample_flag(any(bool(x["is_sample"].any()) for x in (team, vol) if not x.empty))
    snap = latest_in(team, sel)
    vs = latest_in(vol, sel) if not vol.empty else vol
    roles = list(vs.itertuples()) if not vs.empty else []
    c = st.columns(1 + len(roles))
    kpi(c[0], ex, "volunteers", None if snap.empty else float(snap["active_volunteers"].iloc[0]), fmt_int,
        f"Snapshot {snap['period'].iloc[0]} (last in selection)" if not snap.empty else "No snapshot in this selection")
    for col, r in zip(c[1:], roles):
        kpi(col, ex, "volunteers", float(r.volunteers), fmt_int, f"Snapshot {r.period}", label=r.role)
    v2 = vol[sel.pmask(vol["period"])] if not vol.empty else vol
    t2 = team[sel.pmask(team["period"])] if not team.empty else team
    a, b = st.columns(2)
    if not t2.empty:
        with a:
            show(style(px.line(t2, x="period", y="active_volunteers", markers=True, color_discrete_sequence=COLORS)), ex, "Active volunteers per half-year", "vo-total")
    if not v2.empty:
        with b:
            show(style(px.bar(v2, x="period", y="volunteers", color="role", color_discrete_sequence=COLORS)), ex, "Active volunteers by role", "vo-roles")
    n = "Volunteers count once per half-year, by their main role, and only with logged activity and a valid VOG (Measurement Dictionary v1.3). Snapshots are never added up."
    st.caption(n)
    ex.note(n)
    if internal:
        with st.expander("Definitions used on this page"):
            definitions_table(["volunteers"])


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
    d = load_indicators(str(indicators_path), indicators_path.stat().st_mtime)
    yrs = set()
    for name in ("inclusion", "team", "visibility", "students_annual", "finance", "partners", "community", "volunteers"):
        yrs |= {int(y) for y in pd.to_numeric(d[name].get("year", pd.Series(dtype=float)), errors="coerce").dropna()}
    yrs |= {int(y) for y in pd.to_numeric(d["historic"].get("graduation_year", pd.Series(dtype=float)), errors="coerce").dropna()}
    yrs |= {int(y) for y in pd.to_numeric(d.get("origin", pd.DataFrame()).get("start_year", pd.Series(dtype=float)), errors="coerce").dropna()}
    years = sorted(y for y in yrs if 2015 <= y <= today.year + 1) or [today.year]
    cohorts = sorted({str(c) for name in ("inclusion", "outcomes", "historic") for c in d[name].get("cohort", pd.Series(dtype=str)).dropna()},
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
    ex = Export()
    has_sample = any(bool(df["is_sample"].any()) for df in d.values() if "is_sample" in df and not df.empty)
    tabs = st.tabs(["A · Impact overview", "B · Programme & inclusion", "C · Employment", "D · Historic programme",
                    "E · Organisation & community", "F · Finance", "G · Partners", "H · Volunteers", "I · Visibility"])
    with tabs[0]:
        page_overview(d, sel, internal, today, ex)
    with tabs[1]:
        page_programme(d, sel, internal, today, ex)
    with tabs[2]:
        page_employment(d, sel, internal, today, ex)
    with tabs[3]:
        page_historic(d, sel, internal, today, ex)
    with tabs[4]:
        page_org(d, sel, internal, ex)
    with tabs[5]:
        page_finance(d, sel, internal, ex)
    with tabs[6]:
        page_partners(d, sel, internal, ex)
    with tabs[7]:
        page_volunteers(d, sel, internal, ex)
    with tabs[8]:
        page_visibility(d, sel, internal, ex)
    with c4:
        st.download_button(
            "⬇ Download public HTML", data=export_html(ex, sel.label, has_sample), file_name=f"HYF_impact_{sel.key}.html", mime="text/html",
            help="One file with the public view of all pages for this selection. Email it or open it offline. Internal details are never included.",
            disabled=internal, width="stretch",
        )
        if internal:
            st.caption("Switch to Public to export.")
