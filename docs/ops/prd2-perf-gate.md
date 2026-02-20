# PRD2 Performance Regression CI Gate

This CI gate runs a deterministic TSFM runner benchmark and fails on regression.

- Benchmark entrypoint: `pipelines/bench_tsfm_runner_perf.py`
- CI workflow: `.github/workflows/prd2-perf-gate.yml`
- Thresholds:
  - `latency_p95_ms <= 300`
  - `elapsed_s <= 60`

## When it runs

- `pull_request`
- `push`
- `workflow_dispatch`

## Local run

### 1) Run benchmark and capture output

```bash
PYTHONPATH=. python3 pipelines/bench_tsfm_runner_perf.py \
  --requests 200 \
  --unique 20 \
  --adapter-latency-ms 15 \
  --budget-p95-ms 300 \
  --budget-cycle-s 60 \
  | tee prd2-bench.log
```

### 2) Parse + validate gate result

```bash
python3 scripts/validate_prd2_perf_bench.py \
  --input prd2-bench.log \
  --output prd2-bench-result.json \
  --p95-threshold-ms 300 \
  --cycle-threshold-s 60
```

A non-zero exit from the helper means regression gate failure.

## JSON output produced by helper

`prd2-bench-result.json` includes:

- `thresholds` (configured limits)
- `metrics` (parsed benchmark values)
- `ok` (boolean)
- `failures` (list of failed checks)

Example keys under `metrics`:
- `requests`
- `elapsed_s`
- `throughput_rps`
- `latency_p50_ms`
- `latency_p95_ms`
- `cache_hit_rate`
- `fallback_rate`
