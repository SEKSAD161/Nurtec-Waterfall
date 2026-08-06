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
        color = (
            _LEVEL if measure in ("absolute", "total")
            else _GAIN if value >= 0
            else _LOSS
        )
        text = (
            f"{value*100:.2f}%"
            if measure in ("absolute", "total")
            else f"{value*100:+.2f}%"
        )
        rows.append({
            "label": label,
            "start": start,
            "end": end,
            "color": color,
            "text": text,
            "order": i,
            "measure": measure,
        })
    return pd.DataFrame(rows)


def _zoomed_y_domain(df: pd.DataFrame, pad_frac: float = 0.15) -> list:
    """Compute a y-domain that ignores the trivial 0 start of anchor bars, so
    the mid-range lever bars are visible instead of being crushed by a full
    0-to-max scale. Adds a small proportional padding on each side.
    """
    anchor = df["measure"].isin(["absolute", "total"])
    # Points we actually care about visually:
    pts = pd.concat([
        df.loc[~anchor, "start"],
        df.loc[~anchor, "end"],
        df.loc[anchor, "end"],
    ])
    lo, hi = float(pts.min()), float(pts.max())
    span = max(hi - lo, 1e-4)
    pad = span * pad_frac
    return [max(lo - pad, 0.0), hi + pad]


def overall_waterfall(res: WaterfallResult, title: str) -> alt.Chart:
    labels = ["Previous MS", "Level 1 - WD", "Level 2 - Rejections", "Level 3 - Reversals", "Other reasons", "New MS"]
    measures = ["absolute", "relative", "relative", "relative", "relative", "total"]
    values = [
        res.previous_ms,
        res.wd.overall_impact,
        res.rj.overall_impact,
        res.rv.overall_impact,
        res.other,
        res.new_ms,
    ]
    df = _build_waterfall_df(labels, measures, values)
    y_domain = _zoomed_y_domain(df)

    bars = alt.Chart(df).mark_bar(size=44, cornerRadius=4).encode(
        x=alt.X("label:N", sort=alt.EncodingSortField(field="order"), title=None,
                axis=alt.Axis(labelAngle=-25, labelLimit=200)),
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
        dy=-10, fontSize=11, font="Inter", fontWeight=600, color=_NAVY_900,
    ).encode(
        x=alt.X("label:N", sort=alt.EncodingSortField(field="order")),
        y=alt.Y("end:Q",
                scale=alt.Scale(zero=False, domain=y_domain, nice=False, clamp=True)),
        text="text:N",
    )
    chart = (bars + text_layer).properties(title=title, height=440, width="container")
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
