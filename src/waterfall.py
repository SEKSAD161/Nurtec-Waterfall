"""Waterfall decomposition math.

Mirrors the QoQ NBRx & TRx Waterfall Excel workbook:

  Previous MS -> Level 1 (WD) -> Level 2 (Rejections) -> Level 3 (Reversals)
              -> Other reasons (residual) -> New MS

Each lever holds one driver constant at the previous quarter and keeps
everything else at the current quarter. Payer-level sub-impacts are then
scaled so they sum to the overall lever impact (the workbook's factor step).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

PAYERS = ["Commercial", "Medicaid", "Medicare", "Others"]
_PAYER_ALIASES = {"Other": "Others", "Others": "Others"}


def _payer_key(name: str) -> str:
    return _PAYER_ALIASES.get(name, name)


def _get(metrics: dict, brand: str, payer: str, metric: str, default: float = 0.0) -> float:
    b = metrics.get(brand, {})
    p = b.get(payer)
    if p is None:
        for alt, canon in _PAYER_ALIASES.items():
            if canon == payer and alt in b:
                p = b[alt]
                break
    if p is None:
        return default
    v = p.get(metric)
    return float(v) if v is not None else default


@dataclass
class LeverBreakdown:
    overall_impact: float
    payer_impacts_raw: Dict[str, float]
    payer_impacts_scaled: Dict[str, float]
    scaling_factor: float


@dataclass
class WaterfallResult:
    previous_ms: float
    new_ms: float
    total_delta: float
    wd: LeverBreakdown
    rj: LeverBreakdown
    rv: LeverBreakdown
    other: float
    debug: dict = field(default_factory=dict)


def _ideal_fr_linear(fr_curr: float, rate_curr: float, rate_prev: float) -> float:
    """Ideal fill rate under 'lever held at previous' -- linear model matching the workbook.

    ideal_FR = FR_curr + (rate_curr - rate_prev).
    If the current rate is worse (higher) than the previous rate, ideal FR increases.
    """
    return fr_curr + (rate_curr - rate_prev)


# ---------- Level 1: Written Demand -------------------------------------
# Impact convention (matches Excel): impact = actual_MS - ideal_MS.
#   ideal_MS = what Nurtec's MS would have been if THIS lever were still at prev quarter.
#   If the lever helped Nurtec, ideal < actual => impact > 0.

def _overall_impact_wd(prev: dict, curr: dict) -> float:
    cgrp_pd_curr = _get(curr, "Overall", "Overall", "PD_CLAIMS")
    if cgrp_pd_curr == 0:
        return 0.0
    cgrp_wd_curr = _get(curr, "Overall", "Overall", "WD")
    nurtec_wd_ms_prev = _get(prev, "Nurtec", "Overall", "WD_MARKET_SHARE")
    nurtec_fr_curr = _get(curr, "Nurtec", "Overall", "FILL_RATE")
    ideal_nurtec_pd = cgrp_wd_curr * nurtec_wd_ms_prev * nurtec_fr_curr
    ideal_ms = ideal_nurtec_pd / cgrp_pd_curr
    actual_ms = _get(curr, "Nurtec", "Overall", "PD_MARKET_SHARE")
    return actual_ms - ideal_ms


def _payer_impact_wd(prev: dict, curr: dict, payer: str) -> float:
    pkey = _payer_key(payer)
    cgrp_wd_curr = _get(curr, "Overall", pkey, "WD")
    cgrp_pd_curr = _get(curr, "Overall", "Overall", "PD_CLAIMS")
    if cgrp_pd_curr == 0:
        return 0.0
    nurtec_wd_ms_prev = _get(prev, "Nurtec", pkey, "WD_MARKET_SHARE")
    nurtec_fr_curr = _get(curr, "Nurtec", pkey, "FILL_RATE")
    ideal_nurtec_pd = cgrp_wd_curr * nurtec_wd_ms_prev * nurtec_fr_curr
    actual_nurtec_pd = _get(curr, "Nurtec", pkey, "PD_CLAIMS")
    return (actual_nurtec_pd - ideal_nurtec_pd) / cgrp_pd_curr


# ---------- Level 2: Rejections -----------------------------------------

def _overall_impact_rj(prev: dict, curr: dict) -> float:
    cgrp_pd_curr = _get(curr, "Overall", "Overall", "PD_CLAIMS")
    if cgrp_pd_curr == 0:
        return 0.0
    nurtec_ideal_fr = _ideal_fr_linear(
        _get(curr, "Nurtec", "Overall", "FILL_RATE"),
        _get(curr, "Nurtec", "Overall", "RJ_RATE"),
        _get(prev, "Nurtec", "Overall", "RJ_RATE"),
    )
    abbvie_ideal_fr = _ideal_fr_linear(
        _get(curr, "Abbvie", "Overall", "FILL_RATE"),
        _get(curr, "Abbvie", "Overall", "RJ_RATE"),
        _get(prev, "Abbvie", "Overall", "RJ_RATE"),
    )
    nurtec_wd = _get(curr, "Nurtec", "Overall", "WD")
    abbvie_wd = _get(curr, "Abbvie", "Overall", "WD")
    ideal_nurtec_pd = nurtec_wd * nurtec_ideal_fr
    ideal_abbvie_pd = abbvie_wd * abbvie_ideal_fr
    # Excel row 93: P93 = N93 / SUM(N93:O93) -- Nurtec + Abbvie only, no "Others".
    ideal_market_pd = ideal_nurtec_pd + ideal_abbvie_pd
    ideal_ms = ideal_nurtec_pd / ideal_market_pd if ideal_market_pd else 0.0
    actual_ms = _get(curr, "Nurtec", "Overall", "PD_MARKET_SHARE")
    return actual_ms - ideal_ms


def _payer_impact_rj(prev: dict, curr: dict, payer: str) -> float:
    """Payer-level RJ impact -- matches the workbook's TRx Waterfall rows 100-103.

    Excel's formula:
        ideal_FR      = 1 - (RJ_prev + RV_curr)           per brand, per payer
        ideal_PD_p    = ideal_FR x WD_curr                per brand, per payer
        ideal_MS_p    = Nurtec_ideal_PD / (Nurtec_ideal_PD + Abbvie_ideal_PD)
        ideal_at_ocgrp = ideal_MS_p x OCGRP_PD_payer_curr
        actual_pd_computed = Nurtec_FR_curr x Nurtec_WD_curr   (per payer)
        raw_impact    = (actual_pd_computed - ideal_at_ocgrp) / OCGRP_PD_OVERALL_curr
    """
    pkey = _payer_key(payer)
    ocgrp_pd_overall = _get(curr, "Overall", "Overall", "PD_CLAIMS")
    ocgrp_pd_p = _get(curr, "Overall", pkey, "PD_CLAIMS")
    if ocgrp_pd_overall == 0:
        return 0.0

    nurtec_wd = _get(curr, "Nurtec", pkey, "WD")
    abbvie_wd = _get(curr, "Abbvie", pkey, "WD")

    nu_ideal_fr = 1.0 - (
        _get(prev, "Nurtec", pkey, "RJ_RATE") + _get(curr, "Nurtec", pkey, "RV_RATE")
    )
    ab_ideal_fr = 1.0 - (
        _get(prev, "Abbvie", pkey, "RJ_RATE") + _get(curr, "Abbvie", pkey, "RV_RATE")
    )

    nu_ideal_pd = nurtec_wd * nu_ideal_fr
    ab_ideal_pd = abbvie_wd * ab_ideal_fr
    denom = nu_ideal_pd + ab_ideal_pd
    if denom == 0:
        return 0.0

    ideal_ms_p = nu_ideal_pd / denom
    ideal_pd_at_ocgrp_scale = ideal_ms_p * ocgrp_pd_p
    nurtec_actual_pd_computed = _get(curr, "Nurtec", pkey, "FILL_RATE") * nurtec_wd

    return (nurtec_actual_pd_computed - ideal_pd_at_ocgrp_scale) / ocgrp_pd_overall


# ---------- Level 3: Reversals ------------------------------------------

def _overall_impact_rv(prev: dict, curr: dict) -> float:
    cgrp_pd_curr = _get(curr, "Overall", "Overall", "PD_CLAIMS")
    if cgrp_pd_curr == 0:
        return 0.0
    nurtec_ideal_fr = _ideal_fr_linear(
        _get(curr, "Nurtec", "Overall", "FILL_RATE"),
        _get(curr, "Nurtec", "Overall", "RV_RATE"),
        _get(prev, "Nurtec", "Overall", "RV_RATE"),
    )
    abbvie_ideal_fr = _ideal_fr_linear(
        _get(curr, "Abbvie", "Overall", "FILL_RATE"),
        _get(curr, "Abbvie", "Overall", "RV_RATE"),
        _get(prev, "Abbvie", "Overall", "RV_RATE"),
    )
    nurtec_wd = _get(curr, "Nurtec", "Overall", "WD")
    abbvie_wd = _get(curr, "Abbvie", "Overall", "WD")
    ideal_nurtec_pd = nurtec_wd * nurtec_ideal_fr
    ideal_abbvie_pd = abbvie_wd * abbvie_ideal_fr
    # Nurtec + Abbvie only (workbook convention).
    ideal_market_pd = ideal_nurtec_pd + ideal_abbvie_pd
    ideal_ms = ideal_nurtec_pd / ideal_market_pd if ideal_market_pd else 0.0
    actual_ms = _get(curr, "Nurtec", "Overall", "PD_MARKET_SHARE")
    return actual_ms - ideal_ms


def _payer_impact_rv(prev: dict, curr: dict, payer: str) -> float:
    """Payer-level RV impact -- symmetric to RJ, but holds RV at prev.

    ideal_FR = 1 - (RJ_curr + RV_prev).
    """
    pkey = _payer_key(payer)
    ocgrp_pd_overall = _get(curr, "Overall", "Overall", "PD_CLAIMS")
    ocgrp_pd_p = _get(curr, "Overall", pkey, "PD_CLAIMS")
    if ocgrp_pd_overall == 0:
        return 0.0

    nurtec_wd = _get(curr, "Nurtec", pkey, "WD")
    abbvie_wd = _get(curr, "Abbvie", pkey, "WD")

    nu_ideal_fr = 1.0 - (
        _get(curr, "Nurtec", pkey, "RJ_RATE") + _get(prev, "Nurtec", pkey, "RV_RATE")
    )
    ab_ideal_fr = 1.0 - (
        _get(curr, "Abbvie", pkey, "RJ_RATE") + _get(prev, "Abbvie", pkey, "RV_RATE")
    )

    nu_ideal_pd = nurtec_wd * nu_ideal_fr
    ab_ideal_pd = abbvie_wd * ab_ideal_fr
    denom = nu_ideal_pd + ab_ideal_pd
    if denom == 0:
        return 0.0

    ideal_ms_p = nu_ideal_pd / denom
    ideal_pd_at_ocgrp_scale = ideal_ms_p * ocgrp_pd_p
    nurtec_actual_pd_computed = _get(curr, "Nurtec", pkey, "FILL_RATE") * nurtec_wd

    return (nurtec_actual_pd_computed - ideal_pd_at_ocgrp_scale) / ocgrp_pd_overall


# ---------- Scaling + assembly -----------------------------------------

def _scale(overall_impact: float, payer_impacts_raw: Dict[str, float]) -> LeverBreakdown:
    raw_sum = sum(payer_impacts_raw.values())
    factor = overall_impact / raw_sum if abs(raw_sum) > 1e-12 else 1.0
    scaled = {p: v * factor for p, v in payer_impacts_raw.items()}
    return LeverBreakdown(
        overall_impact=overall_impact,
        payer_impacts_raw=payer_impacts_raw,
        payer_impacts_scaled=scaled,
        scaling_factor=factor,
    )


def build_waterfall(prev_metrics: dict, curr_metrics: dict) -> WaterfallResult:
    prev_ms = _get(prev_metrics, "Nurtec", "Overall", "PD_MARKET_SHARE")
    new_ms = _get(curr_metrics, "Nurtec", "Overall", "PD_MARKET_SHARE")
    total_delta = new_ms - prev_ms

    wd_overall = _overall_impact_wd(prev_metrics, curr_metrics)
    wd_raw = {p: _payer_impact_wd(prev_metrics, curr_metrics, p) for p in PAYERS}
    wd = _scale(wd_overall, wd_raw)

    rj_overall = _overall_impact_rj(prev_metrics, curr_metrics)
    rj_raw = {p: _payer_impact_rj(prev_metrics, curr_metrics, p) for p in PAYERS}
    rj = _scale(rj_overall, rj_raw)

    rv_overall = _overall_impact_rv(prev_metrics, curr_metrics)
    rv_raw = {p: _payer_impact_rv(prev_metrics, curr_metrics, p) for p in PAYERS}
    rv = _scale(rv_overall, rv_raw)

    other = total_delta - (wd_overall + rj_overall + rv_overall)

    return WaterfallResult(
        previous_ms=prev_ms,
        new_ms=new_ms,
        total_delta=total_delta,
        wd=wd,
        rj=rj,
        rv=rv,
        other=other,
        debug={
            "wd_raw_sum": sum(wd_raw.values()),
            "rj_raw_sum": sum(rj_raw.values()),
            "rv_raw_sum": sum(rv_raw.values()),
        },
    )


def rescale_to_npa(res: WaterfallResult, npa_prev_ms: float, npa_curr_ms: float) -> WaterfallResult:
    """Rescale the LAAD waterfall to NPA market-share space.

    Matches the Excel workbook's convention: the 3 levers (WD / Rejections /
    Reversals) are scaled so their sum equals the full NPA delta. The LAAD
    residual "Other reasons" is absorbed into the levers rather than carried
    through (Excel's NPA-scaled tab doesn't show it separately).

      factor = (npa_curr - npa_prev) / (L1_laad + L2_laad + L3_laad)

    Applied to each lever's overall impact and every payer sub-impact, so the
    waterfall telescopes exactly from NPA prev -> NPA curr with Other = 0.
    """
    laad_levers_sum = res.wd.overall_impact + res.rj.overall_impact + res.rv.overall_impact
    npa_delta = npa_curr_ms - npa_prev_ms
    factor = (npa_delta / laad_levers_sum) if abs(laad_levers_sum) > 1e-12 else 0.0

    def scale_lever(l: LeverBreakdown) -> LeverBreakdown:
        return LeverBreakdown(
            overall_impact=l.overall_impact * factor,
            payer_impacts_raw={p: v * factor for p, v in l.payer_impacts_raw.items()},
            payer_impacts_scaled={p: v * factor for p, v in l.payer_impacts_scaled.items()},
            scaling_factor=l.scaling_factor,
        )

    return WaterfallResult(
        previous_ms=npa_prev_ms,
        new_ms=npa_curr_ms,
        total_delta=npa_delta,
        wd=scale_lever(res.wd),
        rj=scale_lever(res.rj),
        rv=scale_lever(res.rv),
        other=0.0,
        debug={"laad_to_npa_factor": factor, "laad_levers_sum": laad_levers_sum, **res.debug},
    )
