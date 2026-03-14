# Resolved Dataset Builder

`pipelines/build_resolved_training_dataset.py` builds supervised rows from historical market snapshots.

Each output row contains:

- one resolved binary label per market
- one selected `snapshot_ts` per requested horizon
- `resolution_ts`
- `horizon_hours`
- `market_prob` copied from `p_yes` when absent

Selection rule:

- for each market and horizon, choose the latest snapshot with `ts <= resolution_ts - horizon`

Optional enrichment:

- `include_template_features=True` adds `market_template`, `template_group`, `template_confidence`, `template_entity_count`, `query_terms`, and `poll_mode`

Typical stage usage:

- source from `feature_frame` when available
- otherwise source from `cutoff_snapshots`
- result stored in `context.state["resolved_training_dataset"]`
