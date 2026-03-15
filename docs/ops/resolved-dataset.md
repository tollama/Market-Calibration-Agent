# Resolved Dataset Builder

`pipelines/build_resolved_training_dataset.py` builds supervised rows from historical market snapshots.

Each output row contains:

- one resolved binary label per market
- one or more deterministic `snapshot_ts` rows per requested horizon
- `resolution_ts`
- `horizon_hours`
- `market_prob` copied from `p_yes` when absent
- `sample_index`
- `snapshot_gap_minutes`
- `age_since_open_minutes`
- `tte_minutes`
- `tte_bucket`
- `platform`

Selection rule:

- for each market and horizon, choose rows with `ts <= resolution_ts - horizon`
- default `sample_mode=all_eligible` emits all eligible as-of rows in deterministic order
- `sample_mode=latest_only` preserves the old latest-snapshot behavior
- optional spacing and per-horizon caps can reduce row count without introducing randomness

Optional enrichment:

- `include_template_features=True` adds `market_template`, `template_group`, `template_confidence`, `template_entity_count`, `query_terms`, and `poll_mode`

Typical stage usage:

- source from `feature_frame` when available
- otherwise source from `cutoff_snapshots`
- result stored in `context.state["resolved_training_dataset"]`
