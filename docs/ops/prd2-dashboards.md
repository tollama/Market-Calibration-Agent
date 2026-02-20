# PRD2 dashboards (TSFM observability)

## Files
- Dashboard JSON: `monitoring/grafana/prd2-observability-dashboard.json`
- Optional Grafana provisioning file: `monitoring/grafana/prd2-observability-dashboard.provider.yaml`

## Import

### Option A) UI import
1. Open Grafana → **Dashboards** → **New** → **Import**.
2. Upload `monitoring/grafana/prd2-observability-dashboard.json`.
3. Select your Prometheus datasource.
4. Save.

### Option B) File provisioning
1. Copy `monitoring/grafana/prd2-observability-dashboard.json` to a directory Grafana can read.
2. Place `monitoring/grafana/prd2-observability-dashboard.provider.yaml` under Grafana provisioning dashboards path (typically `/etc/grafana/provisioning/dashboards/`).
3. Ensure provider `options.path` points to the dashboard JSON directory.
4. Restart Grafana.

## Expected panels
1. **Request Latency (p50/p95/p99)**
   - `tsfm_request_latency_ms_bucket`
2. **Error Rate**
   - `tsfm_request_total{status=~"error|failed"} / tsfm_request_total`
3. **Fallback Rate by Reason**
   - `tsfm_fallback_total` grouped by `reason`
4. **Breaker-Open Rate**
   - `tsfm_breaker_open_total / tsfm_request_total`
5. **Cache Hit Rate**
   - `tsfm_cache_hit_total / tsfm_request_total`
6. **Top-N Cycle Time (p95 by market)**
   - `topk(10, histogram_quantile(... tsfm_cycle_time_seconds_bucket ... by market_id))`

## Notes
- Panels are static PromQL definitions only (no runtime code changes).
- If a panel shows **No data**, verify metric names/labels in your Prometheus scrape target.
