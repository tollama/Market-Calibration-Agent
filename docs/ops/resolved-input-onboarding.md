# Resolved Input Onboarding

Use this when you want to run:

```bash
python3 scripts/generate_real_data_forecasting_pack.py
```

## Accepted Input Shapes

### 1. Raw Snapshot Rows

Minimum required columns:

- `market_id`
- `ts`
- one of `resolution_ts`, `end_ts`, `event_end_ts`
- one of `label`, `label_status`

Recommended columns:

- `event_id`
- `category`
- `platform`
- `p_yes` or `market_prob`
- `volume_24h`
- `open_interest`

`label_status` should use resolved binary values such as `RESOLVED_TRUE` and `RESOLVED_FALSE`.

### 2. Resolved Dataset Rows

Minimum required columns:

- `market_id`
- `snapshot_ts`
- `resolution_ts`
- `label`

Recommended columns:

- `market_prob`
- `category`
- `liquidity_bucket`
- `tte_bucket`
- `horizon_hours`
- feature columns already produced by the forecasting pipeline

## Explicit Input Path

If auto-discovery is not enough, pass the file directly:

```bash
python3 scripts/generate_real_data_forecasting_pack.py \
  --input /absolute/path/to/resolved_dataset.csv \
  --output-dir artifacts/forecasting_baseline_pack/real_data_v1
```

For repo-relative discovery in a different directory:

```bash
python3 scripts/generate_real_data_forecasting_pack.py \
  --search-root /absolute/path/to/workspace
```

## Failure Modes

The script writes a blocked pack when:

- the input path does not exist
- the file format cannot be read
- the schema is not recognized
- the resolved dataset becomes empty after filtering

The blocking reason is written to:

- `artifacts/forecasting_baseline_pack/real_data_v1/status.json`

## Current Workspace State

The current repo run is blocked because no local resolved input file is present.
See:

- `artifacts/forecasting_baseline_pack/real_data_v1/status.json`
