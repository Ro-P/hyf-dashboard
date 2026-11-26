"""
Turn the Dojo trainee export into COUNTS-ONLY files that are safe to upload
(e.g. to Streamlit Cloud). Run this on your own laptop, never in the cloud.

    python tools/make_cloud_data.py "path/to/dojo.trainees.xlsx"

Writes into data/real/ (or data/ when there is no data/real folder):
  - HYF_indicators.xlsx : tabs `historic`, `historic_gender` and `origin` rebuilt from Dojo
                          (other tabs are kept as they are)
  - HYF_counts.xlsx     : summary tables for the Build tab
No names, IDs or per-person rows are written. In HYF_counts.xlsx and in
historic_gender, any count from 1 to 4 is left empty (privacy: groups < 5).
"""
from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

import pandas as pd

MIN_GROUP = 5
NEW_PROGRAMME_FROM = 55  # classes from C55 onwards are the new programme
HISTORIC_LAST_YEAR = 2025  # historic tabs keep graduation years up to and including this year
ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ["HYF_OUT_DIR"]) if os.getenv("HYF_OUT_DIR") else ROOT / "data" / "real"  # where the prod app reads its data

JOB = {"tech-job": "tech_job", "internship": "internship", "searching": "searching", "not-searching": "not_searching",
       "other-studies": "other_studies", "non-tech-job": "non_tech_job", "no-longer-helping": "stopped_support"}


def suppress(df: pd.DataFrame, keep: tuple = ()) -> pd.DataFrame:
    """Blank out counts 1–4 (0 stays 0) in every numeric column except `keep`."""
    out = df.copy()
    for c in out.columns:
        if c in keep or not pd.api.types.is_numeric_dtype(out[c]):
            continue
        out[c] = out[c].astype("Int64").mask(out[c].between(1, MIN_GROUP - 1))
    return out


# Column names in the Google Sheet "trainees.csv" tab → names this script uses (the Dojo export already uses these)
SHEET_COLUMNS = {
    "start cohort": "Start Cohort", "learning status": "Learning Status", "gender": "Gender",
    "country of origin": "Origin Country", "origin country": "Origin Country", "background": "Background",
    "start date": "Start Date", "graduation date": "Graduation Date", "quit reason": "Quit Reason",
    "job path": "Job Path", "track": "Track",
}
KEEP = ["Start Cohort", "Learning Status", "Gender", "Origin Country", "Background", "Start Date",
        "Graduation Date", "Quit Reason", "Job Path"]


def range_counts(years: pd.Series, values: pd.Series, name: str) -> pd.DataFrame:
    """Trainees per value for every from-year/to-year range the filter can pick. Counts 1–4 are left empty
    (the value is still listed, so you can see it exists, but not how many)."""
    df = pd.DataFrame({"y": years, "v": values}).dropna()
    if df.empty:
        return pd.DataFrame(columns=["from_year", "to_year", name, "trainees"])
    df["y"] = df["y"].astype(int)
    ys = sorted(df["y"].unique())
    rows = []
    for i, a in enumerate(ys):
        for b in ys[i:]:
            for v, n in df.loc[df["y"].between(a, b), "v"].value_counts().items():
                rows.append({"from_year": a, "to_year": b, name: v, "trainees": int(n)})
    out = pd.DataFrame(rows)
    out["trainees"] = out["trainees"].astype("Int64").mask(out["trainees"].between(1, MIN_GROUP - 1))
    return out


def read_trainees(src: str) -> pd.DataFrame:
    """Read the trainee rows from a Dojo export (tab dojo.trainees) or the Google Sheet (tab trainees.csv)."""
    tabs = pd.ExcelFile(src).sheet_names
    tab = next((t for t in tabs if t.strip().lower() in ("dojo.trainees", "trainees.csv", "trainees")), None)
    if tab is None:
        tab = next((t for t in tabs if "trainee" in t.lower()), tabs[0])
    d = pd.read_excel(src, sheet_name=tab)
    d = d.rename(columns={c: SHEET_COLUMNS.get(str(c).strip().lower(), c) for c in d.columns})
    missing = [c for c in KEEP if c not in d.columns]
    if missing:
        sys.exit(f"Tab '{tab}' is missing these columns: {', '.join(missing)}")
    d = d[KEEP + (["Track"] if "Track" in d.columns else [])].copy()  # drop names, birth dates, cities and everything else
    # "C55", "Class 55" or 55 → 55
    d["Start Cohort"] = pd.to_numeric(d["Start Cohort"].astype(str).str.extract(r"(\d+)")[0], errors="coerce")
    d = d.dropna(subset=["Start Cohort"])
    for c in ("Start Date", "Graduation Date"):
        if not pd.api.types.is_datetime64_any_dtype(d[c]):
            with warnings.catch_warnings():   # Google Sheets dates are day-first (31/12/2025)
                warnings.simplefilter("ignore")
                d[c] = pd.to_datetime(d[c], errors="coerce", dayfirst=True, utc=True)
    for c in ("Learning Status", "Job Path"):   # "Graduated" / "Tech job" → "graduated" / "tech-job"
        d[c] = d[c].astype("string").str.strip().str.lower().str.replace(r"[\s_]+", "-", regex=True)
    return d


def main(src: str) -> None:
    d = read_trainees(src)
    d["start"] = pd.to_datetime(d["Start Date"], errors="coerce", utc=True).dt.tz_localize(None)
    d["grad"] = pd.to_datetime(d["Graduation Date"], errors="coerce", utc=True).dt.tz_localize(None)
    d["status"] = d["Learning Status"].str.strip().str.lower()
    d["gender"] = d["Gender"].fillna("no answer").str.strip().str.lower().replace({"other": "non-binary or other", "non-binary": "non-binary or other"})
    d["job"] = d["Job Path"].map(JOB)
    g = d["status"] == "graduated"

    # ---- per class: programme counts only
    def class_rows(df: pd.DataFrame) -> pd.DataFrame:
        rows = []
        for c, r in df.groupby("Start Cohort"):
            gr = r[r["status"] == "graduated"]
            rows.append(dict(
                cohort=f"C{int(c):02d}",
                programme="new" if c >= NEW_PROGRAMME_FROM else "historic",
                graduation_date=gr["grad"].max().date() if gr["grad"].notna().any() else None,
                graduation_year=int(gr["grad"].max().year) if gr["grad"].notna().any() else None,
                started=len(r), graduates=len(gr), quit=int((r["status"] == "quit").sum()),
                still_studying=int(r["status"].isin(["studying", "on-hold"]).sum()),
                working_in_it=int(gr["job"].isin(["tech_job", "internship"]).sum()),
                working=int(gr["job"].isin(["tech_job", "internship", "non_tech_job"]).sum()),   # in IT or outside IT
                placed_6m_confirmed=None, status_recorded=None,  # job start dates are not in the export
                is_sample=False,
            ))
        return pd.DataFrame(rows)

    # graduates by gender per graduation year (+ total row), suppressed
    def gender_by_grad_year(df: pd.DataFrame) -> pd.DataFrame:
        gg = df[df["status"] == "graduated"].assign(year=lambda x: x["grad"].dt.year).dropna(subset=["year"])
        gt = pd.crosstab(gg["year"], gg["gender"]).reindex(columns=["woman", "man", "non-binary or other", "no answer"], fill_value=0)
        gt.columns = ["women", "men", "nonbinary_or_other", "no_answer"]
        gt = gt.reset_index().rename(columns={"year": "graduation_year"})
        gt["graduation_year"] = gt["graduation_year"].astype(int).astype(str)
        total = gt.drop(columns="graduation_year").sum().to_frame().T
        total.insert(0, "graduation_year", "All")
        out = suppress(pd.concat([gt, total], ignore_index=True))
        out["gender_responses"] = out[["women", "men", "nonbinary_or_other"]].sum(axis=1, min_count=1)
        out["is_sample"] = False
        return out

    # historic tabs: classes before C55, graduation years up to HISTORIC_LAST_YEAR
    h = d[d["Start Cohort"] < NEW_PROGRAMME_FROM]
    historic = class_rows(h).drop(columns="programme")
    historic = historic[~(historic["graduation_year"] > HISTORIC_LAST_YEAR)]
    hgender = gender_by_grad_year(h[~(h["grad"].dt.year > HISTORIC_LAST_YEAR)])
    # all-programme tabs (historic + new) for the "10 years at a glance" overview
    classes = class_rows(d)
    all_gender = gender_by_grad_year(d)

    # job path of graduates (current status) per graduation year + "All" row; counts 1–4 hidden except graduates
    gj = d[g].assign(year=lambda x: x["grad"].dt.year, path=lambda x: x["job"].fillna("not_recorded")).dropna(subset=["year"])
    jp = pd.crosstab(gj["year"].astype(int), gj["path"]).reindex(columns=list(JOB.values()) + ["not_recorded"], fill_value=0)
    jp.insert(0, "graduates", jp.sum(axis=1))
    jp = jp.reset_index().rename(columns={"year": "graduation_year"})
    jp["graduation_year"] = jp["graduation_year"].astype(str)
    allrow = jp.drop(columns="graduation_year").sum().to_frame().T
    allrow.insert(0, "graduation_year", "All")
    job_paths = suppress(pd.concat([jp, allrow], ignore_index=True), keep=("graduation_year", "graduates"))
    job_paths["is_sample"] = False
    # same per cohort (for the cohort filter on the Employment tab)
    gjc = d[g].assign(cohort=lambda x: x["Start Cohort"].map(lambda c: f"C{int(c):02d}"), path=lambda x: x["job"].fillna("not_recorded"))
    jpc = pd.crosstab(gjc["cohort"], gjc["path"]).reindex(columns=list(JOB.values()) + ["not_recorded"], fill_value=0)
    jpc.insert(0, "graduates", jpc.sum(axis=1))
    job_paths_by_cohort = suppress(jpc.reset_index(), keep=("cohort", "graduates"))
    job_paths_by_cohort["is_sample"] = False

    # ---- Build-tab tables (all classes, incl. C55), suppressed
    d["start_year"] = d["start"].dt.year
    d["grad_year"] = d["grad"].dt.year
    status_year = d.pivot_table(index="start_year", columns="status", values="Start Cohort", aggfunc="size", fill_value=0)
    status_year = status_year.reindex(columns=["graduated", "quit", "studying", "on-hold"], fill_value=0)
    status_year["still_studying"] = status_year.pop("studying") + status_year.pop("on-hold")
    status_year.insert(0, "started", status_year.sum(axis=1))
    status_year = suppress(status_year.reset_index(), keep=("start_year", "started"))
    outcomes = d[g].pivot_table(index="grad_year", columns="job", values="Start Cohort", aggfunc="size", fill_value=0)
    outcomes = outcomes.reindex(columns=list(JOB.values()), fill_value=0)
    outcomes.insert(0, "working_in_it", outcomes["tech_job"] + outcomes["internship"])
    outcomes.insert(0, "graduates", outcomes.sum(axis=1) - outcomes["working_in_it"])
    outcomes = suppress(outcomes.reset_index().astype({"grad_year": int}), keep=("grad_year",))
    gender_year = pd.crosstab(d["start_year"], d["gender"]).reindex(columns=["woman", "man", "non-binary or other", "no answer"], fill_value=0)
    gender_year.columns = ["women", "men", "nonbinary_or_other", "no_answer"]
    gender_year = suppress(gender_year.reset_index(), keep=("start_year",))
    def totals(col, name):
        s = d[col].fillna("not recorded").value_counts()
        small = s[s < MIN_GROUP].sum()
        s = s[s >= MIN_GROUP]
        if small:
            s[f"other (groups under {MIN_GROUP})"] = small
        return s.rename_axis(name).reset_index(name="trainees")
    tables = {
        "status_by_start_year": status_year,
        "outcomes_by_grad_year": outcomes,
        "gender_by_start_year": gender_year,
        "quit_reasons": totals("Quit Reason", "quit_reason"),
        "background": totals("Background", "background"),
        "origin_country": totals("Origin Country", "origin_country"),
    }

    # ---- origin: trainees per country per class start year; countries under 5 in a year -> "Other"
    oc = d.assign(country=d["Origin Country"].fillna("not recorded").astype(str).str.strip())
    oc = oc.groupby([oc["start"].dt.year.rename("start_year"), "country"]).size().reset_index(name="trainees")
    small = (oc["trainees"] < MIN_GROUP) & (oc["country"] != "not recorded")
    oc.loc[small, "country"] = f"Other (groups under {MIN_GROUP})"
    origin = oc.groupby(["start_year", "country"], as_index=False)["trainees"].sum().rename(columns={"country": "origin_country"})
    origin["is_sample"] = False

    # ---- number of different countries of origin (all countries, also those with fewer than 5 trainees),
    #      for every from-year/to-year range the dashboard filter can pick. Only the number of countries is stored.
    cy = d.assign(country=d["Origin Country"].astype(str).str.strip().str.title(), start_year=d["start"].dt.year).dropna(subset=["start_year"])
    cy = cy[~cy["country"].str.lower().isin(["", "nan", "none", "not recorded", "unknown", "n/a", "prefer not to say"])]
    years = sorted(cy["start_year"].astype(int).unique())
    origin_countries = pd.DataFrame(
        [{"from_year": a, "to_year": b, "countries": int(cy.loc[cy["start_year"].between(a, b), "country"].nunique())}
         for i, a in enumerate(years) for b in years[i:]])
    origin_countries["is_sample"] = False
    # ---- per cohort (for the cohort filter on the Impact overview); counts 1–4 hidden / grouped
    co = d.assign(cohort=d["Start Cohort"].map(lambda c: f"C{int(c):02d}"),
                  country=d["Origin Country"].astype(str).str.strip().str.title())
    co = co.dropna(subset=["country"])
    co = co[~co["country"].str.lower().isin(["", "nan", "none", "<na>", "not recorded", "unknown", "n/a", "prefer not to say"])]
    origin_by_cohort = co.groupby(["cohort", "country"]).size().reset_index(name="trainees")
    origin_by_cohort.loc[origin_by_cohort["trainees"] < MIN_GROUP, "country"] = f"Other (groups under {MIN_GROUP})"
    origin_by_cohort = origin_by_cohort.groupby(["cohort", "country"], as_index=False)["trainees"].sum()
    origin_by_cohort["is_sample"] = False
    # which countries are in each cohort, as random numbers instead of names (so the Countries card can count
    # different countries for any set of cohorts without storing who comes from where; new numbers on every run)
    import random
    names = sorted(co["country"].unique())
    codes = random.sample(range(1, 10 * len(names) + 10), len(names))
    country_keys = co[["cohort", "country"]].drop_duplicates().assign(country_key=lambda x: x["country"].map(dict(zip(names, codes))))
    country_keys = country_keys[["cohort", "country_key"]].sample(frac=1).sort_values("cohort").reset_index(drop=True)
    country_keys["is_sample"] = False
    gc = d[d["status"] == "graduated"].assign(cohort=lambda x: x["Start Cohort"].map(lambda c: f"C{int(c):02d}"))
    gender_by_cohort = pd.crosstab(gc["cohort"], gc["gender"]).reindex(columns=["woman", "man", "non-binary or other"], fill_value=0)
    gender_by_cohort.columns = ["women", "men", "nonbinary_or_other"]
    gender_by_cohort = suppress(gender_by_cohort.reset_index())
    gender_by_cohort["is_sample"] = False
    origin_range = range_counts(cy["start_year"], cy["country"], "country")        # page B: every country, small counts hidden
    origin_range["is_sample"] = False

    # ---- students supported (page B): a trainee counts in every year they were in class, or in job support
    #      (up to 12 months after graduating). Each person counted once per year / per range.
    today = pd.Timestamp.today()
    end = d["start"].copy()
    gr = d["status"] == "graduated"
    end[gr] = d.loc[gr, "grad"] + pd.DateOffset(months=12)
    end[d["status"].isin(["studying", "on-hold"])] = today
    end = end.fillna(d["grad"]).fillna(d["start"]).clip(upper=today)
    sy, ey = d["start"].dt.year, end.dt.year
    ok = sy.notna() & ey.notna()
    yrs = list(range(int(sy[ok].min()), int(ey[ok].max()) + 1)) if ok.any() else []
    students_supported = pd.DataFrame(
        [{"from_year": a, "to_year": b, "students": int((ok & (sy <= b) & (ey >= a)).sum())} for i, a in enumerate(yrs) for b in yrs[i:]])
    students_supported["is_sample"] = False
    rows = []
    for y in yrs:
        act = d[ok & (sy <= y) & (ey >= y)]
        for c, n in act["Start Cohort"].value_counts().sort_index().items():
            rows.append({"year": y, "cohort": f"C{int(c):02d}", "students": int(n)})
    students_by_cohort = pd.DataFrame(rows, columns=["year", "cohort", "students"])
    students_by_cohort["students"] = students_by_cohort["students"].astype("Int64").mask(students_by_cohort["students"].between(1, MIN_GROUP - 1))
    students_by_cohort["is_sample"] = False


    # ---- write
    DATA.mkdir(exist_ok=True)
    with pd.ExcelWriter(DATA / "HYF_counts.xlsx") as xw:
        pd.DataFrame({"About this file": [
            "Counts only, made from the Dojo trainee export with tools/make_cloud_data.py.",
            f"Counts from 1 to {MIN_GROUP - 1} are left empty to protect privacy.",
            "No names, IDs or per-person rows."]}).to_excel(xw, sheet_name="Read me", index=False)
        for name, t in tables.items():
            t.to_excel(xw, sheet_name=name, index=False)
    ind = DATA / "HYF_indicators.xlsx"
    sheets = pd.read_excel(ind, sheet_name=None) if ind.exists() else {}
    sheets["historic"] = historic
    sheets["historic_gender"] = hgender
    sheets["origin"] = origin
    sheets["origin_countries"] = origin_countries
    sheets["origin_range"] = origin_range
    sheets["origin_by_cohort"] = origin_by_cohort
    sheets["gender_by_cohort"] = gender_by_cohort
    sheets["country_keys_by_cohort"] = country_keys
    sheets["students_supported"] = students_supported
    sheets["students_by_cohort"] = students_by_cohort
    sheets["classes"] = classes
    sheets["all_gender"] = all_gender
    sheets["job_paths"] = job_paths
    sheets["job_paths_by_cohort"] = job_paths_by_cohort
    with pd.ExcelWriter(ind) as xw:
        for name, t in sheets.items():
            t.to_excel(xw, sheet_name=name, index=False)
    print(f"Wrote {DATA / 'HYF_counts.xlsx'} and updated {ind} "
          f"({len(historic)} historic classes, {int(historic.graduates.sum())} graduates; "
          f"all programmes: {len(classes)} classes, {int(classes.graduates.sum())} graduates).")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
