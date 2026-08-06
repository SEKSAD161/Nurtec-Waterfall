import base64
b = base64.b64encode(open(r'c:\Users\SEKSAD\.snowflake\cortex\playground\workspace\nurtec-waterfall-app\src\waterfall.py','rb').read()).decode()
CHUNK = 5000
parts = [b[i:i+CHUNK] for i in range(0, len(b), CHUNK)]
values = ",".join(["(" + str(i) + ",'" + p + "','waterfall.py')" for i, p in enumerate(parts)])
sql = "INSERT INTO VAW_AMER_DESIGN.USPRIMARYCAREADHOCANALYTICSPARTC._wf_b64 (chunk_id, chunk, fname) VALUES " + values
open(r'c:\Users\SEKSAD\.snowflake\cortex\playground\workspace\_ins_wf.sql', 'w').write(sql)
print('wf', len(sql), 'parts', len(parts))

b2 = base64.b64encode(open(r'c:\Users\SEKSAD\.snowflake\cortex\playground\workspace\nurtec-waterfall-app\streamlit_app.py','rb').read()).decode()
parts2 = [b2[i:i+CHUNK] for i in range(0, len(b2), CHUNK)]
values2 = ",".join(["(" + str(i) + ",'" + p + "','streamlit_app.py')" for i, p in enumerate(parts2)])
sql2 = "INSERT INTO VAW_AMER_DESIGN.USPRIMARYCAREADHOCANALYTICSPARTC._wf_b64 (chunk_id, chunk, fname) VALUES " + values2
open(r'c:\Users\SEKSAD\.snowflake\cortex\playground\workspace\_ins_sa.sql', 'w').write(sql2)
print('sa', len(sql2), 'parts', len(parts2))
