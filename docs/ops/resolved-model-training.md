# Resolved Model Training

`pipelines/train_resolved_model.py` provides an end-to-end offline path:

1. load snapshot rows from `csv`, `parquet`, or `jsonl`
2. build a resolved training dataset by horizon
3. optionally enrich with local news and poll CSVs
4. fit either a direct ridge baseline or a residual model against `market_prob`
5. optionally add horizon interactions for a single-model multi-horizon fit
6. optionally run feature-group ablations
7. write predictions, model JSON, optional backtest report, optional ablation report, and a summary JSON

Example:

```bash
python -m pipelines.train_resolved_model \
  --input artifacts/snapshots.csv \
  --output-dir artifacts/resolved_model \
  --model-path artifacts/resolved_model/model.json \
  --dataset-path artifacts/resolved_model/dataset.csv \
  --report-dir artifacts/resolved_model/report \
  --target-mode residual \
  --run-ablation
```

Key options:

- `--target-mode direct|residual`
- `--disable-horizon-interactions`
- `--sample-weight-scheme none|segment_balanced`
- `--sample-weight-key <column>`
- `--run-ablation`
- `--ablation-report-path`

Current default workflow uses `target_mode=residual` with horizon interactions enabled in `run_training_workflow()`. The intent is to model where the market is wrong, not just re-learn the market level.

For mixed-platform resolved datasets, the real-data pack path now uses light
segment balancing against `canonical_category` to reduce domination by a single
platform/category block while still keeping a global model.

The current real-data pack path also supports routed offline training. The
active configuration uses a global weighted residual model plus segment models
for `crypto` vs `non_crypto`, routed by `canonical_category` with a global
fallback.
