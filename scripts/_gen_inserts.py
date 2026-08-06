import base64
files = [
    ('waterfall.py',
     r'c:\Users\SEKSAD\.snowflake\cortex\playground\workspace\nurtec-waterfall-app\src\waterfall.py',
     'snow://workspace/USER$.PUBLIC."DEFAULT$"/versions/live/nurtec-waterfall-app/src/waterfall.py'),
    ('streamlit_app.py',
     r'c:\Users\SEKSAD\.snowflake\cortex\playground\workspace\nurtec-waterfall-app\streamlit_app.py',
     'snow://workspace/USER$.PUBLIC."DEFAULT$"/versions/live/nurtec-waterfall-app/streamlit_app.py'),
]
CHUNK = 2000
insert_stmts = []
for fname, path, uri in files:
    b = base64.b64encode(open(path, 'rb').read()).decode()
    for i in range(0, len(b), CHUNK):
        chunk_id = i // CHUNK
        chunk = b[i:i+CHUNK]
        insert_stmts.append(
            f"INSERT INTO VAW_AMER_DESIGN.USPRIMARYCAREADHOCANALYTICSPARTC._wf_b64 (chunk_id, chunk) SELECT {chunk_id}, '{chunk}';"
        )
    # separator row with URI info
    insert_stmts.append(
        f"INSERT INTO VAW_AMER_DESIGN.USPRIMARYCAREADHOCANALYTICSPARTC._wf_b64 (chunk_id, chunk) SELECT -1, '||FILE||{fname}||URI||{uri}';"
    )
open(r'c:\Users\SEKSAD\.snowflake\cortex\playground\workspace\_inserts.sql', 'w').write('\n'.join(insert_stmts))
print('inserts:', len(insert_stmts))
