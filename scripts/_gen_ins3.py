import base64, os
files = [
    ('waterfall.py', r'c:\Users\SEKSAD\.snowflake\cortex\playground\workspace\nurtec-waterfall-app\src\waterfall.py'),
    ('streamlit_app.py', r'c:\Users\SEKSAD\.snowflake\cortex\playground\workspace\nurtec-waterfall-app\streamlit_app.py'),
]
CHUNK = 2500
for fname, path in files:
    b = base64.b64encode(open(path, 'rb').read()).decode()
    parts = [b[i:i+CHUNK] for i in range(0, len(b), CHUNK)]
    stem = fname.replace('.py','')
    for idx, p in enumerate(parts):
        # Wrap b64 into an INSERT SQL statement, ready to execute
        sql = "INSERT INTO VAW_AMER_DESIGN.USPRIMARYCAREADHOCANALYTICSPARTC._wf_b64 (chunk_id, chunk, fname) VALUES (" + str(idx) + ", '" + p + "', '" + fname + "');"
        out = rf'c:\Users\SEKSAD\.snowflake\cortex\playground\workspace\_ins_{stem}_c{idx}.sql'
        open(out, 'w', newline='').write(sql)
        print(fname, idx, len(sql))
