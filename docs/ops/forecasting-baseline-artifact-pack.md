# Forecasting Baseline Artifact Pack

This repo now includes a deterministic reference artifact pack at:

- `artifacts/forecasting_baseline_pack/reference_fixture_v1`

It also includes a real-data discovery path at:

- `artifacts/forecasting_baseline_pack/real_data_v1`

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

To generate a pack from locally available resolved-market data:

```bash
python3 scripts/generate_real_data_forecasting_pack.py
```

To point the generator at a specific file:

```bash
python3 scripts/generate_real_data_forecasting_pack.py \
  --input /absolute/path/to/resolved_dataset.csv
```

The real-data generator now drops synthetic benchmark noise before training and
evaluation, specifically rows classified as `category=test` and titles such as
`Daily market` or `Test, do not trade`.

If local resolved inputs are not present, the script writes a blocked pack with:

- `status.json`
- `discovery_manifest.json`
- `README.md`

Input onboarding and accepted schemas are documented in:

- `docs/ops/resolved-input-onboarding.md`

The repo also includes a bootstrap helper for Manifold:

```bash
python3 scripts/bootstrap_manifold_resolved_dataset.py
```

For a broader local bootstrap that uses all implemented market-data connectors,
use:

```bash
python3 scripts/bootstrap_prediction_market_resolved_dataset.py
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
- Use `scripts/generate_real_data_forecasting_pack.py` as the default path for
  that replacement. The current workspace run is recorded at
  `artifacts/forecasting_baseline_pack/real_data_v1/status.json`.
