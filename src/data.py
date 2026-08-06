"""Snowflake data-loading for the Nurtec waterfall app.

Two sources:
  1. LAAD quarter metrics -- long-format table with columns
       QTR, CLAIM_TYPE, BRAND, PAYER, METRIC, VALUE
     Reshaped to a nested dict keyed by BRAND -> PAYER -> METRIC -> VALUE.

  2. NPA monthly metrics -- used only to compute Nurtec's NPA-level market share
     per quarter, so the LAAD waterfall can be rescaled to real-world NPA.
"""
from __future__ import annotations

import os

import pandas as pd
import streamlit as st

LAAD_TABLE = "VAW_AMER_DESIGN.USPRIMARYCAREADHOCANALYTICSPARTC.USPRIMARYCAREADHOCANALYTICSPARTC_SQL_NURTEC_WATERFALL_QTR_METRICS"
NPA_TABLE = "VAW_AMER_DESIGN.FORECASTING_DATA_ECOSYSTEM.FORECASTING_DATA_ECOSYSTEM_NURTEC_NPA_METRICS"


def _get_session():
    """Return a Snowpark session via st.connection."""
    conn = st.connection("snowflake", ttl=os.getenv("SNOWFLAKE_CONNECTION_TTL"))
    return conn.session()


@st.cache_data(ttl=3600, show_spinner="Loading LAAD waterfall metrics from Snowflake...")
def load_laad() -> pd.DataFrame:
    session = _get_session()
    df = session.sql(
        f"SELECT QTR, CLAIM_TYPE, BRAND, PAYER, METRIC, VALUE FROM {LAAD_TABLE}"
    ).to_pandas()
    df.columns = [c.upper() for c in df.columns]
    return df


@st.cache_data(ttl=3600, show_spinner="Loading NPA metrics from Snowflake...")
def load_npa_monthly() -> pd.DataFrame:
    session = _get_session()
    df = session.sql(
        f"""
        SELECT DATE, PRODUCT_NAME, METRIC, METRIC_VALUE
        FROM {NPA_TABLE}
        WHERE SOURCE = 'NPA'
          AND MARKET_CLASS = 'TOTAL'
          AND METRIC IN ('TRx','NRx','OCGRP_TRx','OCGRP_NRx')
        """
    ).to_pandas()
    df.columns = [c.upper() for c in df.columns]
    df["DATE"] = pd.to_datetime(df["DATE"])
    # pandas gives period strings like '2024Q1' which match the LAAD QTR values
    df["QTR"] = df["DATE"].dt.to_period("Q").astype(str)
    return df


def npa_market_share_by_qtr(claim_type: str) -> pd.DataFrame:
    """Quarterly Nurtec NPA market share.

    For TRx  -> Nurtec TRx / OCGRP_TRx.
    For NBRx -> Nurtec NRx / OCGRP_NRx  (NPA has no NBRx grain; NRx is the
    closest analogue at the market level).
    """
    monthly = load_npa_monthly()
    if claim_type.upper() == "TRX":
        nurtec_metric, market_metric = "TRx", "OCGRP_TRx"
    else:
        nurtec_metric, market_metric = "NRx", "OCGRP_NRx"

    nurtec = (
        monthly[(monthly["PRODUCT_NAME"] == "NURTEC") & (monthly["METRIC"] == nurtec_metric)]
        .groupby("QTR", as_index=False)["METRIC_VALUE"].sum()
        .rename(columns={"METRIC_VALUE": "NURTEC_VOL"})
    )
    market = (
        monthly[(monthly["PRODUCT_NAME"] == "OVERALL") & (monthly["METRIC"] == market_metric)]
        .groupby("QTR", as_index=False)["METRIC_VALUE"].sum()
        .rename(columns={"METRIC_VALUE": "MARKET_VOL"})
    )
    out = nurtec.merge(market, on="QTR", how="inner")
    out["NPA_MS"] = out["NURTEC_VOL"] / out["MARKET_VOL"]
    return out.sort_values("QTR").reset_index(drop=True)


def available_quarters(df: pd.DataFrame, claim_type: str) -> list:
    q = df[df["CLAIM_TYPE"].str.upper() == claim_type.upper()]["QTR"].unique().tolist()
    return sorted(q)


def slice_metrics(df: pd.DataFrame, qtr: str, claim_type: str) -> dict:
    """Return nested dict metrics[BRAND][PAYER][METRIC] = value.

    The source table only carries BRAND in ('Nurtec', 'Abbvie') -- the workbook's
    "Oral CGRP" market total is the sum of the two brands. We synthesize a
    BRAND='Overall' row here so the waterfall math (which reads market-total WD
    and PD_CLAIMS at Overall/payer and Overall/Overall) has values to work with.
    """
    sub = df[(df["QTR"] == qtr) & (df["CLAIM_TYPE"].str.upper() == claim_type.upper())]
    out: dict = {}
    for _, r in sub.iterrows():
        out.setdefault(r["BRAND"], {}).setdefault(r["PAYER"], {})[r["METRIC"]] = r["VALUE"]

    # Synthesize market totals -- BRAND = 'Overall' -- from Nurtec + Abbvie.
    market: dict = {}
    for brand, payers in out.items():
        if brand == "Overall":
            continue
        for payer, metrics in payers.items():
            m = market.setdefault(payer, {})
            for metric in ("WD", "PD_CLAIMS"):
                v = metrics.get(metric)
                if v is not None:
                    m[metric] = m.get(metric, 0.0) + float(v)
    if market:
        out["Overall"] = market
    return out
