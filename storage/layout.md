# Storage Layout

All data is stored under a single root directory.

## Directory convention

```text
<root>/
  raw/
    <dataset>/
      dt=YYYY-MM-DD/
        *.jsonl
  derived/
    <dataset>/
      dt=YYYY-MM-DD/
        *.parquet
```

## Partition rule

- Partition key: `dt`
- Partition format: `dt=YYYY-MM-DD`
- `dt` accepts `date`, `datetime`, or ISO string input and is normalized to `YYYY-MM-DD`.

## Idempotency rule

- Writers use deterministic output paths (`dataset`, `dt`, `filename`).
- Re-running the same write replaces the same target file instead of appending.
- Optional row-level dedupe can be enabled by providing a `dedupe_key`.
