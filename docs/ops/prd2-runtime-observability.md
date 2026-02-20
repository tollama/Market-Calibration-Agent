# PRD2 runtime observability (P2-09)

This doc closes P2-09 by wiring runtime metric emission in the TSFM service path and exposing scrape output via API.

## What is now emitted in service path

From `TSFMRunnerService.forecast()` on every request:

- `tsfm_request_total{rollout_stage,status}`
- `tsfm_request_latency_ms_bucket{rollout_stage,le}` (+ `_sum`, `_count`)
- `tsfm_cycle_time_seconds_bucket{market_id,le}` (+ `_sum`, `_count`)
- `tsfm_cache_hit_total{rollout_stage}`
- `tsfm_fallback_total{rollout_stage,reason}`
- `tsfm_breaker_open_total{rollout_stage}`
- `tsfm_quantile_crossing_total{rollout_stage}`
- `tsfm_invalid_output_total{rollout_stage}`
- `tsfm_interval_width{rollout_stage,bucket}`
- `tsfm_target_coverage{rollout_stage,bucket}`

## Scrape endpoint

- API endpoint: `GET /metrics`
- Content type: Prometheus text exposition
- Source: in-memory emitter in service instance

## Smoke validation

```bash
python3 scripts/prd2_runtime_metrics_smoke.py
```

Expected:
- `METRICS_SMOKE_PASS`
- required tokens listed as `found=...`

## Test coverage

- `tests/unit/test_tsfm_runtime_observability.py`
- `tests/unit/test_api_metrics_endpoint.py`

These verify emitter wiring and `/metrics` exposure.
