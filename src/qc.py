"""Excel-style QC / calculation tables for the Nurtec waterfall app.

Mirrors the intermediate tables in the workbook's `TRx Waterfall` /
`NBRx Waterfall` tabs (rows 36 - 130) so end users can audit each cell of
each lever computation against Excel.

All formulas are the SAME ones used in ``src/waterfall.py`` -- this module
just also exposes the intermediates and packages them into DataFrames
laid out the way Excel does.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import pandas as pd

from .waterfall import LeverBreakdown, WaterfallResult, PAYERS


PAYER_LABELS = [
    ("Commercial", "Level 1.1 - Commercial"),
    ("Medicaid",   "Level 1.2 - Medicaid"),
    ("Medicare",   "Level 1.3 - Medicare"),
    ("Others",     "Level 1.4 - Others"),
]


@dataclass
class PayerQCTable:
    payer: str
    heading: str
    inputs_df: pd.DataFrame
    metrics_df: pd.DataFrame
    impact_raw: float
    impact_scaled: float


@dataclass
class LeverQCTables:
    lever_name: str
    assumption: str
    overall_inputs_df: pd.DataFrame
    overall_impact: float
    sum_payer_raw: float
    scaling_factor: float
    payer_tables: List[PayerQCTable] = field(default_factory=list)


# ---------- helpers ------------------------------------------------------

def _g(metrics: dict, brand: str, payer: str, metric: str, default: float = 0.0) -> float:
    b = metrics.get(brand, {}) or {}
    p = b.get(payer)
    if p is None:
        return default
    v = p.get(metric)
    return float(v) if v is not None else default


def _metrics_df(rows_raw: dict, rows_scaled: dict) -> pd.DataFrame:
    """Build the "Metric / Actual / Scaled up" table used in payer sub-blocks."""
    metrics = ["Nurtec Ideal PD", "Nurtec Actual PD", "Volume Difference", "Market Share impact"]
    return pd.DataFrame(
        [(m, rows_raw[m], rows_scaled[m]) for m in metrics],
        columns=["Metric", "Actual (raw)", "Scaled up"],
    )


# ---------- Level 1 - Written Demand ------------------------------------

def l1_qc(prev: dict, curr: dict, wd: LeverBreakdown, prev_qtr: str, curr_qtr: str) -> LeverQCTables:
    cgrp_pd_curr = _g(curr, "Overall", "Overall", "PD_CLAIMS")
    cgrp_wd_curr = _g(curr, "Overall", "Overall", "WD")
    nu_wd_ms_prev = _g(prev, "Nurtec", "Overall", "WD_MARKET_SHARE")
    nu_fr_curr = _g(curr, "Nurtec", "Overall", "FILL_RATE")
    ideal_nurtec_pd_overall = cgrp_wd_curr * nu_wd_ms_prev * nu_fr_curr
    ideal_ms_overall = ideal_nurtec_pd_overall / cgrp_pd_curr if cgrp_pd_curr else 0.0

    overall_inputs_df = pd.DataFrame(
        [
            {
                "Time Period": prev_qtr,
                "Oral CGRP WD": _g(prev, "Overall", "Overall", "WD"),
                "Nurtec WD Mkt share": _g(prev, "Nurtec", "Overall", "WD_MARKET_SHARE"),
                "Nurtec PD Mkt share": _g(prev, "Nurtec", "Overall", "PD_MARKET_SHARE"),
                "Nurtec Fill Rate": _g(prev, "Nurtec", "Overall", "FILL_RATE"),
                "Oral CGRP PD Claims": _g(prev, "Overall", "Overall", "PD_CLAIMS"),
                "Ideal Nurtec PD Mkt Share": None,
            },
            {
                "Time Period": curr_qtr,
                "Oral CGRP WD": cgrp_wd_curr,
                "Nurtec WD Mkt share": _g(curr, "Nurtec", "Overall", "WD_MARKET_SHARE"),
                "Nurtec PD Mkt share": _g(curr, "Nurtec", "Overall", "PD_MARKET_SHARE"),
                "Nurtec Fill Rate": nu_fr_curr,
                "Oral CGRP PD Claims": cgrp_pd_curr,
                "Ideal Nurtec PD Mkt Share": ideal_ms_overall,
            },
        ]
    )

    sum_raw = sum(wd.payer_impacts_raw.values())
    factor = wd.scaling_factor

    payer_tables: List[PayerQCTable] = []
    for payer, heading in PAYER_LABELS:
        cgrp_wd_p = _g(curr, "Overall", payer, "WD")
        cgrp_pd_p = _g(curr, "Overall", payer, "PD_CLAIMS")
        nu_wd_ms_prev_p = _g(prev, "Nurtec", payer, "WD_MARKET_SHARE")
        nu_fr_p = _g(curr, "Nurtec", payer, "FILL_RATE")
        ideal_pd_p = cgrp_wd_p * nu_wd_ms_prev_p * nu_fr_p
        actual_pd_p = _g(curr, "Nurtec", payer, "PD_CLAIMS")
        vol_diff_raw = actual_pd_p - ideal_pd_p
        vol_diff_scaled = vol_diff_raw * factor
        ms_impact_raw = wd.payer_impacts_raw.get(payer, 0.0)
        ms_impact_scaled = wd.payer_impacts_scaled.get(payer, 0.0)

        inputs_df = pd.DataFrame(
            [
                {
                    "Time Period": prev_qtr,
                    "Oral CGRP WD": _g(prev, "Overall", payer, "WD"),
                    "Oral CGRP PD": _g(prev, "Overall", payer, "PD_CLAIMS"),
                    "Nurtec WD Mkt share": _g(prev, "Nurtec", payer, "WD_MARKET_SHARE"),
                    "Nurtec PD Mkt share": _g(prev, "Nurtec", payer, "PD_MARKET_SHARE"),
                    "Nurtec Fill Rate": _g(prev, "Nurtec", payer, "FILL_RATE"),
                },
                {
                    "Time Period": curr_qtr,
                    "Oral CGRP WD": cgrp_wd_p,
                    "Oral CGRP PD": cgrp_pd_p,
                    "Nurtec WD Mkt share": _g(curr, "Nurtec", payer, "WD_MARKET_SHARE"),
                    "Nurtec PD Mkt share": _g(curr, "Nurtec", payer, "PD_MARKET_SHARE"),
                    "Nurtec Fill Rate": nu_fr_p,
                },
            ]
        )
        metrics_df = _metrics_df(
            rows_raw={
                "Nurtec Ideal PD": ideal_pd_p,
                "Nurtec Actual PD": actual_pd_p,
                "Volume Difference": vol_diff_raw,
                "Market Share impact": ms_impact_raw,
            },
            rows_scaled={
                "Nurtec Ideal PD": None,
                "Nurtec Actual PD": None,
                "Volume Difference": vol_diff_scaled,
                "Market Share impact": ms_impact_scaled,
            },
        )
        payer_tables.append(
            PayerQCTable(
                payer=payer,
                heading=heading.replace("Level 1.", "Level 1."),
                inputs_df=inputs_df,
                metrics_df=metrics_df,
                impact_raw=ms_impact_raw,
                impact_scaled=ms_impact_scaled,
            )
        )

    return LeverQCTables(
        lever_name="Level 1 - Written Demand",
        assumption=(
            "Assumption: an ideal scenario where the Written Demand market share "
            "is held constant at the previous quarter's level, while RJ and RV "
            "dynamics remain at the current quarter."
        ),
        overall_inputs_df=overall_inputs_df,
        overall_impact=wd.overall_impact,
        sum_payer_raw=sum_raw,
        scaling_factor=factor,
        payer_tables=payer_tables,
    )


# ---------- Level 2 / Level 3 (Rejections / Reversals) -------------------

def _l23_qc(
    prev: dict,
    curr: dict,
    lever: LeverBreakdown,
    prev_qtr: str,
    curr_qtr: str,
    *,
    lever_name: str,
    assumption: str,
    hold_metric: str,
    other_metric: str,
    payer_heading_prefix: str,
) -> LeverQCTables:
    """Shared implementation for L2 (hold RJ at prev) and L3 (hold RV at prev).

    ``hold_metric`` is the rate held at prev (`RJ_RATE` for L2, `RV_RATE` for L3).
    ``other_metric`` is the rate at curr (`RV_RATE` for L2, `RJ_RATE` for L3).
    """
    # --- Overall table --------------------------------------------------
    cgrp_pd_curr = _g(curr, "Overall", "Overall", "PD_CLAIMS")
    nu_wd = _g(curr, "Nurtec", "Overall", "WD")
    ab_wd = _g(curr, "Abbvie", "Overall", "WD")
    nu_ideal_fr = 1.0 - (_g(prev, "Nurtec", "Overall", hold_metric) + _g(curr, "Nurtec", "Overall", other_metric))
    ab_ideal_fr = 1.0 - (_g(prev, "Abbvie", "Overall", hold_metric) + _g(curr, "Abbvie", "Overall", other_metric))
    nu_ideal_pd = nu_wd * nu_ideal_fr
    ab_ideal_pd = ab_wd * ab_ideal_fr
    ideal_ms_overall = nu_ideal_pd / (nu_ideal_pd + ab_ideal_pd) if (nu_ideal_pd + ab_ideal_pd) else 0.0

    overall_inputs_df = pd.DataFrame(
        [
            {
                "Time Period": prev_qtr,
                "Oral CGRP WD": _g(prev, "Overall", "Overall", "WD"),
                "Oral CGRP PD": _g(prev, "Overall", "Overall", "PD_CLAIMS"),
                "Nurtec WD": _g(prev, "Nurtec", "Overall", "WD"),
                "Nurtec PD Mkt share": _g(prev, "Nurtec", "Overall", "PD_MARKET_SHARE"),
                "Nurtec Fill Rate": _g(prev, "Nurtec", "Overall", "FILL_RATE"),
                "Nurtec RJ Rate": _g(prev, "Nurtec", "Overall", "RJ_RATE"),
                "Nurtec RV Rate": _g(prev, "Nurtec", "Overall", "RV_RATE"),
                "Abbvie RJ Rate": _g(prev, "Abbvie", "Overall", "RJ_RATE"),
                "Abbvie RV Rate": _g(prev, "Abbvie", "Overall", "RV_RATE"),
                "Nurtec Ideal Fill Rate": None,
                "Abbvie Ideal Fill Rate": None,
                "Nurtec Ideal PD": None,
                "Abbvie Ideal PD": None,
                "Ideal Nurtec PD Mkt Share": None,
            },
            {
                "Time Period": curr_qtr,
                "Oral CGRP WD": _g(curr, "Overall", "Overall", "WD"),
                "Oral CGRP PD": cgrp_pd_curr,
                "Nurtec WD": nu_wd,
                "Nurtec PD Mkt share": _g(curr, "Nurtec", "Overall", "PD_MARKET_SHARE"),
                "Nurtec Fill Rate": _g(curr, "Nurtec", "Overall", "FILL_RATE"),
                "Nurtec RJ Rate": _g(curr, "Nurtec", "Overall", "RJ_RATE"),
                "Nurtec RV Rate": _g(curr, "Nurtec", "Overall", "RV_RATE"),
                "Abbvie RJ Rate": _g(curr, "Abbvie", "Overall", "RJ_RATE"),
                "Abbvie RV Rate": _g(curr, "Abbvie", "Overall", "RV_RATE"),
                "Nurtec Ideal Fill Rate": nu_ideal_fr,
                "Abbvie Ideal Fill Rate": ab_ideal_fr,
                "Nurtec Ideal PD": nu_ideal_pd,
                "Abbvie Ideal PD": ab_ideal_pd,
                "Ideal Nurtec PD Mkt Share": ideal_ms_overall,
            },
        ]
    )

    sum_raw = sum(lever.payer_impacts_raw.values())
    factor = lever.scaling_factor
    ocgrp_pd_overall = cgrp_pd_curr

    payer_tables: List[PayerQCTable] = []
    for payer, heading in PAYER_LABELS:
        heading = heading.replace("Level 1.", f"{payer_heading_prefix}.")
        nu_wd_p = _g(curr, "Nurtec", payer, "WD")
        ab_wd_p = _g(curr, "Abbvie", payer, "WD")
        ocgrp_pd_p = _g(curr, "Overall", payer, "PD_CLAIMS")

        nu_ideal_fr_p = 1.0 - (_g(prev, "Nurtec", payer, hold_metric) + _g(curr, "Nurtec", payer, other_metric))
        ab_ideal_fr_p = 1.0 - (_g(prev, "Abbvie", payer, hold_metric) + _g(curr, "Abbvie", payer, other_metric))
        nu_ideal_pd_p = nu_wd_p * nu_ideal_fr_p
        ab_ideal_pd_p = ab_wd_p * ab_ideal_fr_p
        denom = nu_ideal_pd_p + ab_ideal_pd_p
        ideal_ms_p = nu_ideal_pd_p / denom if denom else 0.0
        ideal_pd_at_ocgrp = ideal_ms_p * ocgrp_pd_p
        actual_pd_computed = _g(curr, "Nurtec", payer, "FILL_RATE") * nu_wd_p

        vol_diff_raw = actual_pd_computed - ideal_pd_at_ocgrp
        vol_diff_scaled = vol_diff_raw * factor
        ms_impact_raw = lever.payer_impacts_raw.get(payer, 0.0)
        ms_impact_scaled = lever.payer_impacts_scaled.get(payer, 0.0)

        inputs_df = pd.DataFrame(
            [
                {
                    "Time Period": prev_qtr,
                    "Oral CGRP WD": _g(prev, "Overall", payer, "WD"),
                    "OCGRP PD": _g(prev, "Overall", payer, "PD_CLAIMS"),
                    "Nurtec WD": _g(prev, "Nurtec", payer, "WD"),
                    "Nurtec PD Mkt share": _g(prev, "Nurtec", payer, "PD_MARKET_SHARE"),
                    "Nurtec Fill Rate": _g(prev, "Nurtec", payer, "FILL_RATE"),
                    "Nurtec RJ Rate": _g(prev, "Nurtec", payer, "RJ_RATE"),
                    "Nurtec RV Rate": _g(prev, "Nurtec", payer, "RV_RATE"),
                    "Abbvie Fill Rate": _g(prev, "Abbvie", payer, "FILL_RATE"),
                    "Abbvie RJ Rate": _g(prev, "Abbvie", payer, "RJ_RATE"),
                    "Abbvie RV Rate": _g(prev, "Abbvie", payer, "RV_RATE"),
                    "Nurtec Ideal Fill Rate": None,
                    "Abbvie Ideal Fill Rate": None,
                },
                {
                    "Time Period": curr_qtr,
                    "Oral CGRP WD": _g(curr, "Overall", payer, "WD"),
                    "OCGRP PD": ocgrp_pd_p,
                    "Nurtec WD": nu_wd_p,
                    "Nurtec PD Mkt share": _g(curr, "Nurtec", payer, "PD_MARKET_SHARE"),
                    "Nurtec Fill Rate": _g(curr, "Nurtec", payer, "FILL_RATE"),
                    "Nurtec RJ Rate": _g(curr, "Nurtec", payer, "RJ_RATE"),
                    "Nurtec RV Rate": _g(curr, "Nurtec", payer, "RV_RATE"),
                    "Abbvie Fill Rate": _g(curr, "Abbvie", payer, "FILL_RATE"),
                    "Abbvie RJ Rate": _g(curr, "Abbvie", payer, "RJ_RATE"),
                    "Abbvie RV Rate": _g(curr, "Abbvie", payer, "RV_RATE"),
                    "Nurtec Ideal Fill Rate": nu_ideal_fr_p,
                    "Abbvie Ideal Fill Rate": ab_ideal_fr_p,
                },
            ]
        )

        metrics_df = _metrics_df(
            rows_raw={
                "Nurtec Ideal PD": ideal_pd_at_ocgrp,
                "Nurtec Actual PD": actual_pd_computed,
                "Volume Difference": vol_diff_raw,
                "Market Share impact": ms_impact_raw,
            },
            rows_scaled={
                "Nurtec Ideal PD": None,
                "Nurtec Actual PD": None,
                "Volume Difference": vol_diff_scaled,
                "Market Share impact": ms_impact_scaled,
            },
        )
        payer_tables.append(
            PayerQCTable(
                payer=payer,
                heading=heading,
                inputs_df=inputs_df,
                metrics_df=metrics_df,
                impact_raw=ms_impact_raw,
                impact_scaled=ms_impact_scaled,
            )
        )

    return LeverQCTables(
        lever_name=lever_name,
        assumption=assumption,
        overall_inputs_df=overall_inputs_df,
        overall_impact=lever.overall_impact,
        sum_payer_raw=sum_raw,
        scaling_factor=factor,
        payer_tables=payer_tables,
    )


def l2_qc(prev: dict, curr: dict, rj: LeverBreakdown, prev_qtr: str, curr_qtr: str) -> LeverQCTables:
    return _l23_qc(
        prev, curr, rj, prev_qtr, curr_qtr,
        lever_name="Level 2 - Rejections",
        assumption=(
            "Assumption: an ideal scenario where Written Demand market share and "
            "RV dynamics remain current, but RJ dynamics for both Pfizer (Nurtec) "
            "and Abbvie are held constant at the previous quarter's level."
        ),
        hold_metric="RJ_RATE",
        other_metric="RV_RATE",
        payer_heading_prefix="Level 2",
    )


def l3_qc(prev: dict, curr: dict, rv: LeverBreakdown, prev_qtr: str, curr_qtr: str) -> LeverQCTables:
    return _l23_qc(
        prev, curr, rv, prev_qtr, curr_qtr,
        lever_name="Level 3 - Reversals",
        assumption=(
            "Assumption: an ideal scenario where Written Demand market share and "
            "RJ dynamics remain current, but RV dynamics for both Pfizer (Nurtec) "
            "and Abbvie are held constant at the previous quarter's level."
        ),
        hold_metric="RV_RATE",
        other_metric="RJ_RATE",
        payer_heading_prefix="Level 3",
    )


def build_qc(prev: dict, curr: dict, res: WaterfallResult, prev_qtr: str, curr_qtr: str) -> Dict[str, LeverQCTables]:
    return {
        "L1": l1_qc(prev, curr, res.wd, prev_qtr, curr_qtr),
        "L2": l2_qc(prev, curr, res.rj, prev_qtr, curr_qtr),
        "L3": l3_qc(prev, curr, res.rv, prev_qtr, curr_qtr),
    }
