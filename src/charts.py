# Altair waterfall chart renderers for Nurtec QoQ market-share decomposition.
# Co-authored with CoCo
"""Altair waterfall renderers."""
from __future__ import annotations

import altair as alt
import pandas as pd

from .waterfall import WaterfallResult, PAYERS


# ---------------- PC HUB Altair theme -------------------------------------
_NAVY_900 = "#0A1A3D"
_NAVY_700 = "#163990"
_NAVY_600 = "#1C4FC0"
_ACCENT   = "#41B6E6"
_GAIN     = "#163990"
_LOSS     = "#E11D48"
_LEVEL    = "#41B6E6"
_MUTED    = "#475569"
_GRID     = "rgba(15,23,42,0.06)"

# Lever palette shared with the payer split table (streamlit_app.py mirrors these)
LEVER_COLORS = {
    "L1":     "#3B82F6",   # blue - Written Demand
    "L2":     "#22C55E",   # green - Rejections
    "L3":     "#F97316",   # orange - Reversals
    "anchor": "#94A3B8",   # slate - Previous / New market share
    "other":  "#94A3B8",   # slate - Other reasons
}


def _lever_color(label: str, measure: str) -> str:
    if measure in ("absolute", "total"):
        return LEVER_COLORS["anchor"]
    lower = label.lower()
    if "wd" in lower or "written" in lower or lower.startswith("level 1") or lower.startswith("l1"):
        return LEVER_COLORS["L1"]
    if "rejection" in lower or lower.startswith("level 2") or lower.startswith("l2"):
        return LEVER_COLORS["L2"]
    if "reversal" in lower or lower.startswith("level 3") or lower.startswith("l3"):
        return LEVER_COLORS["L3"]
    if "other" in lower:
        return LEVER_COLORS["other"]
    return _GAIN


def _pchub_theme() -> dict:
    return {
        "config": {
            "background": "transparent",
            "view": {"stroke": "transparent"},
            "font": "Inter, system-ui, sans-serif",
            "title": {
                "font": "Manrope, Inter, sans-serif",
                "fontWeight": 700,
                "fontSize": 14,
                "color": _NAVY_900,
                "anchor": "start",
                "offset": 12,
                "subtitleColor": _MUTED,
            },
            "axis": {
                "labelColor": _MUTED,
                "titleColor": _NAVY_900,
                "labelFont": "Inter",
                "titleFont": "Manrope",
                "titleFontWeight": 700,
                "titleFontSize": 11,
                "labelFontSize": 10,
                "grid": True,
                "gridColor": _GRID,
                "domainColor": "rgba(15,23,42,0.12)",
                "tickColor": "rgba(15,23,42,0.12)",
            },
            "legend": {
                "labelColor": _MUTED,
                "titleColor": _NAVY_900,
                "labelFont": "Inter",
                "titleFont": "Manrope",
                "labelFontSize": 10,
            },
            "bar": {"cornerRadius": 3},
            "range": {
                "category": [_NAVY_700, _ACCENT, "#7C3AED", _LOSS, "#F59E0B", "#10B981"],
            },
        }
    }


alt.themes.register("pchub", _pchub_theme)
alt.themes.enable("pchub")


def _split_label(label: str) -> tuple[str, str]:
    """Split a waterfall label into (prefix, suffix) so we can render it on
    two lines with different colors without breaking single words apart."""
    if " - " in label:
        head, tail = label.split(" - ", 1)
        return head, tail
    if " " in label:
        head, tail = label.split(" ", 1)
        return head, tail
    return label, ""


def _build_waterfall_df(labels: list, measures: list, values: list) -> pd.DataFrame:
    """Build a DataFrame with running totals for waterfall rendering."""
    rows = []
    running = 0.0
    for i, (label, measure, value) in enumerate(zip(labels, measures, values)):
        if measure == "absolute":
            start = 0.0
            end = value
            running = value
        elif measure == "total":
            start = 0.0
            end = value
            running = value
        else:
            start = running
            end = running + value
            running = end
        color = _lever_color(label, measure)
        text = (
            f"{value*100:.2f}%"
            if measure in ("absolute", "total")
            else f"{value*100:+.2f}%"
        )
        prefix, suffix = _split_label(label)
        rows.append({
            "label": label,
            "prefix": prefix,
            "suffix": suffix,
            "start": start,
            "end": end,
            "top": max(start, end),
            "color": color,
            "text": text,
            "order": i,
            "measure": measure,
        })
    return pd.DataFrame(rows)


def _zoomed_y_domain(df: pd.DataFrame, pad_frac: float = 0.4) -> list:
    """Compute a y-domain that ignores the trivial 0 start of anchor bars, so
    the mid-range lever bars are visible instead of being crushed by a full
    0-to-max scale. Adds a proportional padding on each side so bars aren't
    pressed against the axis edges.
    """
    anchor = df["measure"].isin(["absolute", "total"])
    pts = pd.concat([
        df.loc[~anchor, "start"],
        df.loc[~anchor, "end"],
        df.loc[anchor, "end"],
    ])
    lo, hi = float(pts.min()), float(pts.max())
    span = max(hi - lo, 1e-4)
    pad = span * pad_frac
    return [max(lo - pad, 0.0), hi + pad]


def overall_waterfall(res: WaterfallResult, title: str, include_other: bool = True) -> alt.Chart:
    labels = ["Previous MS", "Level 1 - WD", "Level 2 - Rejections", "Level 3 - Reversals"]
    measures = ["absolute", "relative", "relative", "relative"]
    values = [
        res.previous_ms,
        res.wd.overall_impact,
        res.rj.overall_impact,
        res.rv.overall_impact,
    ]
    if include_other:
        labels.append("Other reasons")
        measures.append("relative")
        values.append(res.other)
    labels.append("New MS")
    measures.append("total")
    values.append(res.new_ms)
    df = _build_waterfall_df(labels, measures, values)
    y_domain = _zoomed_y_domain(df)

    bars = alt.Chart(df).mark_bar(size=44, cornerRadius=4).encode(
        x=alt.X("label:N", sort=alt.EncodingSortField(field="order"), title=None,
                axis=alt.Axis(labels=False, ticks=True, domain=True, labelPadding=4)),
        y=alt.Y("start:Q", title="Market Share",
                axis=alt.Axis(format=".1%"),
                scale=alt.Scale(zero=False, domain=y_domain, nice=False, clamp=True)),
        y2="end:Q",
        color=alt.Color("color:N", scale=None),
        tooltip=[
            alt.Tooltip("label:N", title="Step"),
            alt.Tooltip("text:N", title="Value"),
        ],
    )
    text_layer = alt.Chart(df).mark_text(
        dy=-10, fontSize=11, font="Inter", fontWeight=500, color=_MUTED,
    ).encode(
        x=alt.X("label:N", sort=alt.EncodingSortField(field="order")),
        y=alt.Y("top:Q",
                scale=alt.Scale(zero=False, domain=y_domain, nice=False, clamp=True)),
        text="text:N",
    )
    # Two-line x-axis labels: prefix (dark navy, bold) on top, suffix (muted) below.
    prefix_layer = alt.Chart(df).mark_text(
        dy=16, fontSize=12, font="Manrope", fontWeight=700, color=_NAVY_900, baseline="top",
    ).encode(
        x=alt.X("label:N", sort=alt.EncodingSortField(field="order")),
        y=alt.datum(y_domain[0]),
        text="prefix:N",
    )
    suffix_layer = alt.Chart(df).mark_text(
        dy=32, fontSize=10.5, font="Inter", fontWeight=500, color=_MUTED, baseline="top",
    ).encode(
        x=alt.X("label:N", sort=alt.EncodingSortField(field="order")),
        y=alt.datum(y_domain[0]),
        text="suffix:N",
    )
    chart = (bars + text_layer + prefix_layer + suffix_layer).properties(
        title=title, height=480, width="container",
    )
    return chart


def payer_breakdown_waterfall(res: WaterfallResult, title: str) -> alt.Chart:
    labels = ["Previous MS"]
    measures = ["absolute"]
    values = [res.previous_ms]

    for name, lever in [("L1 WD", res.wd), ("L2 Rejections", res.rj), ("L3 Reversals", res.rv)]:
        for payer in PAYERS:
            labels.append(f"{name} - {payer}")
            measures.append("relative")
            values.append(lever.payer_impacts_scaled.get(payer, 0.0))
    labels += ["Other reasons", "New MS"]
    measures += ["relative", "total"]
    values += [res.other, res.new_ms]

    df = _build_waterfall_df(labels, measures, values)

    bars = alt.Chart(df).mark_bar(size=18, cornerRadius=2).encode(
        x=alt.X("label:N", sort=alt.EncodingSortField(field="order"), title=None,
                 axis=alt.Axis(labelAngle=-40)),
        y=alt.Y("start:Q", title="Market Share", axis=alt.Axis(format=".1%")),
        y2="end:Q",
        color=alt.Color("color:N", scale=None),
        tooltip=[
            alt.Tooltip("label:N", title="Step"),
            alt.Tooltip("text:N", title="Value"),
        ],
    )
    text_layer = alt.Chart(df).mark_text(
        dy=-8, fontSize=9, font="Inter", fontWeight=500, color=_NAVY_900,
    ).encode(
        x=alt.X("label:N", sort=alt.EncodingSortField(field="order")),
        y=alt.Y("end:Q"),
        text="text:N",
    )
    chart = (bars + text_layer).properties(title=title, height=500, width="container")
    return chart


# ---------------- QoQ metric time series ---------------------------------
_PCT_METRICS = {"WD_MARKET_SHARE", "PD_MARKET_SHARE", "FILL_RATE", "RJ_RATE", "RV_RATE"}
_PAYER_COLORS = {
    "Commercial": _NAVY_700,
    "Medicaid":   _ACCENT,
    "Medicare":   "#7C3AED",
    "Others":     "#F59E0B",
    "Overall":    _NAVY_900,
}


def qoq_metric_chart(
    df: pd.DataFrame,
    metric: str,
    brand: str,
    claim_type: str,
    payers: list | None = None,
    title: str | None = None,
) -> alt.Chart:
    """Quarter-over-quarter line chart of a single LAAD metric, one line per payer.

    df is the long-format LAAD DataFrame with QTR, CLAIM_TYPE, BRAND, PAYER, METRIC, VALUE.
    """
    sub = df[
        (df["CLAIM_TYPE"].str.upper() == claim_type.upper())
        & (df["BRAND"] == brand)
        & (df["METRIC"] == metric)
    ].copy()
    if payers:
        sub = sub[sub["PAYER"].isin(payers)]
    sub = sub.sort_values(["QTR", "PAYER"])

    is_pct = metric.upper() in _PCT_METRICS
    y_axis = alt.Axis(format=".1%" if is_pct else ",.0f", title=metric)
    y_scale = alt.Scale(zero=False, nice=True)
    tooltip_val = alt.Tooltip("VALUE:Q", title=metric, format=(".2%" if is_pct else ",.0f"))

    present_payers = list(sub["PAYER"].unique())
    palette = [_PAYER_COLORS.get(p, _NAVY_700) for p in present_payers]

    lines = alt.Chart(sub).mark_line(
        strokeWidth=2.4, interpolate="monotone",
    ).encode(
        x=alt.X("QTR:N", sort=None, title=None, axis=alt.Axis(labelAngle=-25)),
        y=alt.Y("VALUE:Q", axis=y_axis, scale=y_scale),
        color=alt.Color(
            "PAYER:N",
            scale=alt.Scale(domain=present_payers, range=palette),
            legend=alt.Legend(title="Payer", orient="top", direction="horizontal"),
        ),
        tooltip=[
            alt.Tooltip("QTR:N", title="Quarter"),
            alt.Tooltip("PAYER:N", title="Payer"),
            tooltip_val,
        ],
    )
    points = alt.Chart(sub).mark_point(
        size=70, filled=True, strokeWidth=0,
    ).encode(
        x=alt.X("QTR:N", sort=None),
        y=alt.Y("VALUE:Q", scale=y_scale),
        color=alt.Color("PAYER:N", scale=alt.Scale(domain=present_payers, range=palette), legend=None),
        tooltip=[
            alt.Tooltip("QTR:N", title="Quarter"),
            alt.Tooltip("PAYER:N", title="Payer"),
            tooltip_val,
        ],
    )
    chart = (lines + points).properties(
        title=title or f"{brand} - {metric} ({claim_type})",
        height=420,
        width="container",
    )
    return chart
