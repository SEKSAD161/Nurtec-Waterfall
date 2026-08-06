import base64
# Single big INSERT for waterfall.py in 2-chunk form
b = base64.b64encode(open(r'c:\Users\SEKSAD\.snowflake\cortex\playground\workspace\nurtec-waterfall-app\src\waterfall.py','rb').read()).decode()
CHUNK = 8000
parts = [b[i:i+CHUNK] for i in range(0, len(b), CHUNK)]
values = ",\n".join([f"({idx}, '{p}', 'waterfall.py')" for idx, p in enumerate(parts)])
sql = f"INSERT INTO VAW_AMER_DESIGN.USPRIMARYCAREADHOCANALYTICSPARTC._wf_b64 (chunk_id, chunk, fname) VALUES {values}"
open(r'c:\Users\SEKSAD\.snowflake\cortex\playground\workspace\_ins_wf.sql','w').write(sql)
print('wf insert len:', len(sql), 'parts:', len(parts))

b2 = base64.b64encode(open(r'c:\Users\SEKSAD\.snowflake\cortex\playground\workspace\nurtec-waterfall-app\streamlit_app.py','rb').read()).decode()
parts2 = [b2[i:i+CHUNK] for i in range(0, len(b2), CHUNK)]
# offset chunk_ids to avoid collision (100+)
values2 = ",\n".join([f"({100+idx}, '{p}', 'streamlit_app.py')" for idx, p in enumerate(parts2)])
sql2 = f"INSERT INTO VAW_AMER_DESIGN.USPRIMARYCAREADHOCANALYTICSPARTC._wf_b64 (chunk_id, chunk, fname) VALUES {values2}"
open(r'c:\Users\SEKSAD\.snowflake\cortex\playground\workspace\_ins_sa.sql','w').write(sql2)
print('sa insert len:', len(sql2), 'parts:', len(parts2))
