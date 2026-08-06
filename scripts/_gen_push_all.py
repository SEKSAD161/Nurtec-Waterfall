import base64
files = [
    ('waterfall.py',
     r'c:\Users\SEKSAD\.snowflake\cortex\playground\workspace\nurtec-waterfall-app\src\waterfall.py',
     'snow://workspace/USER$.PUBLIC."DEFAULT$"/versions/live/nurtec-waterfall-app/src/waterfall.py'),
    ('streamlit_app.py',
     r'c:\Users\SEKSAD\.snowflake\cortex\playground\workspace\nurtec-waterfall-app\streamlit_app.py',
     'snow://workspace/USER$.PUBLIC."DEFAULT$"/versions/live/nurtec-waterfall-app/streamlit_app.py'),
]

# Build all inserts + push actions in one big multi-statement SQL
lines = ["DELETE FROM VAW_AMER_DESIGN.USPRIMARYCAREADHOCANALYTICSPARTC._wf_b64;"]
push_calls = []
for order, (fname, path, uri) in enumerate(files):
    b = base64.b64encode(open(path, 'rb').read()).decode()
    # split into ~2000 chunks
    CHUNK = 2000
    parts = [b[i:i+CHUNK] for i in range(0, len(b), CHUNK)]
    values = ",\n".join([f"({order*100 + idx}, '{p}', '{fname}')" for idx, p in enumerate(parts)])
    lines.append(f"INSERT INTO VAW_AMER_DESIGN.USPRIMARYCAREADHOCANALYTICSPARTC._wf_b64 (chunk_id, chunk, fname) VALUES\n{values};")
    push_calls.append((fname, uri, order*100, order*100 + len(parts) - 1))

# Write a big anonymous block that reassembles and writes each file
lines.append("""
BEGIN
""")
for i, (fname, uri, lo, hi) in enumerate(push_calls):
    lines.append(f"""
LET content_{i} STRING := (
  SELECT TO_VARCHAR(TO_BINARY(LISTAGG(chunk, '') WITHIN GROUP (ORDER BY chunk_id), 'BASE64'), 'UTF-8')
  FROM VAW_AMER_DESIGN.USPRIMARYCAREADHOCANALYTICSPARTC._wf_b64
  WHERE chunk_id BETWEEN {lo} AND {hi}
);
CALL VAW_AMER_DESIGN.USPRIMARYCAREADHOCANALYTICSPARTC.write_ws_text_sp('{uri}', :content_{i});
""")
lines.append("RETURN 'done';\nEND;")

sql = "\n".join(lines)
open(r'c:\Users\SEKSAD\.snowflake\cortex\playground\workspace\_push_all.sql', 'w').write(sql)
print('total SQL chars:', len(sql))
