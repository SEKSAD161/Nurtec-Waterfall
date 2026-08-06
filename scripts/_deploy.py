"""Push updated qc.py + streamlit_app.py into the workspace via a direct
Snowflake connection, then sync -> commit the streamlit app to a new version.

Uses the pfe-amerprod01 connection (OAuth) already configured in
~/.snowflake/connections.toml -- avoids the buggy `cortex ws cp` upload
and the 26-chunk manual INSERT dance.
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

import snowflake.connector

ROOT = Path(r"c:\Users\SEKSAD\.snowflake\cortex\playground\workspace\nurtec-waterfall-app")
FILES = [
    (ROOT / "src" / "qc.py",
     'snow://workspace/USER$.PUBLIC."DEFAULT$"/versions/live/nurtec-waterfall-app/src/qc.py',
     'qc.py'),
    (ROOT / "streamlit_app.py",
     'snow://workspace/USER$.PUBLIC."DEFAULT$"/versions/live/nurtec-waterfall-app/streamlit_app.py',
     'streamlit_app.py'),
]


def _load_oauth_token() -> str:
    """Read the JWT access token cortex CLI already negotiated (in its cache).

    The credential_cache_v1.json holds three entries; the third is a JWT
    `eyJ...`.  We ignore the two refresh-token-shaped entries (`ver:X-hint:...`).
    """
    import json
    cache = json.loads(
        Path.home().joinpath(".snowflake", "cortex", "cache", "credential_cache",
                             "credential_cache_v1.json").read_text()
    )
    for tok in cache.get("tokens", {}).values():
        if tok.startswith("eyJ"):
            return tok
    raise RuntimeError("No JWT access token found in cortex credential cache.")


def main() -> int:
    cn = snowflake.connector.connect(
        account="PFE-AMERPROD01",
        user="SEKSAD",
        authenticator="oauth",
        token=_load_oauth_token(),
    )
    cur = cn.cursor()

    print("[1/4] Setting session context...")
    cur.execute("USE ROLE COMM_SEKSAD_ROLE")
    cur.execute("USE DATABASE VAW_AMER_DESIGN")
    cur.execute("USE SCHEMA USPRIMARYCAREADHOCANALYTICSPARTC")
    cur.execute("USE WAREHOUSE VAW_AMER_PROD_WH")

    print("[2/4] Resetting chunk staging table...")
    cur.execute(
        "CREATE OR REPLACE TABLE VAW_AMER_DESIGN.USPRIMARYCAREADHOCANALYTICSPARTC._wf_b64 "
        "(chunk_id INT, chunk STRING, fname STRING)"
    )

    print("[3/4] Uploading files (chunk + reassemble on server)...")
    CHUNK = 4000
    for path, uri, fname in FILES:
        raw = path.read_bytes()
        b64 = base64.b64encode(raw).decode("ascii")
        parts = [b64[i:i + CHUNK] for i in range(0, len(b64), CHUNK)]
        print(f"  {fname}: {len(raw):,} bytes -> {len(parts)} chunks")

        cur.execute(
            f"DELETE FROM VAW_AMER_DESIGN.USPRIMARYCAREADHOCANALYTICSPARTC._wf_b64 "
            f"WHERE fname = '{fname}'"
        )
        cur.executemany(
            "INSERT INTO VAW_AMER_DESIGN.USPRIMARYCAREADHOCANALYTICSPARTC._wf_b64 "
            "(chunk_id, chunk, fname) VALUES (%s, %s, %s)",
            [(idx, part, fname) for idx, part in enumerate(parts)],
        )
        cur.execute(
            "CALL VAW_AMER_DESIGN.USPRIMARYCAREADHOCANALYTICSPARTC.write_ws_from_chunks_sp(%s, %s)",
            (uri, fname),
        )
        row = cur.fetchone()
        print(f"    -> {row[0]}")

    print("[4/4] Syncing workspace -> streamlit live and committing new version...")
    cur.execute("USE ROLE VAW_AMER_DESIGN_DSS_COMMERCIAL")
    try:
        cur.execute(
            "ALTER STREAMLIT VAW_AMER_DESIGN.USPRIMARYCAREADHOCANALYTICSPARTC.NURTEC_WATERFALL_APP "
            "ADD LIVE VERSION FROM LAST"
        )
        print("  + Added live version")
    except snowflake.connector.errors.ProgrammingError as e:
        if "already a live version" in str(e).lower():
            print("  + Live version already exists (ok)")
        else:
            raise
    cur.execute(
        "COPY FILES "
        "INTO 'snow://streamlit/VAW_AMER_DESIGN.USPRIMARYCAREADHOCANALYTICSPARTC.NURTEC_WATERFALL_APP/versions/live/' "
        "FROM 'snow://workspace/USER$.PUBLIC.\"DEFAULT$\"/versions/live/nurtec-waterfall-app/'"
    )
    n = len(cur.fetchall())
    print(f"  + Copied {n} files to streamlit live location")
    cur.execute(
        "ALTER STREAMLIT VAW_AMER_DESIGN.USPRIMARYCAREADHOCANALYTICSPARTC.NURTEC_WATERFALL_APP COMMIT"
    )
    print(f"  + {cur.fetchone()[0]}")

    cur.execute("USE ROLE COMM_SEKSAD_ROLE")
    cur.execute("DROP TABLE IF EXISTS VAW_AMER_DESIGN.USPRIMARYCAREADHOCANALYTICSPARTC._wf_b64")
    print("  + Cleaned up staging table")

    cn.close()
    print("\nDone. Hard-refresh the Streamlit app in your browser.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
