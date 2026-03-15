# Forecasting Baseline Artifact Pack

This repo now includes a deterministic reference artifact pack at:

- `artifacts/forecasting_baseline_pack/reference_fixture_v1`

The pack is generated from repo-local fixture data and is intended to make the
forecasting evaluation contract reproducible in-repo. It is not a substitute
for a production benchmark run on live resolved-market data.

## Contents

- `dataset_summary.json`
- `benchmark_summary.json`
- `promotion_decision.json`
- `inputs/offline_eval_input.csv`
- `inputs/backtest_rows.csv`
- `offline_eval/`
- `backtest_report/`

## Generation

```bash
python3 scripts/generate_forecasting_baseline_pack.py
```

To write to a different directory:

```bash
python3 scripts/generate_forecasting_baseline_pack.py \
  --output-dir artifacts/forecasting_baseline_pack/my_run
```

## Promotion Gate

The committed pack includes `backtest_report/decision_summary.csv`. To evaluate
that file directly:

```bash
python3 scripts/evaluate_forecasting_promotion_gate.py \
  --input artifacts/forecasting_baseline_pack/reference_fixture_v1/backtest_report/decision_summary.csv \
  --output-json artifacts/forecasting_baseline_pack/reference_fixture_v1/promotion_decision.json
```

Exit codes:

- `0`: at least one model variant passed the promotion gate
- `2`: no variant passed

## Expected Use

- Use this pack to validate schema stability for offline eval, backtest
  reporting, and promotion-gate automation.
- Replace or supplement it with a real resolved-market benchmark pack when
  offline research data is available locally.
