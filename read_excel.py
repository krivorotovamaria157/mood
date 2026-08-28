import pandas as pd
import json

xl = pd.ExcelFile('эмоции.xlsx')
print('=== ЛИСТЫ ===')
print(json.dumps(xl.sheet_names, ensure_ascii=False))
print()

dfs = pd.read_excel('эмоции.xlsx', sheet_name=None)
for name in xl.sheet_names:
    print(f'=== ЛИСТ: {name} ===')
    df = dfs[name]
    print(f'  shape: {df.shape}')
    print(f'  columns: {list(df.columns)}')
    print()
    print(df.to_string())
    print()
