# Backtest Reporting

`pipelines/generate_backtest_report.py` adds a fixed offline report template for resolved-market evaluation.

Current outputs:

- `overall_summary.csv`
- `group_metrics.csv`
- `edge_bucket_metrics.csv`
- `predictions.csv`
- `walk_forward_overall_summary.csv`
- `walk_forward_group_metrics.csv`
- `walk_forward_fold_summary.csv`
- `walk_forward_worst_fold_summary.csv`
- `walk_forward_edge_bucket_metrics.csv`
- `walk_forward_predictions.csv`
- `event_holdout_overall_summary.csv`
- `event_holdout_group_metrics.csv`
- `event_holdout_edge_bucket_metrics.csv`
- `event_holdout_predictions.csv`
- `decision_summary.csv`
- `summary.md`

Walk-forward behavior:

- expanding train / rolling test
- label-availability cutoff via `resolution_ts`
- optional embargo window in hours

Event-holdout behavior:

- deterministic event-level holdout by seed when `event_id` is present
- report is still written with empty artifacts when holdout is unavailable or too small

Decision summary behavior:

- compares each model variant against the benchmark variant, default `market`
- checks overall, walk-forward, and event-holdout pass status
- emits `go`, `conditional_go`, `no_go`, or `reference`

Supported prediction variants default to any of:

- `p_yes` as `market`
- `pred` as `primary`
- `baseline_pred` as `baseline`
- `recalibrated_pred` as `recalibrated`

The report is intentionally data-first. It evaluates existing prediction columns without introducing a new model dependency.
