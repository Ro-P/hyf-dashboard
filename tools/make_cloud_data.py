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

import sys
from pathlib import Path

import pandas as pd

MIN_GROUP = 5
NEW_PROGRAMME_FROM = 55  # classes from C55 onwards are the new programme
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "real" if (ROOT / "data" / "real").exists() else ROOT / "data"  # prod data folder

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


def main(src: str) -> None:
    d = pd.read_excel(src, sheet_name="dojo.trainees")
    d = d[["Start Cohort", "Learning Status", "Gender", "Origin Country", "Background", "Start Date",
           "Graduation Date", "Quit Reason", "Job Path"]].copy()  # drop IDs and anything else
    d["start"] = pd.to_datetime(d["Start Date"], errors="coerce", utc=True).dt.tz_localize(None)
    d["grad"] = pd.to_datetime(d["Graduation Date"], errors="coerce", utc=True).dt.tz_localize(None)
    d["status"] = d["Learning Status"].str.strip().str.lower()
    d["gender"] = d["Gender"].fillna("no answer").str.strip().str.lower().replace({"other": "non-binary or other", "non-binary": "non-binary or other"})
    d["job"] = d["Job Path"].map(JOB)
    g = d["status"] == "graduated"

    # ---- historic tab (classes before C55), per class: programme counts only
    h = d[d["Start Cohort"] < NEW_PROGRAMME_FROM]
    rows = []
    for c, r in h.groupby("Start Cohort"):
        gr = r[r["status"] == "graduated"]
        rows.append(dict(
            cohort=f"C{int(c):02d}",
            graduation_date=gr["grad"].max().date() if gr["grad"].notna().any() else None,
            graduation_year=int(gr["grad"].max().year) if gr["grad"].notna().any() else None,
            started=len(r), graduates=len(gr), quit=int((r["status"] == "quit").sum()),
            still_studying=int(r["status"].isin(["studying", "on-hold"]).sum()),
            working_in_it=int(gr["job"].isin(["tech_job", "internship"]).sum()),
            placed_6m_confirmed=None, status_recorded=None,  # job start dates are not in the Dojo export
            is_sample=False,
        ))
    historic = pd.DataFrame(rows)

    # ---- historic_gender: graduates by gender per graduation year (+ total row), suppressed
    hg = h[h["status"] == "graduated"].assign(year=lambda x: x["grad"].dt.year)
    gt = pd.crosstab(hg["year"], hg["gender"]).reindex(columns=["woman", "man", "non-binary or other", "no answer"], fill_value=0)
    gt.columns = ["women", "men", "nonbinary_or_other", "no_answer"]
    gt = gt.reset_index().rename(columns={"year": "graduation_year"})
    gt["graduation_year"] = gt["graduation_year"].astype(int).astype(str)
    total = gt.drop(columns="graduation_year").sum().to_frame().T
    total.insert(0, "graduation_year", "All")
    hgender = suppress(pd.concat([gt, total], ignore_index=True))
    hgender["gender_responses"] = hgender[["women", "men", "nonbinary_or_other"]].sum(axis=1, min_count=1)
    hgender["is_sample"] = False

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
    with pd.ExcelWriter(ind) as xw:
        for name, t in sheets.items():
            t.to_excel(xw, sheet_name=name, index=False)
    print(f"Wrote {DATA / 'HYF_counts.xlsx'} and updated {ind} "
          f"({len(historic)} historic classes, {int(historic.graduates.sum())} graduates).")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
