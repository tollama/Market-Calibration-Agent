# PRD2 Offline Evaluation (time split + event-holdout)

This closes PRD2 **P2-07** by providing a reproducible offline interval-quality evaluation pipeline.

## What it evaluates

Input table must include:
- base columns: `market_id,event_id,category,ts,actual`
- per-model quantiles with prefix form:
  - `<prefix>_q10`, `<prefix>_q50`, `<prefix>_q90` (required)
  - `<prefix>_q05`, `<prefix>_q95` (optional, used for 90% coverage/width)

Default model prefixes:
- `baseline`
- `tsfm_raw`
- `tsfm_conformal`

## Splits

- **Time split**: latest 20% rows as validation
- **Event-holdout**: hold out 20% events (deterministic by seed)

## Metrics

Primary interval metrics:
- `coverage_80`, `coverage_90`
- `mean_width_80`, `mean_width_90`
- `pinball_q10`, `pinball_q50`, `pinball_q90`, `pinball_mean`

Operational proxies:
- `breach_rate`
- `breach_followthrough_rate`
  - default meaningful move threshold: `abs move >= 0.03`
  - follow-through window: `6h`

## Run

```bash
PYTHONPATH=. python -m pipelines.evaluate_tsfm_offline \
  --input data/derived/tsfm/offline_eval_input.parquet \
  --output-dir artifacts/prd2_offline_eval

# equivalent wired entrypoint
PYTHONPATH=. python scripts/evaluate_tsfm_offline.py \
  --input data/derived/tsfm/offline_eval_input.parquet \
  --output-dir artifacts/prd2_offline_eval
```

Optional knobs:
- `--model-prefix` (repeatable)
- `--validation-ratio`
- `--holdout-ratio`
- `--seed`
- `--move-threshold`
- `--followthrough-hours`

## Artifacts

- `offline_eval_metrics.csv`
  - rows: `split x model`
- `offline_eval_summary.json`
  - run metadata and split sizes

These artifacts are intended for CI checks and release governance evidence.
