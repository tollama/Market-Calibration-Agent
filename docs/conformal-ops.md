# Conformal calibration ops

This project now supports a lightweight rolling conformal calibration job that writes a persisted state file for inference-time use.

## Defaults

- History input: `data/derived/calibration/conformal_history.jsonl`
- Persisted state: `data/derived/calibration/conformal_state.json`
- Target coverage: `0.80`
- Rolling window: last `2000` samples
- Minimum samples to update: `100`

State file schema (`schema_version=1`) includes:
- `adjustment`: `target_coverage`, `quantile_level`, `center_shift`, `width_scale`, `sample_size`
- `updated_at`
- `metadata` (source, pre/post coverage, etc.)

## Input history format

Each JSONL row (or CSV row) should provide:
- `q10`, `q50`, `q90` (or nested under `band` / `forecast_band`)
- `actual` (or `resolved_prob`)

Example JSONL row:

```json
{"market_id":"m-1","q10":0.22,"q50":0.39,"q90":0.63,"actual":0.58}
```

## Manual run

```bash
python -m pipelines.update_conformal_calibration \
  --input data/derived/calibration/conformal_history.jsonl \
  --state-path data/derived/calibration/conformal_state.json \
  --target-coverage 0.8 \
  --window-size 2000 \
  --min-samples 100
```

Dry-run (compute only, no write):

```bash
python -m pipelines.update_conformal_calibration --dry-run
```

## Cron example

Run every hour:

```cron
0 * * * * cd /path/to/Market-Calibration-Agent && /path/to/.venv/bin/python -m pipelines.update_conformal_calibration >> logs/conformal_calibrator.log 2>&1
```

## Inference behavior

`TSFMRunnerService` auto-loads `data/derived/calibration/conformal_state.json` on startup when present.
- If state exists and is valid: response includes `conformal_last_step`.
- If state is missing/invalid: service keeps current behavior (no conformal block, no failure).
