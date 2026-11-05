"""
HYF Ask-the-Data Dashboard
--------------------------
A small local app: put CSV/Excel files in the `data/` folder, ask a question
in plain language, and Claude writes the analysis + chart code. The code runs
on YOUR laptop against YOUR files. Only the table structure (column names,
types and – optionally – a few example values) is sent to Claude, never the
full dataset.

Without an API key you can still build charts yourself (Build tab),
save them to dashboards and download a dashboard as a single HTML file.

Run:  streamlit run app.py
"""

from __future__ import annotations

import builtins
import hmac
import html
import json
import os
import re
import traceback
import uuid
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import brand

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # optional
    pass

# On Streamlit Cloud, settings come from "Secrets" (st.secrets) instead of .env
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, (str, int, float, bool)):
            os.environ.setdefault(_k, str(_v))
except Exception:  # no secrets file: fine when running locally
    pass

# --------------------------------------------------------------------------- #
# Settings (change in .env)
# --------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).parent
# APP_ENV picks the environment: "dev" (fictional data in data/mock) or "prod" (real counts in data/real).
# Leave it empty to use the data/ folder itself (laptop use).
APP_ENV = os.getenv("APP_ENV", "").strip().lower()
_ENV_DATA = {"dev": BASE_DIR / "data" / "mock", "prod": BASE_DIR / "data" / "real"}
DATA_DIR = Path(os.getenv("HYF_DATA_DIR", _ENV_DATA.get(APP_ENV, BASE_DIR / "data"))).expanduser()
SAVED_FILE = BASE_DIR / "saved_dashboards.json"
APP_VERSION = "2026-11-05"
INDICATORS_FILE = Path(os.getenv("HYF_INDICATORS_FILE", DATA_DIR / "HYF_indicators.xlsx")).expanduser()
MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5")
# How many example rows per table Claude may see. 0 = structure only.
SAMPLE_ROWS = int(os.getenv("SAMPLE_ROWS_SENT", "3"))
# Set ENABLE_ASK=false to hide the Ask Claude tab (e.g. in the cloud version)
DEMO_MODE = os.getenv("DEMO_MODE", "true" if APP_ENV == "dev" else "false").strip().lower() in ("true", "1", "yes", "on")
ENABLE_ASK = os.getenv("ENABLE_ASK", "true").strip().lower() not in ("false", "0", "no", "off")
MAX_FIX_ATTEMPTS = 2

# Columns that look personal are never sent to Claude (not even examples).
PII_PATTERN = re.compile(
    r"(name|naam|e-?mail|phone|telefoon|tel|address|adres|street|straat|"
    r"postcode|zip|bsn|birth|geboorte|dob|iban|passport|paspoort)",
    re.IGNORECASE,
)

HYF_COLORS = brand.CHART_COLORS  # HYF palette, set in brand.py
brand.apply_plotly_theme()

EXAMPLE_QUESTIONS = [
    "How many trainees started and graduated per year since 2016?",
    "Which role families did graduates get jobs in, tech jobs vs internships?",
    "Compare the graduation rate of the first 20 classes with the last 20",
    "What happened to graduates who didn't find a tech job?",
]

# --------------------------------------------------------------------------- #
# Data loading
# --------------------------------------------------------------------------- #
def safe_name(text: str) -> str:
    name = re.sub(r"\W+", "_", text.strip().lower()).strip("_")
    return name if not name[:1].isdigit() else f"t_{name}"


def _folder_signature(folder: Path) -> tuple:
    if not folder.exists():
        return ()
    return tuple(
        (p.name, p.stat().st_mtime)
        for p in sorted(folder.iterdir())
        if p.suffix.lower() in {".csv", ".xlsx", ".xls"}
    )


@st.cache_data(show_spinner="Loading your data…")
def load_tables(folder: str, _signature: tuple) -> dict[str, pd.DataFrame]:
    tables: dict[str, pd.DataFrame] = {}
    for path in sorted(Path(folder).iterdir()):
        suffix = path.suffix.lower()
        if path.name.startswith(("~$", ".")):
            continue
        if suffix == ".csv":
            tables[safe_name(path.stem)] = pd.read_csv(path)
        elif suffix in {".xlsx", ".xls"}:
            sheets = pd.read_excel(path, sheet_name=None)
            sheets = {k: v for k, v in sheets.items() if not str(k).strip().lower().startswith("read me")}
            for sheet, df in sheets.items():
                key = path.stem if len(sheets) == 1 else f"{path.stem}_{sheet}"
                tables[safe_name(key)] = df
    # Parse obvious date columns
    for df in tables.values():
        for col in df.columns:
            if df[col].dtype == object and re.search(r"date|datum", str(col), re.I):
                parsed = pd.to_datetime(df[col], errors="coerce")
                if parsed.notna().mean() > 0.8:
                    df[col] = parsed
    return tables


def is_pii(col: str) -> bool:
    return bool(PII_PATTERN.search(str(col)))


def describe_tables(tables: dict[str, pd.DataFrame]) -> str:
    """Structure-only description of the data that is sent to Claude."""
    parts = []
    for name, df in tables.items():
        lines = [f"### Table `{name}` — {len(df):,} rows"]
        for col in df.columns:
            s = df[col]
            info = f"- `{col}` ({s.dtype}, {s.nunique()} distinct, {s.isna().sum()} missing)"
            if is_pii(col):
                info += " [personal data – values hidden, do not display]"
            elif SAMPLE_ROWS > 0:
                if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
                    if s.notna().any():
                        info += f" range {s.min():g} – {s.max():g}"
                elif pd.api.types.is_datetime64_any_dtype(s):
                    if s.notna().any():
                        info += f" from {s.min():%Y-%m-%d} to {s.max():%Y-%m-%d}"
                elif s.nunique() <= 12:
                    vals = ", ".join(map(str, s.dropna().unique()[:12]))
                    info += f" values: {vals}"
            lines.append(info)
        if SAMPLE_ROWS > 0:
            safe_cols = [c for c in df.columns if not is_pii(c)]
            sample = df[safe_cols].head(SAMPLE_ROWS)
            lines.append("Example rows:\n" + sample.to_csv(index=False))
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


# --------------------------------------------------------------------------- #
# Claude
# --------------------------------------------------------------------------- #
SYSTEM_PROMPT = """You are the data analyst for HackYourFuture (HYF), a Dutch \
non-profit coding school for people from refugee backgrounds. HYF celebrates \
its 10-year anniversary. You turn questions into small, beautiful dashboards.

You write Python code that runs locally against the user's data. Available:
- `tables`: dict of pandas DataFrames (names below); each table is also a variable with the same name
- `pd`, `np`, `px` (plotly.express), `go` (plotly.graph_objects), `HYF_COLORS` (list of hex colours)

Your code MUST set a variable `result`: a list of dashboard items, in display order:
- {"type": "metric", "label": str, "value": str|number, "delta": optional str}
- {"type": "chart", "title": str, "fig": plotly figure}
- {"type": "table", "title": str, "df": DataFrame}
- {"type": "text", "text": markdown str}   (a short insight)

Rules:
- Put 2–4 KPI metrics first when it makes sense, then 1–3 charts, then an optional short insight.
- Charts: clear titles, labelled axes, no chart junk, use HYF_COLORS. Years as categories/integers, not floats.
- Never show personal data (names, emails, phones, addresses). Aggregate; hide groups smaller than 5 people.
- Do not read or write files, use the network, or import anything except pandas, numpy, plotly, math, datetime, statistics.
- If the data cannot answer the question, set result to one text item explaining what data is missing.

Reply with ONE short sentence describing the dashboard, then the code in a single ```python block."""


def get_client():
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return None
    from anthropic import Anthropic

    return Anthropic(api_key=key)


def ask_claude(messages: list[dict]) -> str:
    client = get_client()
    resp = client.messages.create(
        model=MODEL, max_tokens=4000, system=SYSTEM_PROMPT, messages=messages
    )
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


def split_reply(reply: str) -> tuple[str, str]:
    match = re.search(r"```(?:python)?\s*\n(.*?)```", reply, re.S)
    code = match.group(1).strip() if match else ""
    summary = reply[: match.start()].strip() if match else reply.strip()
    return summary, code


# --------------------------------------------------------------------------- #
# Running generated code (restricted)
# --------------------------------------------------------------------------- #
ALLOWED_MODULES = {"pandas", "numpy", "plotly", "math", "datetime", "statistics"}
BLOCKED_BUILTINS = {"open", "exec", "eval", "compile", "input", "breakpoint", "exit", "quit"}


def _safe_import(name, *args, **kwargs):
    if name.split(".")[0] not in ALLOWED_MODULES:
        raise ImportError(f"Importing '{name}' is not allowed in dashboard code")
    return builtins.__import__(name, *args, **kwargs)


def run_code(code: str, tables: dict[str, pd.DataFrame]) -> list[dict]:
    safe_builtins = {k: v for k, v in vars(builtins).items() if k not in BLOCKED_BUILTINS}
    safe_builtins["__import__"] = _safe_import
    copies = {k: v.copy() for k, v in tables.items()}
    ns = {
        "__builtins__": safe_builtins,
        "pd": pd, "np": np, "px": px, "go": go,
        "HYF_COLORS": HYF_COLORS,
        "tables": copies,
        **copies,
    }
    exec(code, ns)  # noqa: S102 – generated code, restricted namespace, local only
    result = ns.get("result")
    if not isinstance(result, list):
        raise ValueError("The code did not set `result` to a list of dashboard items")
    return result


def generate_dashboard(question: str, tables, history: list[dict]) -> dict:
    """Ask Claude, run the code, and let Claude fix errors a couple of times."""
    schema = describe_tables(tables)
    messages = []
    for h in history[-3:]:  # short memory so follow-up questions work
        messages.append({"role": "user", "content": h["question"]})
        messages.append({"role": "assistant", "content": f"{h['summary']}\n```python\n{h['code']}\n```"})
    messages.append(
        {"role": "user", "content": f"Data available:\n\n{schema}\n\nQuestion: {question}"}
    )

    last_error = ""
    for attempt in range(MAX_FIX_ATTEMPTS + 1):
        reply = ask_claude(messages)
        summary, code = split_reply(reply)
        if not code:
            return {"question": question, "summary": summary, "code": "", "items": [{"type": "text", "text": summary}]}
        try:
            items = run_code(code, tables)
            return {"question": question, "summary": summary, "code": code, "items": items}
        except Exception:
            last_error = traceback.format_exc(limit=3)
            messages += [
                {"role": "assistant", "content": reply},
                {"role": "user", "content": f"That code failed:\n{last_error}\nPlease fix it. Same reply format."},
            ]
    raise RuntimeError(f"Could not build this dashboard.\n\n{last_error}")


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def fmt_value(v) -> str:
    if isinstance(v, (bool, np.bool_)):
        return str(v)
    if isinstance(v, (int, np.integer)):
        return f"{v:,}"
    if isinstance(v, (float, np.floating)):
        return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.1f}"
    return str(v)


def render_items(items: list[dict], key: str, heading: str = "") -> None:
    """`heading` = title already shown above; charts with the same title don't repeat it."""
    metrics = [i for i in items if i.get("type") == "metric"]
    if metrics:
        cols = st.columns(min(len(metrics), 4))
        for n, m in enumerate(metrics):
            cols[n % len(cols)].metric(m.get("label", ""), fmt_value(m.get("value")), m.get("delta"))
    for n, item in enumerate(i for i in items if i.get("type") != "metric"):
        t = item.get("type")
        if t == "chart" and item.get("fig") is not None:
            fig = item["fig"]
            if item.get("title") and item["title"] != heading and not fig.layout.title.text:
                fig.update_layout(title=item["title"])
            fig.update_layout(margin=dict(l=10, r=10, t=50 if fig.layout.title.text else 15, b=10))
            st.plotly_chart(fig, width="stretch", key=f"{key}-chart-{n}")
        elif t == "table":
            if item.get("title"):
                st.markdown(f"**{item['title']}**")
            st.dataframe(item.get("df"), width="stretch", hide_index=True)
        elif t == "text":
            st.info(item.get("text", ""))


# --------------------------------------------------------------------------- #
# Build-it-yourself charts (no AI)
# --------------------------------------------------------------------------- #
CHART_TYPES = ["Bar", "Line", "Area", "Pie", "Scatter", "KPI number", "Table"]
MEASURES = {
    "Count rows": "count",
    "Count distinct": "nunique",
    "Sum": "sum",
    "Average": "mean",
    "Percentage (share of True / 1)": "pct",
    "Median": "median",
    "Minimum": "min",
    "Maximum": "max",
}
NONE = "—"


def _agg_func(name: str):
    return (lambda s: s.mean() * 100) if name == "pct" else name


def apply_filters(df: pd.DataFrame, filters: list[dict] | None) -> pd.DataFrame:
    for f in filters or []:
        if f.get("col") in df.columns and f.get("values"):
            wanted = {str(v) for v in f["values"]}
            df = df[df[f["col"]].astype(str).isin(wanted)]
    return df


def measure_label(spec: dict) -> str:
    label = next((k for k, v in MEASURES.items() if v == spec.get("agg")), "Count rows")
    if spec.get("agg", "count") == "count":
        return "Number of rows"
    return f"{label.split(' (')[0]} of {spec.get('y')}"


def aggregate(df: pd.DataFrame, spec: dict, groups: list[str]) -> tuple[pd.DataFrame, str]:
    agg, y = spec.get("agg", "count"), spec.get("y")
    out_col = measure_label(spec)
    if agg == "count" or not y:
        if groups:
            return df.groupby(groups, dropna=False).size().reset_index(name=out_col), out_col
        return pd.DataFrame({out_col: [len(df)]}), out_col
    if groups:
        out = df.groupby(groups, dropna=False)[y].agg(_agg_func(agg)).reset_index()
        return out.rename(columns={y: out_col}), out_col
    return pd.DataFrame({out_col: [df[y].agg(_agg_func(agg))]}), out_col


def validate_spec(spec: dict) -> str | None:
    chart, agg = spec["chart"], spec.get("agg", "count")
    if agg != "count" and not spec.get("y"):
        return "Pick a value column for this measure."
    if chart in ("Bar", "Line", "Area", "Pie") and not spec.get("x"):
        return "Pick a column to group by."
    if chart == "Scatter" and not (spec.get("x") and spec.get("y")):
        return "A scatter plot needs both a group-by (x) column and a value (y) column."
    return None


def build_items(spec: dict, tables: dict[str, pd.DataFrame]) -> list[dict]:
    if spec["table"] not in tables:
        raise ValueError(f"Table '{spec['table']}' is no longer in the data folder")
    df = apply_filters(tables[spec["table"]], spec.get("filters"))
    chart, x, color = spec["chart"], spec.get("x"), spec.get("color")
    title = spec.get("title") or ""

    if chart == "KPI number":
        data, col = aggregate(df, spec, [])
        value = data[col].iloc[0]
        if spec.get("agg") == "pct":
            value = f"{value:.0f}%"
        return [{"type": "metric", "label": title or measure_label(spec), "value": value}]

    if chart == "Table":
        groups = [c for c in (x, color) if c]
        data = aggregate(df, spec, groups)[0] if groups else df
        return [{"type": "table", "title": title, "df": data}]

    if chart == "Scatter":
        fig = px.scatter(df, x=x, y=spec["y"], color=color)
        return [{"type": "chart", "title": title, "fig": fig}]

    groups = [x] + ([color] if color and chart != "Pie" else [])
    data, ycol = aggregate(df, spec, groups)
    data = data.sort_values(x)
    if chart == "Pie":
        fig = px.pie(data, names=x, values=ycol, hole=0.45, color_discrete_sequence=HYF_COLORS)
    else:
        make = {"Bar": px.bar, "Line": px.line, "Area": px.area}[chart]
        extra = {"barmode": "group"} if chart == "Bar" else {}
        fig = make(data, x=x, y=ycol, color=color, **extra)
        if chart == "Line":
            fig.update_traces(mode="lines+markers")
        if pd.api.types.is_integer_dtype(data[x]):  # e.g. years: no 2,016.5 ticks
            fig.update_xaxes(type="category")
        fig.update_layout(xaxis_title=x, yaxis_title=ycol)
    return [{"type": "chart", "title": title, "fig": fig}]


def panel_items(panel: dict, tables) -> list[dict]:
    return build_items(panel["spec"], tables) if panel.get("spec") else run_code(panel["code"], tables)


# --------------------------------------------------------------------------- #
# Saved dashboards
# --------------------------------------------------------------------------- #
def load_saved() -> dict:
    if SAVED_FILE.exists():
        return json.loads(SAVED_FILE.read_text(encoding="utf-8"))
    return {}


def save_saved(data: dict) -> None:
    SAVED_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def add_to_dashboard(board: str, entry: dict) -> None:
    data = load_saved()
    data.setdefault(board, []).append(
        {
            "id": uuid.uuid4().hex[:8],
            "question": entry["question"],
            "summary": entry.get("summary", ""),
            "code": entry.get("code", ""),
            "spec": entry.get("spec"),
            "wide": bool(entry.get("wide")),
            "saved_at": datetime.now().isoformat(timespec="minutes"),
        }
    )
    save_saved(data)


def save_controls(entry: dict, key: str) -> None:
    """Dashboard picker + Save button, shared by the Ask and Build tabs."""
    boards = list(load_saved().keys())
    c1, c2, c3 = st.columns([2, 1, 3])
    board = c1.selectbox(
        "Dashboard", boards + ["➕ New dashboard…"], key=f"board-{key}", label_visibility="collapsed"
    )
    new_name = None
    if board == "➕ New dashboard…":
        new_name = c3.text_input(
            "Name", placeholder="e.g. 10-year anniversary", key=f"new-{key}", label_visibility="collapsed"
        )
    if c2.button("📌 Save", key=f"save-{key}"):
        target = (new_name or "").strip() if board == "➕ New dashboard…" else board
        if target:
            add_to_dashboard(target, entry)
            st.toast(f"Saved to “{target}”")
        else:
            st.warning("Give the new dashboard a name first.")


def dashboard_html(board: str, panels: list[dict], tables) -> str:
    """A single, self-contained HTML file of a dashboard (works offline)."""
    esc = html.escape
    sections, first_chart = [], True
    for panel in panels:
        try:
            items = panel_items(panel, tables)
        except Exception as exc:
            items = [{"type": "text", "text": f"Could not build this view: {exc}"}]
        cls = ' class="wide"' if panel.get("wide") else ""
        block = [f"<section{cls}><h2>{esc(panel['question'])}</h2>"]
        metrics = [i for i in items if i.get("type") == "metric"]
        if metrics:
            block.append('<div class="kpis">' + "".join(
                f'<div class="kpi"><div class="v">{esc(fmt_value(m.get("value")))}</div>'
                f'<div class="l">{esc(str(m.get("label", "")))}</div></div>' for m in metrics
            ) + "</div>")
        for item in items:
            t = item.get("type")
            if t == "chart" and item.get("fig") is not None:
                fig = item["fig"]
                if item.get("title") and item["title"] != panel["question"] and not fig.layout.title.text:
                    fig.update_layout(title=item["title"])
                fig.update_layout(height=380, margin=dict(l=10, r=10, t=50 if fig.layout.title.text else 15, b=10))
                block.append(fig.to_html(full_html=False, include_plotlyjs=first_chart,
                                         default_width="100%", default_height="380px",
                                         config={"displaylogo": False, "responsive": True}))
                first_chart = False
            elif t == "table":
                if item.get("title") and item["title"] != panel["question"]:
                    block.append(f"<h3>{esc(item['title'])}</h3>")
                block.append(item["df"].to_html(index=False, classes="tbl", border=0))
            elif t == "text":
                block.append(f"<p class='note'>{esc(item.get('text', ''))}</p>")
        block.append("</section>")
        sections.append("\n".join(block))
    stamp = datetime.now().strftime("%d %B %Y")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(board)} · HackYourFuture</title>
<style>
{brand.export_css()}
main{{max-width:1200px;margin:0 auto;padding:24px 16px;
display:grid;align-items:start;grid-template-columns:repeat(auto-fit,minmax(min(100%,520px),1fr));gap:16px}}
section{{overflow:hidden;background:#fff;border:1px solid #E8DFC4;border-radius:12px;padding:16px;min-width:0}}
section.wide{{grid-column:1/-1}} h2{{font-size:16px;margin:0 0 12px}} h3{{font-size:14px}}
.kpis{{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:8px}}
.kpi{{flex:1 1 120px;background:#FAF5D9;border-radius:10px;padding:12px}}
.kpi .v{{font-size:26px;font-weight:700}} .kpi .l{{font-size:13px;opacity:.75}}
.tbl{{border-collapse:collapse;width:100%;font-size:13px}} .tbl th,.tbl td{{padding:6px 8px;border-bottom:1px solid #eee;text-align:left}}
.note{{background:#FFF9D6;border-radius:8px;padding:10px}}
footer{{text-align:center;font-size:12px;opacity:.6;padding:16px}}
</style></head><body>
{brand.export_header(board, f"HackYourFuture · data as of {stamp}")}
<main>{''.join(sections)}</main>
<footer>Made with the HYF dashboard app</footer>
<script>function fit(){{document.querySelectorAll('.plotly-graph-div').forEach(d=>window.Plotly&&Plotly.Plots.resize(d))}}
window.addEventListener('load',fit);window.addEventListener('resize',fit);</script></body></html>"""


# --------------------------------------------------------------------------- #
# App
# --------------------------------------------------------------------------- #
NEW_BOARD = "➕ New dashboard…"
BUILDER_DEFAULTS = {
    "b_chart": "Bar", "b_measure": "Count rows", "b_x": NONE, "b_y": NONE,
    "b_color": NONE, "b_fcol": NONE, "b_fvals": [], "b_title": "", "b_wide": False,
}


def update_panels(board: str, change) -> None:
    data = load_saved()
    data[board] = change(data.get(board, []))
    if not data[board]:
        del data[board]
    save_saved(data)


def move_panel(board: str, panel_id: str, step: int) -> None:
    def change(panels):
        i = next(n for n, p in enumerate(panels) if p["id"] == panel_id)
        j = max(0, min(len(panels) - 1, i + step))
        panels.insert(j, panels.pop(i))
        return panels
    update_panels(board, change)


def remove_panel(board: str, panel_id: str) -> None:
    update_panels(board, lambda panels: [p for p in panels if p["id"] != panel_id])


def panel_rows(panels: list[dict]) -> list[list[dict]]:
    """Two charts per row; a 'wide' chart gets a row of its own."""
    rows, current = [], []
    for p in panels:
        if p.get("wide"):
            if current:
                rows.append(current)
                current = []
            rows.append([p])
        else:
            current.append(p)
            if len(current) == 2:
                rows.append(current)
                current = []
    if current:
        rows.append(current)
    return rows


def render_board(board: str, tables, key_prefix: str) -> None:
    """Show every chart on a dashboard, with ↑ ↓ ✕ controls."""
    panels = load_saved().get(board, [])
    if not panels:
        st.write("No charts on this dashboard yet.")
        return
    for row in panel_rows(panels):
        cols = [st.container()] if row[0].get("wide") else st.columns(2)
        for col, panel in zip(cols, row):
            idx = next(n for n, p in enumerate(panels) if p["id"] == panel["id"])
            with col, st.container(border=True):
                head, b_up, b_down, b_rm = st.columns([8, 1, 1, 1])
                head.markdown(f"**{panel['question']}**")
                b_up.button("↑", key=f"{key_prefix}-up-{panel['id']}", help="Move up",
                            disabled=idx == 0, on_click=move_panel, args=(board, panel["id"], -1))
                b_down.button("↓", key=f"{key_prefix}-down-{panel['id']}", help="Move down",
                              disabled=idx == len(panels) - 1, on_click=move_panel, args=(board, panel["id"], 1))
                b_rm.button("✕", key=f"{key_prefix}-rm-{panel['id']}", help="Remove from dashboard",
                            on_click=remove_panel, args=(board, panel["id"]))
                try:
                    render_items(panel_items(panel, tables), key=f"{key_prefix}-{panel['id']}",
                                 heading=panel["question"])
                except Exception as exc:
                    st.error(f"This view no longer fits the data: {exc}")


def download_board_button(board: str, tables, key: str) -> None:
    panels = load_saved().get(board, [])
    st.download_button(
        "⬇ Download as HTML", data=dashboard_html(board, panels, tables),
        file_name=f"{safe_name(board) or 'dashboard'}.html", mime="text/html", key=key,
        disabled=not panels,
        help="One file you can email, open in any browser or show at the event. Works offline.",
    )


def _add_chart(board: str, entry: dict) -> None:
    """Button callback: save the chart, then clear the form for the next one."""
    add_to_dashboard(board, entry)
    st.session_state["b_board"] = board
    st.session_state["b_new_name"] = ""
    for k, v in BUILDER_DEFAULTS.items():
        st.session_state[k] = v
    st.session_state["b_flash"] = f"Added “{entry['question']}”. Make your next chart below."


def _clear_form() -> None:
    for k, v in BUILDER_DEFAULTS.items():
        st.session_state[k] = v


def builder_tab(tables: dict[str, pd.DataFrame]) -> None:
    st.write("Build a dashboard chart by chart by picking options. No AI is used, so it is free and works without an API key.")

    # Step A: which dashboard are we building? ------------------------------
    boards = list(load_saved().keys())
    if st.session_state.get("b_board") not in boards + [NEW_BOARD]:
        st.session_state["b_board"] = boards[0] if boards else NEW_BOARD
    a1, a2 = st.columns([1, 1])
    board_choice = a1.selectbox("Dashboard you're building", boards + [NEW_BOARD], key="b_board")
    board = board_choice
    if board_choice == NEW_BOARD:
        board = a2.text_input("Name of the new dashboard", placeholder="e.g. 10-year anniversary",
                              key="b_new_name").strip()

    if msg := st.session_state.pop("b_flash", None):
        st.success(msg)

    # Step B: the chart -----------------------------------------------------
    with st.container(border=True):
        h1, h2 = st.columns([5, 1])
        h1.markdown("**New chart**")
        h2.button("Clear form", on_click=_clear_form, width="stretch")
        c1, c2, c3 = st.columns(3)
        table = c1.selectbox("1 · Table", list(tables), key="b_table")
        df = tables[table]
        cols = [c for c in df.columns if not is_pii(c)]  # personal columns are not offered
        value_cols = [c for c in cols if pd.api.types.is_numeric_dtype(df[c]) or pd.api.types.is_bool_dtype(df[c])]
        # Reset choices that don't exist in a newly picked table
        for k, opts in (("b_x", cols), ("b_color", cols), ("b_fcol", cols), ("b_y", cols)):
            if st.session_state.get(k, NONE) not in [NONE] + opts:
                st.session_state[k] = NONE
        chart = c2.selectbox("2 · Chart type", CHART_TYPES, key="b_chart")
        measure = c3.selectbox("3 · Measure", list(MEASURES), key="b_measure")
        agg = MEASURES[measure]

        c4, c5, c6 = st.columns(3)
        x = None
        if chart != "KPI number":
            x_label = "4 · X-axis" if chart == "Scatter" else ("4 · Group by (optional)" if chart == "Table" else "4 · Group by")
            x = c4.selectbox(x_label, [NONE] + cols, key="b_x")
        y_options = value_cols if agg != "nunique" else cols
        if st.session_state.get("b_y", NONE) not in [NONE] + y_options:
            st.session_state["b_y"] = NONE
        y = c5.selectbox(
            "5 · Value column", [NONE] + y_options, key="b_y",
            disabled=(agg == "count" and chart != "Scatter"),
            help="Not needed for 'Count rows'. For 'Percentage', pick a True/False column such as employed_within_6_months.",
        )
        color = None
        if chart in ("Bar", "Line", "Area", "Scatter", "Table"):
            color = c6.selectbox("6 · Split by colour (optional)", [NONE] + cols, key="b_color")

        with st.expander("Filter (optional)"):
            f1, f2 = st.columns([1, 2])
            fcol = f1.selectbox("Only rows where", [NONE] + cols, key="b_fcol")
            fvals = []
            if fcol != NONE:
                options = sorted(df[fcol].dropna().astype(str).unique())[:200]
                st.session_state["b_fvals"] = [v for v in st.session_state.get("b_fvals", []) if v in options]
                fvals = f2.multiselect("is one of", options, key="b_fvals")

        t1, t2 = st.columns([4, 1])
        title = t1.text_input("Title", placeholder="e.g. Trainees per year", key="b_title")
        wide = t2.checkbox("Full width", key="b_wide", help="Let this chart use the whole width of the dashboard")

        spec = {
            "table": table,
            "chart": chart,
            "agg": agg,
            "x": None if x in (None, NONE) else x,
            "y": None if (y == NONE or (agg == "count" and chart != "Scatter")) else y,
            "color": None if color in (None, NONE) else color,
            "filters": [{"col": fcol, "values": fvals}] if fcol != NONE and fvals else [],
            "title": title.strip(),
        }
        problem = validate_spec(spec)
        items = None
        if problem:
            st.info(problem)
        else:
            try:
                items = build_items(spec, tables)
            except Exception as exc:
                st.warning(f"This combination doesn't work: {exc}")
        if items:
            st.caption("Preview")
            render_items(items, key="builder-preview")
            question = spec["title"] or (
                f"{measure_label(spec)}" + (f" by {spec['x']}" if spec["x"] else "") + f" ({table})"
            )
            entry = {"question": question, "spec": spec, "wide": wide}
            st.button(
                f"➕ Add to “{board}”" if board else "➕ Add to dashboard",
                type="primary", disabled=not board, on_click=_add_chart, args=(board, entry),
                help=None if board else "Give the new dashboard a name first (top of the page).",
            )

    # Step C: the dashboard so far ------------------------------------------
    if board and board in load_saved():
        st.divider()
        d1, d2 = st.columns([3, 1])
        d1.subheader(f"{board} · {len(load_saved()[board])} charts")
        with d2:
            download_board_button(board, tables, key="dl-builder")
        render_board(board, tables, key_prefix="build")


def auth_mode() -> str:
    """none | password | google. Set AUTH_MODE, or it follows from which settings exist."""
    mode = os.getenv("AUTH_MODE", "").strip().lower()
    if mode:
        return mode
    if os.getenv("AUTH_CLIENT_ID"):
        return "google"
    if os.getenv("APP_PASSWORD"):
        return "password"
    return "none"


def require_login() -> None:
    """Stop the page here until the viewer has logged in (when a login is configured)."""
    mode = auth_mode()
    if mode == "none":
        return
    if mode == "password":
        if st.session_state.get("auth_ok"):
            with st.sidebar:
                if st.button("Log out"):
                    st.session_state.auth_ok = False
                    st.rerun()
            return
        brand.header("Impact & data", "HackYourFuture")
        st.write("This dashboard is for HackYourFuture colleagues. Enter the password you received.")
        with st.form("login"):
            pw = st.text_input("Password", type="password")
            ok = st.form_submit_button("Log in", type="primary")
        if ok:
            if hmac.compare_digest(pw.encode(), os.getenv("APP_PASSWORD", "").encode()) and os.getenv("APP_PASSWORD"):
                st.session_state.auth_ok = True
                st.rerun()
            st.error("That password is not correct. Ask the dashboard owner for the current password.")
        st.stop()
    if mode == "google":
        try:
            logged_in = bool(st.user.is_logged_in)
        except AttributeError:  # login not configured yet
            logged_in = False
        if not logged_in:
            brand.header("Impact & data", "HackYourFuture")
            st.write("This dashboard is for HackYourFuture colleagues. Log in with your HYF Google account.")
            if st.button("Log in with Google", type="primary"):
                try:
                    st.login()
                except Exception as exc:  # e.g. Google settings missing
                    st.error(f"Google login is not set up correctly: {exc}")
            st.stop()
        email = str(getattr(st.user, "email", "") or "").lower()
        domains = [x.strip().lower().lstrip("@") for x in os.getenv("ALLOWED_EMAIL_DOMAINS", "hackyourfuture.net").split(",") if x.strip()]
        emails = [x.strip().lower() for x in os.getenv("ALLOWED_EMAILS", "").split(",") if x.strip()]
        if not (email in emails or any(email.endswith("@" + dom) for dom in domains)):
            brand.header("Impact & data", "HackYourFuture")
            st.error(f"{email or 'This account'} doesn't have access. Log in with your HackYourFuture account.")
            st.button("Log out", on_click=st.logout)
            st.stop()
        with st.sidebar:
            st.caption(f"Logged in as {email}")
            st.button("Log out", on_click=st.logout)
        return
    st.error(f"Unknown AUTH_MODE '{mode}'. Use none, password or google.")
    st.stop()


def main() -> None:
    st.set_page_config(page_title="HYF Data Dashboard", page_icon=brand.page_icon(), layout="wide")
    brand.sidebar_logo()
    if APP_ENV == "prod" and auth_mode() == "none":
        st.error("This is the production app with real data, so it needs a login. Set APP_PASSWORD (or the Google login settings) "
                 "in the environment's variables and restart.")
        st.stop()
    require_login()
    brand.header("Impact & data", "HackYourFuture")
    if APP_ENV == "dev":
        st.caption("🧪 DEV environment · fictional data · for testing changes before they go to production")
    st.caption("The HYF Impact Dashboard, plus your own charts and questions to Claude. Your data stays on this computer.")
    if DEMO_MODE:
        st.warning("**Demo version with fictional data.** None of these numbers are real HackYourFuture results. Use it to see how the dashboard works, not to report figures.", icon="🧪")

    # Sidebar ---------------------------------------------------------------
    with st.sidebar:
        st.subheader("Data")
        st.write(f"Folder: `{DATA_DIR}`")
        tables: dict[str, pd.DataFrame] = {}
        if not DATA_DIR.exists():
            st.error("Data folder not found. Create it, mount it (Docker: ./data:/app/data) or set HYF_DATA_DIR.")
        else:
            try:
                tables = load_tables(str(DATA_DIR), _folder_signature(DATA_DIR))
            except Exception as exc:
                st.error(f"Could not read the data files: {exc}")
            if not tables:
                st.warning("No CSV or Excel files in the data folder yet. The tabs still work once you add them.")
        for name, df in tables.items():
            pii = [c for c in df.columns if is_pii(c)]
            st.write(f"• **{name}** — {len(df):,} rows" + (" 🔒" if pii else ""))
        if st.button("Reload data"):
            load_tables.clear()
            st.rerun()
        st.divider()
        st.subheader("Privacy")
        st.write(
            f"Sent to Claude (Ask tab only): column names & types"
            + (f", plus {SAMPLE_ROWS} example rows per table" if SAMPLE_ROWS else " only")
            + ". 🔒 personal columns are never sent."
        )
        st.divider()
        if not ENABLE_ASK:
            st.info("Ask Claude is switched off in this version.")
        elif get_client() is None:
            st.warning("No ANTHROPIC_API_KEY set. The Ask tab needs it; Build and Saved work without it.")
        else:
            st.success(f"Connected · {MODEL}")
        st.caption(f"App version {APP_VERSION}" + (f" · {APP_ENV.upper()}" if APP_ENV else ""))

    names = ["📊 Impact dashboard"] + (["💬 Ask Claude"] if ENABLE_ASK else []) + ["🛠 Build it yourself", "📌 Saved dashboards", "🗂 Data"]
    tabs = st.tabs(names)
    tab_impact, tab_build, tab_boards, tab_data = tabs[0], tabs[-3], tabs[-2], tabs[-1]
    tab_ask = tabs[1] if ENABLE_ASK else None

    # Impact dashboard (Measurement Dictionary v1.3) -----------------------
    with tab_impact:
        try:
            import impact

            impact.render(INDICATORS_FILE)
        except Exception as exc:  # keep the other tabs working
            st.error(f"The Impact dashboard could not load: {exc}")

    # Ask -------------------------------------------------------------------
    if tab_ask is not None:
        with tab_ask:
            if not tables:
                st.info("Add CSV or Excel files to the data folder to ask questions about them.")
            history: list[dict] = st.session_state.setdefault("history", [])

            st.write("Try one:")
            ex_cols = st.columns(len(EXAMPLE_QUESTIONS))
            clicked = None
            for col, q in zip(ex_cols, EXAMPLE_QUESTIONS):
                if col.button(q, width="stretch"):
                    clicked = q

            question = st.chat_input("Ask anything about HYF's data…") or clicked
            if question and not tables:
                st.error("There is no data to analyse yet.")
            elif question:
                if get_client() is None:
                    st.error("Add your ANTHROPIC_API_KEY to the .env file first.")
                else:
                    with st.spinner("Claude is building your dashboard…"):
                        try:
                            entry = generate_dashboard(question, tables, history)
                            entry["id"] = uuid.uuid4().hex[:8]
                            history.append(entry)
                        except Exception as exc:  # show, don't crash
                            st.error(str(exc))

            for entry in reversed(history):
                with st.container(border=True):
                    st.markdown(f"#### {entry['question']}")
                    if entry["summary"]:
                        st.caption(entry["summary"])
                    render_items(entry["items"], key=entry["id"], heading=entry["question"])
                    if entry["code"]:
                        save_controls(entry, key=entry["id"])
                        with st.expander("Show the code Claude wrote"):
                            st.code(entry["code"], language="python")

    # Build it yourself -----------------------------------------------------
    with tab_build:
        if tables:
            builder_tab(tables)
        else:
            st.info("Add CSV or Excel files to the data folder to build charts.")

    # Saved dashboards ------------------------------------------------------
    with tab_boards:
        saved = load_saved()
        if not saved:
            st.write("Nothing saved yet. Build charts in **🛠 Build it yourself** or ask a question and press **📌 Save**.")
        else:
            b1, b2 = st.columns([3, 1])
            board = b1.selectbox("Dashboard", list(saved.keys()), key="saved_board")
            with b2:
                download_board_button(board, tables, key="dl-saved")
            st.caption("Saved views re-run on the latest files in your data folder — no AI call, no cost. "
                       "Use ↑ ↓ to reorder and ✕ to remove.")
            render_board(board, tables, key_prefix="saved")

    # Data ------------------------------------------------------------------
    with tab_data:
        if not tables:
            st.info(f"No data files found in `{DATA_DIR}`.")
        else:
            name = st.selectbox("Table", list(tables.keys()))
            df = tables[name]
            st.write(f"{len(df):,} rows · {len(df.columns)} columns")
            st.dataframe(df.head(200), width="stretch", hide_index=True)


if __name__ == "__main__":
    main()
