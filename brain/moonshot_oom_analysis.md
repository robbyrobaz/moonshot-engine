# Moonshot OOM Analysis

## Root cause

`src/tournament/backtest.py` loads the full joined feature+label corpus for a challenger in `_load_labeled_data()`.

Current query:

```sql
SELECT f.symbol, f.ts, f.feature_names, f.feature_values, l.label
FROM features f
JOIN labels l ON f.symbol = l.symbol AND f.ts = l.ts
WHERE l.direction = ? AND l.tp_pct = ? AND l.sl_pct = ?
ORDER BY f.ts ASC
```

The only filters applied are:

- `direction`
- `tp_pct`
- `sl_pct`

It does **not** filter by:

- `feature_set`
- `confidence_threshold`
- `model_type`
- any train/test time window
- any specific challenger `model_id`

That means every challenger with the same direction and global TP/SL settings scans the same full label population. If there are about 3.5M matching labels for one direction, every backtest attempt loads that same 3.5M-row join.

## Why it OOMs

The previous implementation called `fetchall()`, which materialized the full SQL result into Python row objects before feature extraction.

That created multiple large in-memory copies at once:

- SQLite result rows from `fetchall()`
- decoded JSON feature payloads per row
- Python `X_rows` list of lists
- final NumPy arrays `X`, `y`, and `pnl`

So the backtest was not just loading 3.5M labels. It was loading 3.5M joined rows and then duplicating that data across Python containers during transformation.

## What is now changed

`src/tournament/backtest.py` now:

- logs RSS memory before label load
- logs RSS memory after label load
- replaces `fetchall()` with `fetchmany(100_000)` progress batches
- logs batch progress with RSS so the memory ramp is visible in logs

This removes the worst peak caused by eager `fetchall()`, but it still loads the full filtered corpus into NumPy arrays for the backtest.

## Durable fix

The real fix is to stop materializing the entire dataset in Python.

Recommended path: move the backtest dataset build to DuckDB and keep intermediate results on disk.

Example approach:

```python
import duckdb


def load_backtest_dataset_duckdb(sqlite_path: str, direction: str, feature_names: list[str]):
    con = duckdb.connect(database=":memory:")
    con.execute("ATTACH ? AS sqlite_db (TYPE sqlite)", [sqlite_path])

    feature_list = ", ".join([f"json_extract_string(f.feature_values, '$.{name}') AS {name}" for name in feature_names])

    query = f"""
        CREATE TEMP TABLE backtest_rows AS
        SELECT
            f.ts,
            l.label,
            {feature_list}
        FROM sqlite_db.features f
        JOIN sqlite_db.labels l
          ON f.symbol = l.symbol AND f.ts = l.ts
        WHERE l.direction = ?
          AND l.tp_pct = ?
          AND l.sl_pct = ?
        ORDER BY f.ts
    """
    con.execute(query, [direction, TP_PCT, SL_PCT])

    for chunk in con.execute("SELECT * FROM backtest_rows").fetch_record_batch(rows_per_batch=100_000):
        yield chunk
```

With that shape, the backtest can:

- stream record batches
- write fold slices to Arrow/NumPy incrementally
- avoid holding both raw SQL rows and decoded Python JSON blobs at the same time

## Lower-risk interim option

If DuckDB is too much change right now, keep SQLite and batch in 100K chunks end-to-end:

- read rows with `fetchmany(100_000)`
- immediately convert to compact NumPy chunk arrays
- append chunks to on-disk memmaps instead of Python lists
- train each fold from memmap-backed arrays

That keeps memory bounded and avoids Python list growth across millions of rows.

## Bottom line

The OOM is caused by eager full-corpus loading for a direction/TP/SL slice, not by challenger-specific params. The current model params only change which columns are selected after load, not which rows are read from storage.
