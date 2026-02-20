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

### Gamma raw ingest compatibility layout (PRD1 I-01)

`pipelines/ingest_gamma_raw.py` writes both layouts during migration-safe operation:

- Canonical PRD path: `raw/gamma/dt=YYYY-MM-DD/{markets,events,markets_original,events_original}.jsonl`
- Legacy dataset-scoped path: `raw/gamma/{markets,events,markets_original,events_original}/dt=YYYY-MM-DD/data.jsonl`

This dual-write behavior preserves existing readers while aligning with PRD wording.

## Partition rule

- Partition key: `dt`
- Partition format: `dt=YYYY-MM-DD`
- `dt` accepts `date`, `datetime`, or ISO string input and is normalized to `YYYY-MM-DD`.

## Idempotency rule

- Writers use deterministic output paths (`dataset`, `dt`, `filename`).
- Re-running the same write replaces the same target file instead of appending.
- Optional row-level dedupe can be enabled by providing a `dedupe_key`.
