import base64
files = [
    ('waterfall',
     r'c:\Users\SEKSAD\.snowflake\cortex\playground\workspace\nurtec-waterfall-app\src\waterfall.py',
     'snow://workspace/USER$.PUBLIC."DEFAULT$"/versions/live/nurtec-waterfall-app/src/waterfall.py'),
    ('streamlit',
     r'c:\Users\SEKSAD\.snowflake\cortex\playground\workspace\nurtec-waterfall-app\streamlit_app.py',
     'snow://workspace/USER$.PUBLIC."DEFAULT$"/versions/live/nurtec-waterfall-app/streamlit_app.py'),
]
for name, path, uri in files:
    b = base64.b64encode(open(path,'rb').read()).decode()
    sql = (
        "DECLARE\n"
        "  content STRING;\n"
        "  result STRING;\n"
        "BEGIN\n"
        f"  content := TO_VARCHAR(TO_BINARY('{b}', 'BASE64'), 'UTF-8');\n"
        f"  CALL VAW_AMER_DESIGN.USPRIMARYCAREADHOCANALYTICSPARTC.write_ws_text_sp('{uri}', :content) INTO :result;\n"
        "  RETURN result;\n"
        "END;\n"
    )
    out_path = rf'c:\Users\SEKSAD\.snowflake\cortex\playground\workspace\_push_{name}.sql'
    open(out_path, 'w').write(sql)
    print(name, 'sql_len:', len(sql), '->', out_path)
