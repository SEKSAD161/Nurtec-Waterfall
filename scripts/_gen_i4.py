import base64
files = [
    ('qc.py',              r'c:\Users\SEKSAD\.snowflake\cortex\playground\workspace\nurtec-waterfall-app\src\qc.py'),
    ('streamlit_app.py',   r'c:\Users\SEKSAD\.snowflake\cortex\playground\workspace\nurtec-waterfall-app\streamlit_app.py'),
]
CHUNK = 1500
for fname, path in files:
    b = base64.b64encode(open(path, 'rb').read()).decode()
    parts = [b[i:i+CHUNK] for i in range(0, len(b), CHUNK)]
    stem = fname.replace('.py','')
    for idx, p in enumerate(parts):
        sql = ("INSERT INTO VAW_AMER_DESIGN.USPRIMARYCAREADHOCANALYTICSPARTC._wf_b64 "
               "(chunk_id, chunk, fname) VALUES ("
               f"{idx}, '{p}', '{fname}');")
        open(rf'c:\Users\SEKSAD\.snowflake\cortex\playground\workspace\_i4_{stem}_{idx:02d}.sql','w',newline='').write(sql)
    print(fname, 'chunks:', len(parts))
