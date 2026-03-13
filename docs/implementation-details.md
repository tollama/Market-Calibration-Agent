# Market Calibration Agent Implementation Details

This document explains how the main modules are implemented and how runtime behavior is controlled.

## 1) Repository Layering

- `connectors/`: external data acquisition (Gamma REST, Subgraph GraphQL, WebSocket stream).
- `registry/`: canonical market registry build/merge/conflict logic.
- `pipelines/`: orchestration and transformation stages.
- `features/`: deterministic feature engineering.
- `calibration/`: metric, interval, conformal, drift, trust-score computations.
- `agents/`: rule-based alerting + LLM-based quality/explain helpers.
- `runners/`: TSFM service, adapter, baselines, observability.
- `api/`: read-only API + TSFM forecast endpoint.
- `storage/`: partitioned JSONL/parquet readers/writers.
- `reports/`: markdown postmortem rendering.
- `demo/`: Streamlit live demo app.

## 2) Data Ingestion and Normalization

### Gamma REST (`connectors/polymarket_gamma.py`)

- Async connector with:
  - retryable status handling (`408, 429, 500, 502, 503, 504`)
  - exponential backoff (+ optional jitter)
  - optional request-rate cap (`max_requests_per_second`)
  - cursor and/or offset pagination with repeated-token protection
- Data normalization:
  - recursive key conversion to snake_case
  - canonical `record_id` extraction (`<record_type>_id`, `id`, `condition_id`, `slug`)

### Subgraph GraphQL (`connectors/polymarket_subgraph.py`)

- `GraphQLClient` wraps transport retries/backoff and GraphQL error handling.
- `SubgraphQueryRunner` paginates by `market_id`, accumulates partial failures, and returns normalized metric rows:
  - `market_id`, `event_id`, `metric`, `value`, `timestamp`, `source`.

### Websocket Stream (`connectors/polymarket_ws.py`)

- Async stream with reconnect retries and backoff.
- Accepts dict/list/callable subscription payload.
- Tracks stream stats (`reconnects`, yielded count, skipped non-json frames).

## 3) Orchestration Pipeline

### Daily orchestrator (`pipelines/daily_job.py`)

- Fixed stage order:
  - `discover`, `ingest`, `normalize`, `snapshots`, `cutoff`, `features`, `metrics`, `publish`.
- Runtime controls:
  - checkpoint save/load (`pipelines/common.py`)
  - resume-from-checkpoint for successful stages
  - per-stage retry budget
  - continue/stop behavior on failure (`continue_on_stage_failure`)
  - no-op/recoverable stage handling

### Important stage behavior

- `ingest`: reads hook output or pre-populated state (`raw_records`, `events`, `market_ids`).
- `snapshots`: optionally enriches snapshots with registry metadata (`pipelines/registry_linker.py`).
- `cutoff`: selects nearest-before cutoff snapshots (`pipelines/build_cutoff_snapshots.py`).
- `features`: builds feature frame via `features/build_features.py`.
- `metrics`:
  - loads trust/alert policies from YAML
  - computes scoreboard rows + summary metrics
  - computes alert feed rows with trust gating support
- `publish`: prepares published records and writes postmortem markdown batch.

## 4) Registry and Contract Handling

- `registry/conflict_rules.py` canonicalizes market rows and enforces merge semantics:
  - `market_id` immutable key.
  - mismatch handling for `event_id`, `outcomes`, `enableOrderBook` via conflict records.
  - status precedence and tag merge rules.
- `registry/build_registry.py` adds:
  - slug ownership guard
  - slug history rows on slug change
  - conflict accumulation in deterministic order.

## 5) Feature, Calibration, and Trust Computation

### Feature engineering (`features/build_features.py`)

- Deterministic sorted computation per market/timestamp.
- Computes:
  - `returns`
  - rolling `vol`
  - `volume_velocity`
  - `oi_change`
  - `tte_seconds` (from `tte_seconds` or end-time columns)
  - `liquidity_bucket` (`base_liquidity=max(volume_24h,open_interest)`에 threshold 적용; 기본 `10k/100k`, `configs/default.yaml` 또는 `MCA_LIQUIDITY_LOW/HIGH`로 조정 가능)
  - `liquidity_bucket_id` (`LOW/MID/HIGH` → `0/1/2`)

### Calibration metrics (`calibration/metrics.py`)

- Probability and label validation is strict (finite, range checks, binary labels).
- Standard metrics:
  - Brier
  - Log Loss
  - ECE
  - optional slope/intercept extension
- Segment metric utility supports category/liquidity/TTE breakdowns.

### Trust score (`calibration/trust_score.py`)

- Inputs normalized into `[0,1]`.
- Weighted score on 0-100 scale.
- `manipulation_suspect` is inverted in the final aggregation.
- Weights are normalized and can be injected from `configs/default.yaml`.

## 6) Alerting Logic

### Rule engine (`agents/alert_agent.py`)

- Base reason codes:
  - `BAND_BREACH`
  - `LOW_OI_CONFIRMATION`
  - `LOW_AMBIGUITY`
  - `VOLUME_SPIKE`
- Severity rule:
  - `HIGH/MED` only when band breach + structural gate + low ambiguity hold.
  - `HIGH` requires both low-OI and volume-spike confirmation.
  - otherwise `FYI`.

### Feed builder (`pipelines/build_alert_feed.py`)

- Requires row keys: `market_id`, `ts`, `p_yes`, `q10`, `q90`.
- Applies optional `min_trust_score` gate.
- Converts blocked strict-gate `HIGH/MED` into `FYI` (and excludes FYI by default unless requested).
- Emits deterministic `alert_id` via SHA-256 hash of canonical alert payload.

### Top-N selective orchestration (`pipelines/alert_topn_orchestration.py`)

- Ranks candidates by:
  1. watchlist priority
  2. explicit alert-candidate flag
  3. composite importance score
- Only top-N selected markets request TSFM forecasts.
- Produces explicit per-market decisions (`EMIT` vs `SUPPRESS` with reason codes).

## 7) TSFM Runner Service Internals

### Request lifecycle (`runners/tsfm_service.py`)

1. Normalize payload containers (`y`, `quantiles`, feature dicts).
2. Validate numeric quality, sizes, frequency, timestamp alignment.
3. Build cache key from full request fingerprint.
4. Serve fresh cache hit when available.
5. Decide tollama eligibility (enough points, liquidity gate, max-gap check, breaker/degradation status).
6. Try tollama adapter call.
7. On runtime error:
   - use stale cache if available (`stale_if_error`)
   - else switch to baseline fallback.
8. Post-process quantile paths:
   - inverse-transform (if needed)
   - clip to `[0,1]`
   - enforce non-crossing
   - enforce min/max interval width
9. Append optional conformal adjustment for the final step.
10. Emit metrics and cache response.

### Resilience mechanisms

- Cache:
  - TTL + stale-if-error windows
  - bounded size with eviction when full.
- Circuit breaker:
  - states: `closed`, `open`, `half-open`
  - opens on failure-rate policy over rolling window
  - half-open probe policy with close criteria.
- Degradation:
  - states: `normal`, `degraded`, `baseline-only`
  - transitions by rolling failure rates
  - baseline-only can periodically probe tollama by configured cadence.

### Adapter (`runners/tollama_adapter.py`)

- Supports two payload styles (legacy and Ollama-like endpoints).
- Handles retryable HTTP/network errors with backoff+jitter.
- Extracts quantile payload from known response shapes and returns normalized `dict[float, list[float]]`.

## 8) API and Derived Store Behavior

### API endpoints (`api/app.py`)

- Read-only data endpoints:
  - `/scoreboard`
  - `/alerts`
  - `/markets`
  - `/markets/{market_id}`
  - `/markets/{market_id}/metrics`
  - `/postmortem/{market_id}`
- Forecast/ops endpoints:
  - `POST /tsfm/forecast`
  - `GET /metrics` and `/tsfm/metrics`
  - `POST /markets/{market_id}/comparison` (baseline vs tollama comparison wrapper)

### Inbound forecast guard

- Reads policy from `configs/default.yaml` (`api.tsfm_forecast.*`):
  - auth required flag
  - token env var name
  - per-minute rate limit.
- Rejects placeholder/missing tokens when auth is enabled.
- Uses token identity (or client IP) for rate-limit windows.

### Derived artifact loading (`api/dependencies.py`)

- Fault-tolerant JSON/JSONL reader with malformed-line accounting.
- Scoreboard/alert loaders support both single-file and partition scans.
- Alert cache includes source-signature invalidation and deduping strategy.
- Postmortem loader prefers dated files and falls back to plain `<market_id>.md`.

## 9) LLM-Specific Agent Implementation

- `llm/client.py` enforces deterministic sampling policy defaults (seed/temperature/top_p).
- Strict JSON parsing/validation in `llm/schemas.py` rejects missing/extra keys and invalid field types.
- `agents/question_quality_agent.py` retries up to 3 times on strict JSON violations.
- `agents/explain_agent.py` applies evidence-bound validation (`agents/explain_validator.py`) and line-level output policy.

## 10) Operational Scripts and Gates

- Release and hardening scripts:
  - `scripts/prd2_verify_all.sh`
  - `scripts/prd2_release_audit.py`
  - `scripts/rollout_hardening_gate.sh`
- Offline evaluation and performance:
  - `pipelines/evaluate_tsfm_offline.py`
  - `pipelines/bench_tsfm_runner_perf.py`
- Demo runtime orchestration:
  - `scripts/run_live_demo.sh`
  - `scripts/stop_live_demo.sh`

