# Resolved Model Training

`pipelines/train_resolved_model.py` provides an end-to-end offline path:

1. load snapshot rows from `csv`, `parquet`, or `jsonl`
2. build a resolved training dataset by horizon
3. optionally enrich with local news and poll CSVs
4. fit a lightweight ridge-style linear baseline
5. write predictions, model JSON, optional backtest report, and a summary JSON

Example:

```bash
python -m pipelines.train_resolved_model \
  --input artifacts/snapshots.csv \
  --output-dir artifacts/resolved_model \
  --model-path artifacts/resolved_model/model.json \
  --dataset-path artifacts/resolved_model/dataset.csv \
  --report-dir artifacts/resolved_model/report
```

The model is intentionally simple. It is meant to establish an internal supervised baseline before introducing heavier model dependencies.
