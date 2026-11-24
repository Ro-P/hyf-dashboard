"""
Shared parts of the HYF Impact Dashboard, used by every tab:
settings, the indicator definitions, loading the workbook, the filters (Sel),
calculations, number formatting, cards, chart style and the privacy rules.

The filters: render() in impact.py reads the filter widgets once and builds one Sel object.
Every tab receives that same Sel and keeps only the rows that match it
(sel.ymask for years, sel.cmask for cohorts, sel.pmask for half-years).
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
# Rows marked is_sample = TRUE are placeholders. They are shown in dev (demo) and left out everywhere else,
# so production only shows real figures; pages and sections without real data are hidden.
# Tabs whose placeholder rows are still shown in production (with a "sample data" warning) until real figures exist.
SAMPLE_TABS = tuple(t.strip() for t in os.getenv("SAMPLE_TABS", "community,finance,visibility").split(",") if t.strip())


def show_sample() -> bool:
    default = "true" if os.getenv("APP_ENV", "").strip().lower() == "dev" else "false"
    return os.getenv("SHOW_SAMPLE_DATA", default).strip().lower() in ("true", "1", "yes", "on")
HISTORIC_LAST_YEAR = int(os.getenv("HISTORIC_LAST_YEAR", "2025"))  # historic programme shown up to and including this graduation year

# --------------------------------------------------------------------------- #
# Definitions (Measurement Dictionary v1.3)
# --------------------------------------------------------------------------- #
DEFS = {
    "students": ("Students Supported", "Unique students enrolled or receiving documented job-search support within 12 months of graduation during the period.", "Deduplicated count of eligible students with active enrolment or documented support.", "Annual", "Student administration and alumni support log"),
    "women": ("% Women", "Share identifying as women among valid voluntary gender respondents within the selected population.", "Women responses ÷ valid gender responses × 100.", "Half-yearly", "Intake questionnaire"),
    "lgbtq": ("% LGBTQ+", "Share voluntarily self-identifying as LGBTQ+ among valid responses to that question.", "LGBTQ+ responses ÷ valid LGBTQ+ responses × 100. Hidden when fewer than five people.", "Half-yearly", "Voluntary intake questionnaire"),
    "satisfaction": ("Student Satisfaction", "Average student score for educational session evaluations on a 1–5 scale.", "Sum of valid evaluation scores ÷ number of valid scores.", "Half-yearly", "Session evaluation forms"),
    "m6": ("6-month placement rate", "Share of graduates whose first job or internship started within six months after graduating (or before).", "Graduates with a job or internship start date no later than graduation + 6 months ÷ all graduates whose 6 months have passed × 100.", "By cohort; half-yearly", "Job placement tracking and graduate follow-up"),
    "m12": ("12-month placement rate", "Share of graduates whose first job or internship started within twelve months after graduating (or before).", "Graduates with a job or internship start date no later than graduation + 12 months ÷ all graduates whose 12 months have passed × 100.", "By cohort; half-yearly", "Alumni follow-up / placement records"),
    "coverage": ("Employment Follow-up Coverage", "Share of eligible graduates with a verified employment status at the milestone.", "Graduates with verified status ÷ all eligible graduates × 100.", "6 and 12 months", "Alumni survey and verified follow-up records"),
    "h_m6": ("Historic 6-month Placement Rate", "Share of graduates who found a paid job or internship with documented intent to hire within six months after graduation.", "Confirmed placements within 6 months ÷ all graduates from eligible historic cohorts × 100. Unknown statuses stay in the denominator.", "Annual / cohort", "Historic job placement and alumni records"),
    "all_started": ("Trainees started", "People who started an HYF class, in all programmes.", "Count of trainees per class, added up over the selected classes.", "Per class", "Trainee records (Google Sheet / Dojo)"),
    "all_grads": ("Graduates", "People who successfully completed an HYF class, in all programmes.", "Count of graduates per class, added up over the selected classes.", "Per class", "Trainee records (Google Sheet / Dojo)"),
    "all_working": ("Employment", "Graduates whose current status is a job or internship, in IT or outside IT.", "Graduates with a tech job, an internship or a non-tech job. Each graduate counted once, by current status (not at a fixed time after graduation). Years filter by graduation year.", "Current status", "Trainee records (job path)"),
    "all_it": ("Graduates working in IT", "Graduates whose current status is a tech job or an IT internship.", "Count of graduates with a tech job or internship. Current status, not measured at a fixed time after graduation.", "Current status", "Trainee records (job path)"),
    "all_women": ("Women graduates", "Graduates who identify as women, among graduates who answered the gender question.", "Count of women-identifying graduates. Graduates who did not answer are left out.", "By graduation year", "Trainee records"),
    "all_still": ("Still studying", "Trainees who are currently following an HYF class.", "Count of trainees with learning status still studying (or on hold), added up over the selected classes.", "Current status", "Trainee records (Google Sheet / Dojo)"),
    "em_it": ("Working in IT", "Graduates whose current status is a tech job or an IT internship.", "Count of graduates with job path tech job or internship.", "Current status", "Trainee records (job path)"),
    "em_tech": ("In a tech job", "Graduates whose current status is a paid tech job.", "Count of graduates with job path tech job.", "Current status", "Trainee records (job path)"),
    "em_intern": ("In an internship", "Graduates whose current status is an IT internship.", "Count of graduates with job path internship.", "Current status", "Trainee records (job path)"),
    "em_nontech": ("In a non-tech job", "Graduates whose current status is a job outside IT.", "Count of graduates with job path non-tech job.", "Current status", "Trainee records (job path)"),
    "em_search": ("Still searching", "Graduates who are still looking for a job.", "Count of graduates with job path searching.", "Current status", "Trainee records (job path)"),
    "countries_all": ("Countries of origin", "Number of different countries HYF trainees come from, including countries with only one or a few trainees.", "Count of different recorded countries of origin among trainees whose class started in the selected years. Only the number of countries is stored, not who comes from where.", "By class start year", "Trainee records (Google Sheet / Dojo)"),
    "h_grad": ("Historic People Graduated", "Unique people successfully completing the historic programme in the reporting period.", "Count unique successful graduates once on completion.", "Annual / cohort", "Historic graduation records"),
    "h_rate": ("Graduation rate", "Share of trainees who finished their course and graduated.", "Graduates ÷ (graduates + quit) × 100. Trainees still studying or on hold are not counted.", "Annual / cohort", "Dojo trainee export"),
    "h_it": ("Graduates working in IT", "Graduates whose current status is a tech job or an internship.", "Graduates with a tech job or internship ÷ all graduates × 100. Current status, not measured at a fixed time after graduation.", "Current status", "Dojo trainee export"),
    "h_women": ("Historic % Women", "Share identifying as women among respondents with valid voluntary gender answers.", "Valid women-identifying responses ÷ all valid gender responses × 100.", "Annual / cohort", "Historic intake records"),
    "op_income": ("Operational Income %", "Share of recognised income earned from operations and qualifying public/private contracts.", "Operational earned income ÷ total recognised income × 100. Grants, gifts and subsidies are excluded from the numerator.", "Annual", "Financial statements"),
    "income": ("Total Income", "All recognised income during the financial year, across revenue types.", "Sum of operational income, grants, subsidies, donations and other income.", "Annual", "Annual accounts"),
    "staff": ("Fixed Staff", "Individuals employed by HYF under an employment contract on the reporting date.", "Active employee headcount; excludes ZZP experts and interns.", "Half-yearly snapshot", "HR records"),
    "zzp": ("External Experts (ZZP)", "Self-employed experts with active HYF contracts on the reporting date.", "Count of active contracted individuals.", "Half-yearly snapshot", "Contract administration"),
    "interns": ("Interns", "Individuals actively interning at HYF on the reporting date.", "Count of people on active internship agreements.", "Half-yearly snapshot", "HR / internship records"),
    "grants": ("Grants", "Income from grants (funds and foundations) in the financial year.", "Sum of grant income in closed financial years.", "Annual", "Finances tab"),
    "partner_type": ("Partners by type", "Active partner organisations per type of partnership: employment, funding, volunteers, events.", "Count of active organisations with that partnership type. One organisation can have several types.", "Annual", "Organisations tab"),
    "volunteer_expertise": ("Volunteers by expertise", "Active volunteers per area of expertise (Data, HR mentor, English mentor…).", "Count of active volunteers who listed that expertise. One volunteer can list several.", "Half-yearly", "Volunteers tab"),
    "volunteers_total": ("Total volunteers", "All volunteers in the Volunteers tab, active and paused.", "Count of volunteers per status, added up.", "Half-yearly", "Volunteers tab"),
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
SHEETS = ["partner_types", "volunteer_expertise", "volunteer_status", "inclusion", "students_annual", "outcomes", "historic", "historic_gender", "targets", "finance", "team", "community", "visibility", "partners", "volunteers", "origin", "employers", "classes", "all_gender", "job_paths", "origin_countries", "origin_range", "origin_by_cohort", "gender_by_cohort", "country_keys_by_cohort", "it_roles", "it_roles_by_cohort", "it_roles_range", "job_paths_by_cohort", "education_by_cohort", "employers_range", "students_supported", "students_by_cohort", "education", "outcomes_by_year", "impact_summary", "impact_countries", "impact_graduates", "impact_jobs", "impact_gender", "impact_origin"]


@st.cache_data(show_spinner=False)
def load_indicators(path: str, mtime: float, with_sample: bool = True, sample_tabs: tuple = ()) -> dict[str, pd.DataFrame]:
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
        if not with_sample and name not in sample_tabs:
            df = df[~df["is_sample"]]
        for c in df.columns:
            if "date" in c:
                df[c] = pd.to_datetime(df[c], errors="coerce")
        if "period" in df.columns:
            df["period"] = df["period"].astype(str).str.strip().str.upper().str.replace(" ", "-")
            df["year"] = df["period"].str[:4].astype(int)
        out[name] = df
    # historic programme: keep graduation years up to HISTORIC_LAST_YEAR only
    h = out["historic"]
    if not h.empty and "graduation_year" in h:
        out["historic"] = h[~(pd.to_numeric(h["graduation_year"], errors="coerce") > HISTORIC_LAST_YEAR)]
    hg = out["historic_gender"]
    if not hg.empty and "graduation_year" in hg:
        late = pd.to_numeric(hg["graduation_year"], errors="coerce") > HISTORIC_LAST_YEAR
        out["historic_gender"] = hg[~late]
        out["historic_gender"].attrs["capped"] = bool(late.any())  # the "All" row then includes later years: don't use it
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
        small = o[f"{m}_small"].astype(str).str.upper().isin(["TRUE", "1"]) if f"{m}_small" in o else pd.Series(False, index=o.index)
        o[f"{m}_small"] = small & elapsed
        reported = elapsed & (o[ok].notna() | small)
        o[f"{m}_reported"] = reported
        o[f"{m}_rate"] = [pct(a, b) if r else None for a, b, r in zip(o[ok], o["graduates"], reported)]
        o[f"{m}_coverage"] = [pct(a, b) if r else None for a, b, r in zip(o[ver], o["graduates"], reported)]
        o[f"{m}_status"] = [
            ("Fewer than 5" if sm else "Reported") if r else ("Not yet due" if not e else "Due — not reported yet") if pd.notna(g) else "In programme"
            for r, e, g, sm in zip(reported, elapsed, o["graduation_date"], o[f"{m}_small"])
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
    return NA if v is None or pd.isna(v) else f"{v:.1f}%"


def fmt_int(v):
    return NA if v is None or pd.isna(v) else f"{int(round(v)):,}"


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


ICONS = {  # simple line icons (inline SVG), drawn in the card's accent colour
    "cap": '<path d="M2 9l10-5 10 5-10 5z"/><path d="M6 11v5c3 2 9 2 12 0v-5"/><path d="M22 9v6"/>',
    "check": '<circle cx="12" cy="12" r="9.5"/><path d="M7.5 12.5l3 3 6-6.5"/>',
    "globe": '<circle cx="12" cy="12" r="9.5"/><path d="M2.5 12h19"/><path d="M12 2.5c3 3 3 16 0 19c-3-3-3-16 0-19z"/>',
}


def _icon(name, color):
    return (f'<svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="{color}" stroke-width="1.6" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>')


IMPACT_CSS = """<style>
.hyf-cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px;margin:8px 0 22px}
.hyf-card{border-radius:16px;padding:26px 28px;display:flex;justify-content:space-between;align-items:flex-start;min-height:150px}
.hyf-card .n{font-size:64px;font-weight:800;line-height:1;margin:0}
.hyf-card .l{font-size:22px;margin:10px 0 0}
.hyf-panel{background:#FFFFFF;border-radius:16px;padding:22px 26px;height:100%}
.hyf-panel h4{margin:0 0 12px;color:#5E1600;font-size:22px}
.hyf-row{display:grid;grid-template-columns:110px 1fr 56px;align-items:center;gap:14px;margin:8px 0}
.hyf-row .c{font-weight:700;color:#5E1600;font-size:18px}
.hyf-row .bar{height:26px;border-radius:7px}
.hyf-row .p{font-weight:700;text-align:right;font-size:18px}
.hyf-pill{display:inline-block;background:#FFF09E;color:#5E1600;font-weight:700;border-radius:999px;padding:8px 22px;margin-top:10px;font-size:17px}
.hyf-help{display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;border-radius:50%;
 border:1.5px solid currentColor;font-size:13px;font-weight:700;margin-left:8px;cursor:help;opacity:.85;vertical-align:middle}
.hyf-legend div{display:flex;align-items:center;gap:10px;margin:12px 0;font-size:20px;color:#5E1600}
.hyf-legend span.sw{width:20px;height:20px;border-radius:5px;display:inline-block}
@media (max-width:900px){.hyf-cards{grid-template-columns:1fr}.hyf-card .n{font-size:48px}}
</style>"""


IMPACT_HELP = {
    "graduates": "Graduates: trainees whose learning status is “graduated”, each person counted once. All programmes, all years. Source: Trainee_details.",
    "jobs": "Jobs: every recorded job or internship of HYF trainees (a graduate with two jobs counts twice). Source: Trainee_details (type / company name).",
    "countries": "Countries of origin: number of different countries of origin recorded for trainees. Source: Trainee_details.",
    "followup": "Job within 6 / 12 months: number of graduates who had a first job or internship that started no later than 6 (or 12) months after their graduation date (numbers, not percentages). Source: Trainee_details (graduation date and job start date).",
    "gender": "Gender: share of graduates who answered the gender question (no answer is left out), by graduation year. Groups of fewer than 5 people (often non-binary / other) are shown as fewer than 5, not as an exact number.",
    "origin": "Largest groups: share of trainees with a recorded country of origin, by the year their class started. Countries with fewer than 5 trainees in a year are grouped under other countries.",
}


def _help(key):
    return f'<span class="hyf-help" title="{html.escape(IMPACT_HELP[key])}">?</span>'


def _range_row(t, sel):
    """Rows of a from_year/to_year table for the selected years (clipped to the years in the table)."""
    if t.empty:
        return t, None, None
    a, b = pd.to_numeric(t["from_year"]), pd.to_numeric(t["to_year"])
    lo, hi = max(sel.y0, int(a.min())), min(sel.y1, int(b.max()))
    return t[(a == lo) & (b == hi)], lo, hi


def _hbar(df, label_col, key, title, ex, color="#B12900"):
    """Horizontal bar chart with the number on each bar; hidden counts (1–4) shown as "<5"."""
    df = df.copy()
    df["n"] = pd.to_numeric(df["trainees"], errors="coerce")
    df["label"] = [f"{int(v)}" if pd.notna(v) else f"<{SUPPRESS_BELOW}" for v in df["n"]]
    df["bar"] = df["n"].fillna(SUPPRESS_BELOW / 2)                # a short bar so the hidden ones are still visible
    df = df.sort_values(["n", label_col], ascending=[False, True], na_position="last")
    fig = px.bar(df, x="bar", y=label_col, orientation="h", text="label", color_discrete_sequence=[color])
    fig.update_traces(textposition="outside", cliponaxis=False, hovertemplate="%{y}: %{text}<extra></extra>")
    fig.update_layout(height=max(260, 26 * len(df) + 70), margin=dict(l=10, r=40, t=10, b=10), showlegend=False)
    fig.update_yaxes(categoryorder="array", categoryarray=list(df[label_col])[::-1], title=None)
    fig.update_xaxes(title=None, rangemode="tozero")
    st.plotly_chart(fig, width="stretch", key=key)
    ex.fig(title, fig)


def _cohort_scope(sel):
    return f"cohorts {', '.join(sel.cohorts[:6])}{' …' if len(sel.cohorts) > 6 else ''}"


def _pick(d, sel, range_tab, cohort_tab, key, value, what):
    """Rows for the current filters: the per-cohort table when cohorts are picked, else the year-range table.
    Returns (rows, scope text), or (None, "") when the data isn't there."""
    if sel.cohorts:
        t = d.get(cohort_tab, pd.DataFrame())
        if t.empty:
            rt = d.get(range_tab, pd.DataFrame())
            if rt.empty:
                return None, ""
            r, lo, hi = _range_row(rt, sel)
            return r, f"{what} {lo}–{hi} (per cohort not in the data yet: run tools/update_from_sheet.py again)"
        part = t[sel.cmask(t["cohort"])]
        r = part.groupby(key, as_index=False)[value].sum(min_count=1)
        return r, _cohort_scope(sel)
    t = d.get(range_tab, pd.DataFrame())
    if t.empty:
        return None, ""
    r, lo, hi = _range_row(t, sel)
    return r, (f"{what} {lo}–{hi}" if lo is not None else "")


JOB_LABELS = {"tech_job": "Tech job", "internship": "Internship", "non_tech_job": "Non-tech job", "searching": "Searching",
              "not_searching": "Not searching", "other_studies": "Other studies", "stopped_support": "No longer in support", "not_recorded": "Not recorded"}
