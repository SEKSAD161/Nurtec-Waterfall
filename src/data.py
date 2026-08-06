"""Data loading for the Nurtec waterfall app.

Two sources:
  1. LAAD quarter metrics -- long-format with columns
       QTR, CLAIM_TYPE, BRAND, PAYER, METRIC, VALUE.
     Reshaped to a nested dict keyed by BRAND -> PAYER -> METRIC -> VALUE.

  2. NPA monthly metrics -- used only to compute Nurtec's NPA-level market share
     per quarter, so the LAAD waterfall can be rescaled to real-world NPA.

Loading strategy
----------------
Each source tries three loaders in order and uses the first one that works:

  1. Dataiku Dataset API (`dataiku.Dataset(name).get_dataframe()`).
     LAAD dataset name defaults to `SQL_NURTEC_WATERFALL_QTR_METRICS`, override
     with env var `DKU_LAAD_DATASET`. NPA is skipped by default because there
     is no equivalent Dataiku dataset today; set `DKU_NPA_DATASET` to opt in.
  2. Bundled CSV under `data/laad.csv` / `data/npa.csv`.
  3. Snowflake via `st.connection("snowflake")` (lazy import, so environments
     without `snowflake-snowpark-python` won't fail at module load).
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st

LAAD_TABLE = "VAW_AMER_DESIGN.USPRIMARYCAREADHOCANALYTICSPARTC.USPRIMARYCAREADHOCANALYTICSPARTC_SQL_NURTEC_WATERFALL_QTR_METRICS"
NPA_TABLE = "VAW_AMER_DESIGN.FORECASTING_DATA_ECOSYSTEM.FORECASTING_DATA_ECOSYSTEM_NURTEC_NPA_METRICS"

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_LAAD_CSV = _DATA_DIR / "laad.csv"
_NPA_CSV = _DATA_DIR / "npa.csv"

_DKU_LAAD_DATASET = os.getenv("DKU_LAAD_DATASET", "SQL_NURTEC_WATERFALL_QTR_METRICS")
_DKU_NPA_DATASET = os.getenv("DKU_NPA_DATASET")  # None by default; opt-in


def _try_dataiku(dataset_name: str | None) -> pd.DataFrame | None:
    """Load a Dataiku Dataset by name. Returns None if Dataiku or the dataset
    isn't available in this environment."""
    if not dataset_name:
        return None
    try:
        import dataiku  # type: ignore
    except Exception:
        return None
    try:
        return dataiku.Dataset(dataset_name).get_dataframe()
    except Exception:
        return None


def _get_session():
    """Lazy: return a Snowpark session via st.connection.

    Only invoked when Dataiku + CSV loaders both miss, so environments without
    the Snowflake connector installed never trip the import.
    """
    conn = st.connection("snowflake", ttl=os.getenv("SNOWFLAKE_CONNECTION_TTL"))
    return conn.session()


@st.cache_data(ttl=3600, show_spinner="Loading LAAD waterfall metrics...")
def load_laad() -> pd.DataFrame:
    df = _try_dataiku(_DKU_LAAD_DATASET)
    if df is None:
        if _LAAD_CSV.exists():
            df = pd.read_csv(_LAAD_CSV)
        else:
            session = _get_session()
            df = session.sql(
                f"SELECT QTR, CLAIM_TYPE, BRAND, PAYER, METRIC, VALUE FROM {LAAD_TABLE}"
            ).to_pandas()
    df.columns = [c.upper() for c in df.columns]
    return df


@st.cache_data(ttl=3600, show_spinner="Loading NPA metrics...")
def load_npa_monthly() -> pd.DataFrame:
    df = _try_dataiku(_DKU_NPA_DATASET)
    if df is None:
        if _NPA_CSV.exists():
            df = pd.read_csv(_NPA_CSV)
        else:
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
    df["QTR"] = df["DATE"].dt.to_period("Q").astype(str)
    # If we pulled the raw NPA dataset from Dataiku, apply the same filter used
    # in the Snowflake query so downstream aggregation matches.
    if "SOURCE" in df.columns and "MARKET_CLASS" in df.columns:
        df = df[
            (df["SOURCE"] == "NPA")
            & (df["MARKET_CLASS"] == "TOTAL")
            & (df["METRIC"].isin(["TRx", "NRx", "OCGRP_TRx", "OCGRP_NRx"]))
        ].reset_index(drop=True)
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
