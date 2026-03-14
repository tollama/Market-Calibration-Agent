# Live Scanner

`pipelines/scan_live_markets.py` is a file-driven scanner for snapshot-like market rows.

Inputs:

- trained model JSON from `pipelines/train_resolved_model.py`
- live rows with `p_yes` or `market_prob`
- optional feature columns such as `returns`, `vol`, `volume_velocity`, `oi_change`, `tte_seconds`

Outputs:

- `pred`
- `baseline_pred`
- `recalibrated_pred`
- `edge`
- `signal`
- `ranking_score`

Example:

```bash
python -m pipelines.scan_live_markets \
  --input artifacts/live_rows.csv \
  --model-path artifacts/resolved_model/model.json \
  --output artifacts/live_scan.csv
```
