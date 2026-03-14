# Backtest Reporting

`pipelines/generate_backtest_report.py` adds a fixed offline report template for resolved-market evaluation.

Current outputs:

- `overall_summary.csv`
- `group_metrics.csv`
- `predictions.csv`
- `walk_forward_overall_summary.csv`
- `walk_forward_group_metrics.csv`
- `walk_forward_fold_summary.csv`
- `walk_forward_predictions.csv`
- `summary.md`

Walk-forward behavior:

- expanding train / rolling test
- label-availability cutoff via `resolution_ts`
- optional embargo window in hours

Supported prediction variants default to any of:

- `p_yes` as `market`
- `pred` as `primary`
- `baseline_pred` as `baseline`
- `recalibrated_pred` as `recalibrated`

The report is intentionally data-first. It evaluates existing prediction columns without introducing a new model dependency.
