import base64
b = base64.b64encode(open(r'c:\Users\SEKSAD\.snowflake\cortex\playground\workspace\nurtec-waterfall-app\streamlit_app.py','rb').read()).decode()
CHUNK = 1500
parts = [b[i:i+CHUNK] for i in range(0, len(b), CHUNK)]
for idx, p in enumerate(parts):
    sql = ("INSERT INTO VAW_AMER_DESIGN.USPRIMARYCAREADHOCANALYTICSPARTC._wf_b64 "
           "(chunk_id, chunk, fname) VALUES ("
           + str(idx) + ", '" + p + "', 'streamlit_app.py');")
    open(rf'c:\Users\SEKSAD\.snowflake\cortex\playground\workspace\_sa5_{idx:02d}.sql', 'w', newline='').write(sql)
print('chunks:', len(parts))
