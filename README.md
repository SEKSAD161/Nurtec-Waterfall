# Nurtec QoQ NBRx & TRx Waterfall

Streamlit-in-Snowflake app that decomposes Nurtec's LAAD market-share change quarter-over-quarter into three levers (Written Demand / Rejections / Reversals) with a payer-level breakdown, and rescales the result to NPA (real-world) market share.

## Layout

- `streamlit_app.py` — app entrypoint, page layout, CSS injection
- `src/`
  - `data.py` — Snowflake queries + slicing helpers
  - `waterfall.py` — lever decomposition math (matches the source Excel workbook)
  - `charts.py` — Altair waterfall + payer-breakdown renderers, themed to the PC-HUB design language
  - `qc.py` — Excel-style calculation walk-through tables
- `.streamlit/config.toml` — theme fallbacks
- `snowflake.yml` — Snowflake CLI project descriptor
- `scripts/` — helper scripts used during initial data load / migrations (not part of the running app)

## Data sources

- LAAD (quarterly, long-format): `<DB>.<SCHEMA>.<..._NURTEC_WATERFALL_QTR_METRICS>`
- NPA (monthly): `<DB>.<SCHEMA>.<..._NURTEC_NPA_METRICS>`

## Deploy

Files are deployed to Snowflake via `snow streamlit deploy` (or by uploading through Snowsight Workspaces). The container runtime is Python 3.11.

## Waterfall convention

Sign convention: `impact = actual_MS - ideal_MS` (positive = the lever helped Nurtec's share). Fill-rate is modeled additively as `FR = 1 - RJ - RV`. Payer-level sub-impacts are scaled so they sum to the overall lever impact. See the in-app "How to use this waterfall?" and "What is the 'Other reasons' Category?" expanders for the full explanation.
