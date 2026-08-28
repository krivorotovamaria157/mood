import pandas as pd

for sheet in ['Дневник', 'Инсайты', 'Аналитика', 'Дашборд']:
    print(f'\n=== ЛИСТ: {sheet} ===')
    df = pd.read_excel('эмоции.xlsx', sheet_name=sheet)
    print(f'shape: {df.shape}')
    print(f'columns: {list(df.columns)}')
    print(df.to_string())
    print()
