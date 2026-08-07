"""Nurtec QoQ NBRx & TRx Waterfall -- Streamlit app.

Pick a Claim Type (NBRx/TRx), a previous quarter, and a current quarter.
The app queries the Nurtec LAAD waterfall metrics + NPA metrics from
Snowflake, decomposes the market-share change into WD / Rejections /
Reversals / Other reasons (with a payer-level breakdown), and renders
LAAD-level and NPA-scaled waterfall charts.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.data import (
    load_laad,
    npa_market_share_by_qtr,
    available_quarters,
    slice_metrics,
)
from src.waterfall import build_waterfall, rescale_to_npa, PAYERS, WaterfallResult
from src.charts import overall_waterfall, payer_breakdown_waterfall, qoq_metric_chart
from src.qc import build_qc, LeverQCTables


def excel_style_table(r: WaterfallResult, include_other: bool = True) -> pd.DataFrame:
    """Build the Excel-style waterfall table.

    Layout mirrors the workbook's TRx Waterfall / NBRx Waterfall tab.
    All contribution values are shown as percent (%);
    market share rows are shown as %.
    """
    rows = []
    rows.append(("Previous market share", r.previous_ms * 100, "%"))
    for name, lever in [
        ("Level 1 - WD", r.wd),
        ("Level 2 - Rejections", r.rj),
        ("Level 3 - Reversals", r.rv),
    ]:
        rows.append((name, lever.overall_impact * 100, "%"))
        for payer in PAYERS:
            rows.append((f"  {payer}", lever.payer_impacts_scaled.get(payer, 0.0) * 100, "%"))
    if include_other:
        rows.append(("Other reasons", r.other * 100, "%"))
    rows.append(("New market share", r.new_ms * 100, "%"))
    rows.append(("Total MS difference", r.total_delta * 100, "%"))

    df = pd.DataFrame(rows, columns=["Waterfall step", "Contribution", "Unit"])
    df["Contribution"] = df.apply(
        lambda x: f"{x['Contribution']:.2f}%",
        axis=1,
    )
    return df[["Waterfall step", "Contribution"]]

st.set_page_config(page_title="Nurtec Waterfall", page_icon="bar_chart", layout="wide")

# ---------------- PC HUB design language (CSS injection) ------------------
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Manrope:wght@600;700;800&display=swap');

:root{
  --navy-900:#0A1A3D; --navy-700:#163990; --navy-600:#1C4FC0;
  --accent:#41B6E6;
  --bg:#EEF3FB; --surface:#FFFFFF;
  --text:#0F172A; --text-muted:#64748B; --text-soft:#475569;
  --hairline:rgba(15,23,42,0.08);
  --hairline-2:rgba(15,23,42,0.06);
  --shadow-sm:0 2px 8px rgba(15,23,42,0.05),0 1px 2px rgba(15,23,42,0.04);
  --shadow-lg:0 18px 40px rgba(15,23,42,0.10),0 6px 12px rgba(15,23,42,0.06);
  --ease:cubic-bezier(0.4,0,0.2,1);
  --ease-out:cubic-bezier(0.16,1,0.3,1);
  --panel-radius:16px;
}

/* Page background: multi-layer radial + soft solid */
[data-testid="stAppViewContainer"]{
  background:
    radial-gradient(ellipse 80% 60% at 0% 0%,rgba(28,79,192,0.08) 0%,transparent 60%),
    radial-gradient(ellipse 70% 50% at 100% 0%,rgba(65,182,230,0.07) 0%,transparent 55%),
    radial-gradient(ellipse 60% 50% at 50% 100%,rgba(124,58,237,0.04) 0%,transparent 60%),
    var(--bg);
  font-family:'Inter',system-ui,sans-serif;
  color:var(--text);
  -webkit-font-smoothing:antialiased;
}
[data-testid="stAppViewContainer"] .main .block-container{ padding-top:1.4rem; padding-bottom:2rem; max-width:1400px; }
[data-testid="stHeader"]{ background:transparent; }

/* Both surfaces (sidebar + main) as separate rounded floating panels */
[data-testid="stSidebar"]{
  padding:1rem 0 1rem 1rem !important;
  background:transparent !important;
}
[data-testid="stSidebar"]>div:first-child{
  background:rgba(255,255,255,0.62) !important;
  backdrop-filter:saturate(180%) blur(22px);
  -webkit-backdrop-filter:saturate(180%) blur(22px);
  border:1px solid var(--hairline) !important;
  border-radius:var(--panel-radius) !important;
  box-shadow:var(--shadow-lg) !important;
  overflow-y:auto !important;
  max-height:calc(100vh - 2rem);
}
[data-testid="stMain"], .main{
  padding:1rem 1rem 1.2rem 1rem !important;
}
[data-testid="stMain"] .block-container,
.main .block-container{
  background:rgba(255,255,255,0.55) !important;
  backdrop-filter:saturate(180%) blur(14px);
  -webkit-backdrop-filter:saturate(180%) blur(14px);
  border:1px solid var(--hairline) !important;
  border-radius:var(--panel-radius) !important;
  box-shadow:var(--shadow-lg) !important;
  padding:1.6rem 1.8rem 2rem !important;
}

/* Typography */
h1,h2,h3,h4,
[data-testid="stMetricLabel"] p,
[data-testid="stMetricLabel"] label,
.stMarkdown h1,.stMarkdown h2,.stMarkdown h3{
  font-family:'Manrope','Inter',system-ui,sans-serif !important;
  font-weight:700;
  letter-spacing:-0.02em;
  color:var(--navy-900);
}
p, .stMarkdown p, [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p{
  font-family:'Inter',system-ui,sans-serif;
  color:var(--text-soft);
}
[data-testid="stCaptionContainer"]{ color:var(--text-muted); }

/* Hero header (custom HTML block) */
.hero{
  position:relative;
  background:
    radial-gradient(ellipse 90% 80% at 20% 20%,rgba(28,79,192,0.06) 0%,transparent 50%),
    radial-gradient(ellipse 60% 70% at 80% 80%,rgba(65,182,230,0.05) 0%,transparent 50%),
    linear-gradient(135deg,rgba(255,255,255,0.9) 0%,rgba(248,250,253,0.95) 100%);
  border-radius:16px;
  padding:1.6rem 1.8rem 1.4rem;
  border:1px solid var(--hairline-2);
  box-shadow:var(--shadow-sm);
  overflow:hidden;
  margin-bottom:1.4rem;
  animation:heroIn 0.5s var(--ease-out) both;
}
.hero::before{
  content:'';position:absolute;top:-1px;left:0;right:0;height:3px;
  background:linear-gradient(90deg,var(--navy-600),var(--accent),#3B6FD9);
  border-radius:16px 16px 0 0;opacity:0.75;
}
.hero-title{
  font-family:'Manrope',sans-serif;
  font-size:1.65rem;font-weight:800;
  color:var(--navy-900);
  letter-spacing:-0.025em;line-height:1.15;
  margin:0 0 0.35rem 0;
}
.hero-subtitle{
  display:flex;align-items:center;gap:0.55rem;
  color:var(--text-soft);font-size:0.85rem;font-weight:500;
}
.hero-subtitle .dot{ width:4px;height:4px;border-radius:50%;background:var(--text-muted);opacity:0.5; }
.hero-subtitle .chip{
  display:inline-flex;align-items:center;gap:6px;
  font-size:0.7rem;font-weight:600;
  color:var(--navy-700);
  background:rgba(28,79,192,0.08);
  padding:0.2rem 0.55rem;border-radius:6px;
  letter-spacing:0.03em;text-transform:uppercase;
}
@keyframes heroIn{ from{opacity:0;transform:translateY(6px);} to{opacity:1;transform:none;} }

/* Sidebar Inputs section styling */
[data-testid="stSidebar"] .block-container{ padding-top:1.6rem !important; }
[data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2,[data-testid="stSidebar"] h3{
  font-size:0.68rem !important;font-weight:700 !important;
  text-transform:uppercase;letter-spacing:0.14em;
  color:var(--text-muted) !important;
  margin-bottom:0.9rem !important;
  padding-bottom:0.55rem;
  border-bottom:1px solid var(--hairline);
}

/* Sidebar field labels (Claim type / Previous quarter / Current quarter) */
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p{
  font-family:'Manrope',sans-serif !important;
  font-size:0.68rem !important;font-weight:700 !important;
  text-transform:uppercase;letter-spacing:0.1em;
  color:var(--navy-700) !important;
  margin-bottom:0.35rem !important;
}

/* Sidebar selectboxes → glass field */
[data-testid="stSidebar"] [data-baseweb="select"]>div{
  background:rgba(255,255,255,0.9) !important;
  border:1px solid var(--hairline) !important;
  border-radius:10px !important;
  min-height:38px;
  font-family:'Inter',sans-serif !important;font-size:0.85rem !important;
  color:var(--navy-900) !important;
  transition:border-color 0.18s var(--ease),box-shadow 0.18s var(--ease);
  box-shadow:0 1px 2px rgba(15,23,42,0.03);
}
[data-testid="stSidebar"] [data-baseweb="select"]>div:hover{
  border-color:rgba(28,79,192,0.28) !important;
}
[data-testid="stSidebar"] [data-baseweb="select"]:focus-within>div{
  border-color:var(--navy-600) !important;
  box-shadow:0 0 0 3px rgba(28,79,192,0.12) !important;
}

/* Sidebar radio (horizontal Claim type) → mini pill row */
[data-testid="stSidebar"] [role="radiogroup"]{
  gap:0.5rem !important;
  background:rgba(255,255,255,0.6);
  border:1px solid var(--hairline);
  border-radius:999px;
  padding:0.25rem;
}
[data-testid="stSidebar"] [role="radiogroup"] label{
  flex:1 1 0;
  min-width:0;
  display:flex !important;align-items:center;justify-content:center;
  padding:0.4rem 0.7rem !important;
  border-radius:999px !important;
  font-family:'Manrope',sans-serif !important;
  font-size:0.78rem !important;font-weight:600 !important;
  color:var(--text-soft) !important;
  text-transform:none !important;letter-spacing:0 !important;
  white-space:nowrap;
  cursor:pointer;
  transition:all 0.18s var(--ease);
  margin:0 !important;
}
[data-testid="stSidebar"] [role="radiogroup"] label p,
[data-testid="stSidebar"] [role="radiogroup"] label span{
  white-space:nowrap !important;
  overflow:visible;
  line-height:1.1;
}
[data-testid="stSidebar"] [role="radiogroup"] label:hover{
  color:var(--navy-700) !important;
  background:rgba(28,79,192,0.06);
}
[data-testid="stSidebar"] [role="radiogroup"] label>div:first-child{ display:none !important; }
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked){
  background:linear-gradient(90deg,var(--navy-700),var(--accent)) !important;
  color:#fff !important;
  box-shadow:0 3px 10px rgba(22,57,144,0.25);
}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) *{ color:#fff !important; }

/* Sidebar Refresh button → accent gradient */
[data-testid="stSidebar"] .stButton>button{
  width:100% !important;
  background:linear-gradient(90deg,var(--navy-700),var(--accent)) !important;
  color:#fff !important;
  border:none !important;
  border-radius:10px !important;
  padding:0.55rem 1rem !important;
  font-family:'Manrope',sans-serif !important;
  font-size:0.8rem !important;font-weight:600 !important;
  letter-spacing:0.01em;
  box-shadow:0 4px 10px rgba(22,57,144,0.22) !important;
  transition:transform 0.18s var(--ease),box-shadow 0.25s var(--ease) !important;
}
[data-testid="stSidebar"] .stButton>button:hover{
  transform:translateY(-1px);
  box-shadow:0 8px 18px rgba(22,57,144,0.32) !important;
  color:#fff !important;
}

/* Sidebar warnings (e.g. "Pick two different quarters") */
[data-testid="stSidebar"] [data-testid="stAlert"]{
  background:rgba(255,200,50,0.10);
  border:1px solid rgba(200,150,0,0.20);
  border-radius:10px;
  font-size:0.78rem;
  color:var(--text-soft);
}

/* Tabs → PC HUB pill row */
.stTabs [data-baseweb="tab-list"]{
  gap:1.1rem;
  border-bottom:none !important;
  padding:0.4rem 0.2rem 0.6rem;margin-bottom:1rem;
  background:transparent !important;
}
.stTabs [data-baseweb="tab-border"]{ display:none !important; }
.stTabs [data-baseweb="tab"]{
  font-family:'Manrope',sans-serif;font-size:0.82rem;font-weight:600;
  padding:0.7rem 2.6rem !important;
  height:auto !important;
  min-width:0;
  border-radius:999px !important;
  background:rgba(255,255,255,0.95) !important;
  border:1px solid var(--hairline) !important;
  color:var(--text-soft) !important;
  transition:transform 0.22s var(--ease-out),box-shadow 0.22s var(--ease),background 0.18s var(--ease),color 0.18s var(--ease),border-color 0.18s var(--ease);
  box-shadow:0 2px 6px rgba(15,23,42,0.05),0 1px 2px rgba(15,23,42,0.04);
  white-space:nowrap;
}
.stTabs [data-baseweb="tab"] [data-testid="stMarkdownContainer"]{ padding:0 0.4rem !important; }
.stTabs [data-baseweb="tab"] p{ margin:0 !important; padding:0 0.25rem !important; }
.stTabs [data-baseweb="tab"]:hover{
  background:#fff !important;color:var(--navy-700) !important;
  border-color:rgba(28,79,192,0.28) !important;
  transform:translateY(-2px);
  box-shadow:0 10px 22px rgba(15,23,42,0.10),0 3px 6px rgba(15,23,42,0.05);
}
.stTabs [aria-selected="true"]{
  background:linear-gradient(90deg,var(--navy-700),var(--accent)) !important;
  color:#fff !important;
  border-color:transparent !important;
  border-radius:999px !important;
  transform:translateY(-2px);
  box-shadow:0 10px 24px rgba(22,57,144,0.35),0 3px 8px rgba(22,57,144,0.20) !important;
}
.stTabs [aria-selected="true"] *,
.stTabs [aria-selected="true"] p,
.stTabs [aria-selected="true"] span,
.stTabs [aria-selected="true"] [data-testid="stMarkdownContainer"],
.stTabs [aria-selected="true"] [data-testid="stMarkdownContainer"] *{
  color:#fff !important;
}
.stTabs [data-baseweb="tab-highlight"]{ display:none !important; height:0 !important; }
.stTabs [data-baseweb="tab-panel"]{ animation:sectionIn 0.28s var(--ease-out) both; }
@keyframes sectionIn{ from{opacity:0;transform:translateY(4px);} to{opacity:1;transform:none;} }

/* Expanders → glass card */
[data-testid="stExpander"]{
  background:rgba(255,255,255,0.75) !important;
  border:1px solid var(--hairline) !important;
  border-radius:14px !important;
  box-shadow:var(--shadow-sm);
  transition:transform 0.28s var(--ease-out),box-shadow 0.28s var(--ease),border-color 0.18s var(--ease);
  overflow:hidden;
  margin-bottom:0.7rem;
}
[data-testid="stExpander"]:hover{
  transform:translateY(-1px);
  box-shadow:var(--shadow-lg);
  border-color:rgba(28,79,192,0.18) !important;
}
[data-testid="stExpander"] summary{
  font-family:'Manrope',sans-serif;font-weight:600;
  color:var(--navy-900) !important;
  padding:0.7rem 1rem !important;
}
[data-testid="stExpander"] summary:hover{ color:var(--navy-700) !important; }
[data-testid="stExpander"] [data-testid="stExpanderDetails"]{
  animation:sectionIn 0.22s var(--ease-out) both;
}

/* Metrics → hero-kpi tiles */
[data-testid="stMetric"]{
  background:rgba(255,255,255,0.78);
  backdrop-filter:blur(8px);
  -webkit-backdrop-filter:blur(8px);
  border:1px solid var(--hairline-2);
  border-radius:12px;
  padding:0.95rem 1.15rem 0.9rem;
  box-shadow:var(--shadow-sm);
  min-height:118px;
  height:100%;
  display:flex;flex-direction:column;justify-content:center;
  transition:transform 0.25s var(--ease-out),box-shadow 0.25s var(--ease);
  overflow:hidden;
}
[data-testid="stMetric"]:hover{
  transform:translateY(-1px);
  box-shadow:var(--shadow-lg);
}
[data-testid="stMetricLabel"]{
  font-size:0.7rem !important;font-weight:600 !important;
  text-transform:uppercase;letter-spacing:0.06em;
  color:var(--text-muted) !important;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
}
[data-testid="stMetricValue"]{
  font-family:'Manrope',sans-serif !important;
  font-size:1.5rem !important;font-weight:700 !important;
  line-height:1.15 !important;
  color:var(--navy-900) !important;
  font-variant-numeric:tabular-nums;
  letter-spacing:-0.02em;
  white-space:nowrap;
}
[data-testid="stMetricValue"] > div{ white-space:nowrap !important; }
[data-testid="stMetricDelta"]{
  font-size:0.75rem !important;font-weight:600 !important;
  font-variant-numeric:tabular-nums;
  white-space:nowrap;
}

/* Non-collapsible sidebar — hide the collapse toggles */
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarCollapsedControl"],
[data-testid="stSidebarNav"] button[kind="header"]{
  display:none !important;
}
[data-testid="stSidebar"]{
  min-width:280px !important;
  max-width:340px !important;
  transform:none !important;
  visibility:visible !important;
}

/* Subheaders */
[data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3{
  font-size:1.02rem !important;font-weight:700;
  color:var(--navy-900) !important;
  margin-top:1.2rem !important;
  padding-top:0.4rem;
}

/* DataFrame → .ds-table look */
[data-testid="stDataFrame"]{
  border:1px solid var(--hairline);
  border-radius:10px;
  overflow:hidden;
  background:var(--surface);
  box-shadow:var(--shadow-sm);
}
[data-testid="stDataFrame"] [role="columnheader"]{
  background:rgba(28,79,192,0.05) !important;
  color:var(--navy-700) !important;
  font-family:'Manrope',sans-serif !important;
  font-weight:700 !important;
  text-transform:uppercase;letter-spacing:0.04em;font-size:0.68rem !important;
  border-bottom:1px solid var(--hairline) !important;
}
[data-testid="stDataFrame"] [role="row"]:hover [role="gridcell"]{
  background:rgba(28,79,192,0.025) !important;
}

/* Buttons */
.stButton>button, [data-testid="baseButton-secondary"]{
  background:rgba(255,255,255,0.75) !important;
  border:1px solid var(--hairline) !important;
  color:var(--text-soft) !important;
  border-radius:8px !important;
  font-family:'Inter',sans-serif !important;
  font-weight:500 !important;
  font-size:0.78rem !important;
  padding:0.4rem 0.85rem !important;
  transition:all 0.18s var(--ease) !important;
  box-shadow:none !important;
}
.stButton>button:hover, [data-testid="baseButton-secondary"]:hover{
  background:#fff !important;
  color:var(--navy-700) !important;
  border-color:rgba(28,79,192,0.28) !important;
  transform:translateY(-1px);
}
[data-testid="baseButton-primary"]{
  background:linear-gradient(90deg,var(--navy-700),var(--accent)) !important;
  color:#fff !important;
  border:none !important;
  box-shadow:0 2px 8px rgba(22,57,144,0.22) !important;
}

/* Radio / Selectbox in sidebar */
[data-testid="stSidebar"] [role="radiogroup"] label,
[data-testid="stSidebar"] .stRadio label{
  font-family:'Inter',sans-serif;font-weight:500;font-size:0.84rem;
  color:var(--text-soft);
}
[data-baseweb="select"]>div{
  background:rgba(255,255,255,0.85) !important;
  border:1px solid var(--hairline) !important;
  border-radius:8px !important;
  font-family:'Inter',sans-serif !important;
  transition:border-color 0.18s var(--ease);
}
[data-baseweb="select"]>div:hover{ border-color:rgba(28,79,192,0.28) !important; }

/* Info / warning banners */
[data-testid="stAlert"]{
  border-radius:10px;
  border:1px solid var(--hairline);
  background:rgba(255,255,255,0.72);
  font-family:'Inter',sans-serif;font-size:0.82rem;
  box-shadow:var(--shadow-sm);
}

/* Altair / Vega chart wrapper */
.vega-embed{ background:transparent !important; }
[data-testid="stVegaLiteChart"]{
  background:rgba(255,255,255,0.6);
  border:1px solid var(--hairline);
  border-radius:14px;
  padding:0.7rem 0.6rem 0.4rem;
  box-shadow:var(--shadow-sm);
  transition:transform 0.28s var(--ease-out),box-shadow 0.28s var(--ease);
}
[data-testid="stVegaLiteChart"]:hover{
  transform:translateY(-1px);
  box-shadow:var(--shadow-lg);
}

/* Scrollbars */
::-webkit-scrollbar{ width:8px;height:8px; }
::-webkit-scrollbar-thumb{ background:rgba(15,23,42,0.14);border-radius:3px; }
::-webkit-scrollbar-thumb:hover{ background:rgba(15,23,42,0.22); }
</style>
    """,
    unsafe_allow_html=True,
)

# ---------------- Hero header --------------------------------------------
st.markdown(
    """
<div class="hero">
  <div class="hero-title">Nurtec QoQ NBRx &amp; TRx Waterfall</div>
  <div class="hero-subtitle">
    <span class="chip">Objective</span>
    <span>Decomposes Nurtec's LAAD market-share change into Written Demand / Rejections / Reversals levers with payer-level breakdown, and rescales to NPA (real-world) market share.</span>
  </div>
</div>
    """,
    unsafe_allow_html=True,
)

# ---------------- Notes / Business Rules content -------------------------
HOW_TO_USE = (
    "This is a directional decomposition: we rebuild market share with one lever frozen "
    "at last quarter's level to isolate its effect, then repeat for each lever. "
    "The intent was to create something intuitive and actionable -- a clear read on which "
    "levers pushed share up or down and roughly by how much -- rather than a pure "
    "mathematical model that may be more precise but harder for stakeholders to interpret. "
    "Read it as a compass for where to focus, not as an exact accounting identity."
)

OTHER_REASONS = (
    "\"Other reasons\" is the overlap between the levers. Written demand, rejections and "
    "reversals move together rather than in isolation, so holding two steady while flexing "
    "one leaves a small shared effect that no single lever can claim. It stays small as "
    "long as the quarter-on-quarter swings are modest."
)

WHY_SCALING = (
    "Each lever's all-market impact is a blend across payer types, and the payer-level "
    "pieces don't sum to it on their own -- for two reasons. First, heterogeneous "
    "economics: payer types behave very differently (Commercial fills far more often than "
    "Other, for instance), so collapsing them into one blended rate matches none of them. "
    "Second, mix shift: the payer mix moves from quarter to quarter, and a single blended "
    "number implicitly assumes last quarter's mix. Together these create a payer-mix gap "
    "between the bottom-up (sum of payers) and top-down (all-market) views. The scaling "
    "factor redistributes that gap so the parts tie to the whole. One caveat: when the "
    "factor is large, more of the payer-level number is reconciliation than signal -- "
    "treat that breakdown as directional (which payer drove the move, and the rank order), "
    "not as a precise figure."
)


def _render_notes(expanded: bool = False):
    with st.expander("How to use this waterfall?", expanded=expanded):
        st.markdown(HOW_TO_USE)
    with st.expander("What is the \"Other reasons\" Category?", expanded=expanded):
        st.markdown(OTHER_REASONS)
    with st.expander("Why scaling?", expanded=expanded):
        st.markdown(WHY_SCALING)


# View state: "waterfall" (default) or "business_rules"
if "view" not in st.session_state:
    st.session_state["view"] = "waterfall"


# ---------------- Sidebar inputs -----------------------------------------
with st.sidebar:
    st.markdown(
        """
<div style="display:flex;justify-content:center;padding:0.4rem 0 1rem;">
  <img src="https://cdn.pfizer.com/pfizercom/2022-10/Pfizer_Logo_Color_CMYK.png"
       alt="Pfizer" style="max-width:140px;height:auto;display:block;" />
</div>
        """,
        unsafe_allow_html=True,
    )
    st.header("Inputs")

    claim_type = st.radio("Claim type", ["TRX", "NBRX"], horizontal=True)

    laad = load_laad()
    qtrs_laad = available_quarters(laad, claim_type)
    try:
        _npa_all = npa_market_share_by_qtr(claim_type)
        qtrs_npa = set(_npa_all["QTR"].tolist()) if not _npa_all.empty else set()
    except Exception:
        qtrs_npa = set()
    qtrs = sorted(set(qtrs_laad) & qtrs_npa) if qtrs_npa else sorted(qtrs_laad)
    if len(qtrs) < 2:
        st.error("Not enough quarters with both LAAD and NPA data.")
        st.stop()

    prev_qtr = st.selectbox("Previous quarter", qtrs, index=max(0, len(qtrs) - 3))
    # Current quarter must be strictly after Previous quarter
    _prev_idx = qtrs.index(prev_qtr)
    curr_options = qtrs[_prev_idx + 1:]
    if not curr_options:
        st.warning("Pick an earlier Previous quarter -- no later quarter available.")
        st.stop()
    curr_qtr = st.selectbox("Current quarter", curr_options, index=len(curr_options) - 1)

    st.markdown("<div style='margin-top:1rem'></div>", unsafe_allow_html=True)
    if st.button(
        "Business Rules & Assumptions",
        key="open_business_rules",
        use_container_width=True,
        help="Open the methodology notes in the main pane",
    ):
        st.session_state["view"] = "business_rules"
        st.rerun()
    if st.button(
        "Calculations",
        key="open_calculations",
        use_container_width=True,
        help="Open the QC / calculation walk-through in the main pane",
    ):
        st.session_state["view"] = "calculations"
        st.rerun()

# ---------------- Business Rules view (early return) ---------------------
if st.session_state.get("view") == "business_rules":
    if st.button("\u2190 Back to waterfall", key="back_to_waterfall"):
        st.session_state["view"] = "waterfall"
        st.rerun()
    st.markdown("## Business Rules &amp; Assumptions")
    st.caption(
        "How the waterfall is built, what \"Other reasons\" means, and why the payer-level "
        "impacts get scaled to match the all-market view."
    )
    _render_notes(expanded=True)
    st.stop()

# ---------------- Compute waterfall --------------------------------------
prev_metrics = slice_metrics(laad, prev_qtr, claim_type)
curr_metrics = slice_metrics(laad, curr_qtr, claim_type)
res = build_waterfall(prev_metrics, curr_metrics)

try:
    npa_df = npa_market_share_by_qtr(claim_type)
    npa_prev = npa_df.loc[npa_df["QTR"] == prev_qtr, "NPA_MS"]
    npa_curr = npa_df.loc[npa_df["QTR"] == curr_qtr, "NPA_MS"]
    npa_available = not (npa_prev.empty or npa_curr.empty)
except Exception as e:
    npa_df = pd.DataFrame()
    npa_available = False
    npa_error = str(e)
else:
    npa_error = None

npa_res = None
if npa_available:
    npa_res = rescale_to_npa(res, float(npa_prev.iloc[0]), float(npa_curr.iloc[0]))

# ---------------- Calculations view (early return) -----------------------
if st.session_state.get("view") == "calculations":
    if st.button("\u2190 Back to waterfall", key="back_to_waterfall_from_calc"):
        st.session_state["view"] = "waterfall"
        st.rerun()
    st.markdown("## Calculations")
    st.subheader(f"Calculation walk-through -- {claim_type}, {prev_qtr} \u2192 {curr_qtr}")
    st.caption(
        "Layout mirrors the workbook's TRx Waterfall / NBRx Waterfall tab (rows 36-130). "
        "Same formulas Excel uses, so you can cross-check any cell."
    )

    def _pct_cols(df: pd.DataFrame) -> list:
        return [c for c in df.columns if any(k in c for k in ("Mkt share", "Fill Rate", "RJ Rate", "RV Rate"))]

    def _int_cols(df: pd.DataFrame) -> list:
        return [c for c in df.columns
                if c in ("Oral CGRP WD", "Oral CGRP PD", "Oral CGRP PD Claims",
                         "OCGRP PD", "Nurtec WD",
                         "Nurtec Ideal PD", "Abbvie Ideal PD")]

    def _fmt_inputs(df: pd.DataFrame):
        fmt = {}
        for c in _pct_cols(df):
            fmt[c] = "{:.2%}"
        for c in _int_cols(df):
            fmt[c] = "{:,.0f}"
        if "Ideal Nurtec PD Mkt Share" in df.columns:
            fmt["Ideal Nurtec PD Mkt Share"] = "{:.2%}"
        return df.style.format(fmt, na_rep="\u2014")

    def _fmt_metrics(df: pd.DataFrame):
        def _cell(row, col):
            v = row[col]
            if v is None or pd.isna(v):
                return "\u2014"
            if row["Metric"] in ("Nurtec Ideal PD", "Nurtec Actual PD"):
                return f"{v:,.2f}"
            if row["Metric"] == "Volume Difference":
                return f"{v:+,.2f}"
            if row["Metric"] == "Market Share impact":
                return f"{v*100:+.2f}%"
            return str(v)
        out = df.copy()
        out["Actual (raw)"] = df.apply(lambda r: _cell(r, "Actual (raw)"), axis=1)
        out["Scaled up"] = df.apply(lambda r: _cell(r, "Scaled up"), axis=1)
        return out

    def render_lever(qc_l: LeverQCTables):
        st.markdown(f"### {qc_l.lever_name}")
        st.caption(qc_l.assumption)

        st.markdown("**Overall calculation**")
        st.dataframe(_fmt_inputs(qc_l.overall_inputs_df), use_container_width=True, hide_index=True)

        k1, k2, k3 = st.columns(3)
        k1.metric("Overall Impact", f"{qc_l.overall_impact*100:+.2f}%")
        k2.metric("Sum of payer raw impact", f"{qc_l.sum_payer_raw*100:+.2f}%")
        k3.metric("Scaling factor", f"{qc_l.scaling_factor:.2f}")

        st.markdown("**Payer-level detail**")
        for pt in qc_l.payer_tables:
            with st.expander(f"{pt.heading}", expanded=False):
                st.dataframe(_fmt_inputs(pt.inputs_df), use_container_width=True, hide_index=True)
                st.dataframe(_fmt_metrics(pt.metrics_df), use_container_width=True, hide_index=True)
                st.caption(
                    f"Difference/Impact -- Raw: {pt.impact_raw*100:+.4f}%   |   "
                    f"Scaled up: {pt.impact_scaled*100:+.4f}%"
                )
        st.markdown("---")

    qc = build_qc(prev_metrics, curr_metrics, res, prev_qtr, curr_qtr)
    render_lever(qc["L1"])
    render_lever(qc["L2"])
    render_lever(qc["L3"])
    st.stop()

# ---------------- Header KPIs --------------------------------------------
c1, c2 = st.columns(2)
c1.metric(f"Previous MS ({prev_qtr})", f"{res.previous_ms*100:.2f}%")
c2.metric(f"New MS ({curr_qtr})", f"{res.new_ms*100:.2f}%", f"{res.total_delta*100:+.2f}%")

# ---------------- Tabs ----------------------------------------------------
tab_npa, tab_laad, tab_payer, tab_qoq = st.tabs(
    ["NPA-scaled waterfall", "LAAD waterfall", "Payer level split", "QoQ Metrics"]
)

with tab_laad:
    st.altair_chart(
        overall_waterfall(res, f"{claim_type} LAAD waterfall -- {prev_qtr} to {curr_qtr}"),
        use_container_width=True,
    )

with tab_npa:
    if not npa_available:
        msg = f"No NPA rows for {prev_qtr} and/or {curr_qtr} in `{'/'.join(['FORECASTING_DATA_ECOSYSTEM','NURTEC_NPA_METRICS'])}`."
        if npa_error:
            msg += f"\n\nError: {npa_error}"
        st.warning(msg)
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric(f"NPA prev ({prev_qtr})", f"{npa_res.previous_ms*100:.2f}%")
        c2.metric(f"NPA curr ({curr_qtr})", f"{npa_res.new_ms*100:.2f}%", f"{npa_res.total_delta*100:+.2f}%")
        c3.metric("LAAD to NPA factor", f"{npa_res.debug['laad_to_npa_factor']:.2f}")

        st.altair_chart(
            overall_waterfall(npa_res, f"{claim_type} NPA-scaled waterfall -- {prev_qtr} to {curr_qtr}", include_other=False),
            use_container_width=True,
        )

with tab_payer:
    st.subheader(f"Payer-level split -- {claim_type}, {prev_qtr} \u2192 {curr_qtr}")
    st.caption(
        "Waterfall levels with per-payer contributions. Overall column matches the LAAD waterfall; "
        "payer columns are the scaled sub-impacts that sum (post-scaling) to the Overall value."
    )

    _payer_cols = list(PAYERS)  # Commercial, Medicaid, Medicare, Others
    _level_rows = [
        ("Level 1 - WD", res.wd),
        ("Level 2 - Rejections", res.rj),
        ("Level 3 - Reversals", res.rv),
    ]

    def _pct(x):
        return "" if x is None else f"{x*100:+.2f}%"

    def _pct_anchor(x):
        return "" if x is None else f"{x*100:.2f}%"

    table_rows = []
    # Previous market share (anchor)
    row = {"Waterfall step": "Previous market share"}
    for p in _payer_cols:
        row[p] = ""
    row["Overall"] = _pct_anchor(res.previous_ms)
    table_rows.append(row)

    # Lever rows: L1, L2, L3
    for name, lever in _level_rows:
        row = {"Waterfall step": name}
        for p in _payer_cols:
            row[p] = _pct(lever.payer_impacts_scaled.get(p, 0.0))
        row["Overall"] = _pct(lever.overall_impact)
        table_rows.append(row)

    # Other reasons (residual, anchor-style formatting with sign)
    row = {"Waterfall step": "Other reasons"}
    for p in _payer_cols:
        row[p] = ""
    row["Overall"] = _pct(res.other)
    table_rows.append(row)

    # New market share (anchor)
    row = {"Waterfall step": "New market share"}
    for p in _payer_cols:
        row[p] = ""
    row["Overall"] = _pct_anchor(res.new_ms)
    table_rows.append(row)

    df_payer_split = pd.DataFrame(table_rows, columns=["Waterfall step"] + _payer_cols + ["Overall"])
    st.dataframe(df_payer_split, use_container_width=True, hide_index=True)

    # Verification note: check that per-payer impacts sum to overall for each lever
    with st.expander("How the numbers relate", expanded=False):
        st.markdown(
            "- **Previous / New market share**: Nurtec's overall LAAD market share for that quarter.\n"
            "- **Level 1 / 2 / 3 overall**: what the market share would change by if only that lever moved.\n"
            "- **Payer columns**: each lever's overall impact split across payer types after payer-mix "
            "scaling. The four payer values for a level sum (approximately) to the level's Overall value.\n"
            "- **Other reasons**: residual = (New MS - Previous MS) - (L1 + L2 + L3). Small when levers "
            "move roughly independently."
        )

with tab_qoq:
    # Metric label -> raw METRIC value in the LAAD table
    _METRIC_OPTIONS = {
        "Written Demand (WD)": "WD",
        "Written Demand market share": "WD_MARKET_SHARE",
        "Paid claims (PD_CLAIMS)": "PD_CLAIMS",
        "Paid claims market share": "PD_MARKET_SHARE",
        "Fill rate": "FILL_RATE",
        "Rejection rate": "RJ_RATE",
        "Reversal rate": "RV_RATE",
    }
    available_metric_codes = set(laad["METRIC"].unique())
    metric_labels = [label for label, code in _METRIC_OPTIONS.items() if code in available_metric_codes]
    if not metric_labels:
        st.warning("No metrics available in the LAAD dataset.")
    else:
        col_a, col_b = st.columns([2, 1])
        with col_a:
            metric_label = st.selectbox(
                "Metric",
                metric_labels,
                key="qoq_metric",
                help="Pick a metric to track quarter-over-quarter across payers.",
            )
        brands_present = [b for b in ["Nurtec", "Abbvie", "Overall"] if b in set(laad["BRAND"].unique())]
        with col_b:
            brand = st.selectbox(
                "Brand",
                brands_present,
                index=0 if "Nurtec" not in brands_present else brands_present.index("Nurtec"),
                key="qoq_brand",
            )

        payer_options = [p for p in ["Overall", "Commercial", "Medicaid", "Medicare", "Others"]
                         if p in set(laad["PAYER"].unique())]
        default_payers = [p for p in payer_options if p != "Overall"] or payer_options
        selected_payers = st.multiselect(
            "Payers to plot",
            payer_options,
            default=default_payers,
            key="qoq_payers",
            help="Choose which payer lines appear on the chart.",
        )

        metric_code = _METRIC_OPTIONS[metric_label]
        if selected_payers:
            st.altair_chart(
                qoq_metric_chart(
                    laad,
                    metric=metric_code,
                    brand=brand,
                    claim_type=claim_type,
                    payers=selected_payers,
                    title=f"{brand} - {metric_label} - {claim_type} - quarter over quarter",
                ),
                use_container_width=True,
            )
        else:
            st.info("Select at least one payer to plot.")
