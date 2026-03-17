import sqlite3

conn = sqlite3.connect('data/moonshot_v2.db')

# Check LONG champion
row = conn.execute('''
    SELECT model_id, model_type, params, entry_threshold, bt_pf, bt_precision, bt_trades, ft_pf, ft_trades
    FROM tournament_models
    WHERE stage='champion' AND direction='long'
''').fetchone()

print("=" * 60)
print("LONG CHAMPION:")
print("=" * 60)
if row:
    print(f"Model ID: {row[0]}")
    print(f"Type: {row[1]}")
    print(f"Entry Threshold: {row[3]}")
    print(f"BT_PF: {row[4]}")
    print(f"BT_Precision: {row[5]}")
    print(f"BT_Trades: {row[6]}")
    print(f"FT_PF: {row[7]}")
    print(f"FT_Trades: {row[8]}")
else:
    print("NO LONG CHAMPION FOUND")

# Check SHORT champion
row = conn.execute('''
    SELECT model_id, model_type, entry_threshold, bt_pf, bt_precision, bt_trades, ft_pf, ft_trades
    FROM tournament_models
    WHERE stage='champion' AND direction='short'
''').fetchone()

print("\n" + "=" * 60)
print("SHORT CHAMPION (for comparison):")
print("=" * 60)
if row:
    print(f"Model ID: {row[0]}")
    print(f"Type: {row[1]}")
    print(f"Entry Threshold: {row[2]}")
    print(f"BT_PF: {row[3]}")
    print(f"BT_Precision: {row[4]}")
    print(f"BT_Trades: {row[5]}")
    print(f"FT_PF: {row[6]}")
    print(f"FT_Trades: {row[7]}")
else:
    print("NO SHORT CHAMPION")

# Count FT models
long_count = conn.execute("SELECT COUNT(*) FROM tournament_models WHERE direction='long' AND stage='forward_test'").fetchone()[0]
short_count = conn.execute("SELECT COUNT(*) FROM tournament_models WHERE direction='short' AND stage='forward_test'").fetchone()[0]

print("\n" + "=" * 60)
print("FORWARD TEST MODELS:")
print("=" * 60)
print(f"LONG models in FT: {long_count}")
print(f"SHORT models in FT: {short_count}")

conn.close()
