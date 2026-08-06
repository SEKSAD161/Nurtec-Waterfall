import os
files = [
    ('qc',              15),
    ('streamlit_app',   11),
]
sql_parts = []
count = 0
for stem, n in files:
    for idx in range(n):
        path = rf'c:\Users\SEKSAD\.snowflake\cortex\playground\workspace\_i4_{stem}_{idx:02d}.sql'
        sql_parts.append(open(path).read().rstrip(';') + ';')
        count += 1
# Split into two halves
half = len(sql_parts) // 2
open(r'c:\Users\SEKSAD\.snowflake\cortex\playground\workspace\_batch1.sql', 'w', newline='').write('\n'.join(sql_parts[:half]))
open(r'c:\Users\SEKSAD\.snowflake\cortex\playground\workspace\_batch2.sql', 'w', newline='').write('\n'.join(sql_parts[half:]))
print('batch1 stmts:', half, 'chars:', sum(len(s) for s in sql_parts[:half]))
print('batch2 stmts:', len(sql_parts)-half, 'chars:', sum(len(s) for s in sql_parts[half:]))
