# PRD2 Offline Evaluation (time split + event-holdout)

This closes PRD2 **P2-07** by providing a reproducible offline interval-quality evaluation pipeline.

## What it evaluates

Input table must include:
- base columns: `market_id,event_id,category,ts,actual`
- optional market baseline columns: `market_prob` or `p_yes`
- optional segment columns: `liquidity_bucket`, `tte_bucket`, `horizon_hours`, `platform`
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

Point forecast metrics:
- `mse_q50`, `rmse_q50`, `mae_q50`
- `mean_actual`, `mean_forecast`, `mean_error`, `mean_abs_error`

Operational proxies:
- `breach_rate`
- `breach_followthrough_rate`
  - default meaningful move threshold: `abs move >= 0.03`
  - follow-through window: `6h`
- `selected`, `selection_rate`, `avg_abs_edge`, `avg_signed_edge`, `avg_pnl`, `hit_rate`

When `market_prob` or `p_yes` is present, the output also includes a `market` row
so models can be compared directly against raw market probability.

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
- `--edge-threshold`

## Artifacts

- `offline_eval_metrics.csv`
  - rows: `split x model`
- `offline_eval_segments.csv`
  - rows: `split x group_by x group_value x model`
- `offline_eval_summary.json`
  - run metadata, schema version, split sizes, segment fields, and artifact paths

These artifacts are intended for CI checks and release governance evidence.

## Benchmark interpretation guide

### Acceptance criteria (TSFM vs Baseline)

Before promoting TSFM to production, the offline eval must demonstrate that TSFM
adds value over both the raw market baseline and the EWMA baseline when those
rows are present. Compare `offline_eval_metrics.csv` rows for the same split:

| Metric | Acceptance condition | Rationale |
| --- | --- | --- |
| `mae_q50` | `tsfm_raw` <= `market` and <= `baseline` | Better median-path accuracy |
| `coverage_80` | `tsfm_conformal` within [0.75, 0.85] **and** closer to 0.80 than `baseline` | Conformal should hit target coverage |
| `mean_width_80` | `tsfm_conformal` width <= 1.1 x `baseline` width | Tighter or equal intervals for same coverage |
| `pinball_mean` | `tsfm_raw` pinball_mean < `baseline` pinball_mean | Better quantile accuracy |
| `avg_pnl` | `tsfm_raw` >= `market` and >= `baseline` | Forecast edges should be economically useful |
| `breach_followthrough_rate` | `tsfm_raw` >= `baseline` | Breaches should be informative, not noise |

### Go/No-Go decision matrix

| Time split pass | Event-holdout pass | Decision |
| --- | --- | --- |
| Yes | Yes | Promote to canary |
| Yes | No | Investigate event-specific failure modes before proceeding |
| No | Yes | Likely overfitting to recent regime; expand training window |
| No | No | Do not promote; baseline-only mode remains active |

### Current status

No benchmark results have been committed yet. To generate the first baseline
comparison:

```bash
# 1. Prepare eval input with both baseline and TSFM quantiles
PYTHONPATH=. python -m pipelines.evaluate_tsfm_offline \
  --input data/derived/tsfm/offline_eval_input.parquet \
  --output-dir artifacts/prd2_offline_eval \
  --model-prefix baseline \
  --model-prefix tsfm_raw \
  --model-prefix tsfm_conformal

# 2. Inspect results
cat artifacts/prd2_offline_eval/offline_eval_metrics.csv
cat artifacts/prd2_offline_eval/offline_eval_segments.csv
```

Once results are available, commit `artifacts/prd2_offline_eval/` to the repository
so reviewers can verify TSFM effectiveness without running the pipeline.
