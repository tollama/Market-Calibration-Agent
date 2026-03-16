# Market Calibration Agent Implementation Details

This document explains how the main modules are implemented and how runtime behavior is controlled.

## 1) Repository Layering

- `connectors/`: external data acquisition via a platform-agnostic abstraction layer (Polymarket Gamma REST/Subgraph/WS, Kalshi REST, Manifold REST).
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

## 2) Connector Abstraction Layer

All platform connectors implement the `MarketDataConnector` Protocol (`connectors/base.py`), which requires `fetch_markets()` and `fetch_events()` methods. Optional capability protocols (`MetricsConnector`, `RealtimeConnector`) are used for platforms that support metrics queries or realtime streaming.

- `connectors/factory.py` provides `create_connector()`, `create_metrics_connector()`, and `create_realtime_connector()` factory functions keyed by `Platform` enum.
- `connectors/normalizers.py` defines the `MarketNormalizer` Protocol for platform-specific field mapping to the canonical `MarketSnapshot` schema.
- Platform is configured in `configs/default.yaml` under the `platforms` section. Each platform has `enabled`, `connector`, `base_url`, auth env vars, and websocket settings.

## 3) Data Ingestion and Normalization

### Polymarket Gamma REST (`connectors/polymarket_gamma.py`)

- Async connector with:
  - retryable status handling (`408, 429, 500, 502, 503, 504`)
  - exponential backoff (+ optional jitter)
  - optional request-rate cap (`max_requests_per_second`)
  - cursor and/or offset pagination with repeated-token protection
- Data normalization:
  - recursive key conversion to snake_case
  - canonical `record_id` extraction (`<record_type>_id`, `id`, `condition_id`, `slug`)

### Polymarket Subgraph GraphQL (`connectors/polymarket_subgraph.py`)

- `GraphQLClient` wraps transport retries/backoff and GraphQL error handling.
- `SubgraphQueryRunner` paginates by `market_id`, accumulates partial failures, and returns normalized metric rows:
  - `market_id`, `event_id`, `metric`, `value`, `timestamp`, `source`.

### Polymarket Websocket Stream (`connectors/polymarket_ws.py`)

- Async stream with reconnect retries and backoff.
- Accepts dict/list/callable subscription payload.
- Tracks stream stats (`reconnects`, yielded count, skipped non-json frames).

### Kalshi REST (`connectors/kalshi.py`)

- Async connector with bearer-token auth (`api_key_id` from env vars).
- Cursor-based pagination using `cursor` field in API response.
- Same retry/backoff patterns as Gamma connector (retryable statuses: `408, 429, 500, 502, 503, 504`).
- Normalization via `connectors/kalshi_normalizer.py`:
  - `ticker` -> platform-prefixed `market_id` (`kalshi:{ticker}`)
  - `yes_bid`/`yes_ask` midpoint -> `p_yes`
  - `volume` -> `volume_24h`, `open_interest` -> `open_interest`
  - `close_time` delta -> `tte_seconds`

### Manifold Markets REST (`connectors/manifold.py`)

- Async connector with no auth required (public API).
- Before-cursor pagination using last item's `id` as the `before` parameter.
- Deduplication by `id` across pages via `seen_ids` set.
- `fetch_events()` returns `[]` (Manifold has no separate events concept).
- Normalization via `connectors/manifold_normalizer.py`:
  - `id` -> platform-prefixed `market_id` (`manifold:{id}`)
  - `probability` -> `p_yes` (binary markets)
  - Multi-outcome markets: each answer flattened into a separate row with `market_id = manifold:{id}:{answer_id}`
  - `totalLiquidity` -> `open_interest` proxy, `uniqueBettorCount` -> `num_traders_proxy`

### Generalized Platform Ingestion (`pipelines/ingest_platform_raw.py`)

- Platform-parameterized version of `ingest_gamma_raw` for non-Polymarket platforms.
- Writes to `raw/{platform}/dt=YYYY-MM-DD/{markets,events}.jsonl`.
- `pipelines/multi_platform_ingest.py` orchestrates ingestion across all enabled platforms in config.

## 4) Orchestration Pipeline

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

## 5) Registry and Contract Handling

- `registry/conflict_rules.py` canonicalizes market rows and enforces merge semantics:
  - `market_id` immutable key.
  - mismatch handling for `event_id`, `outcomes`, `enableOrderBook` via conflict records.
  - status precedence and tag merge rules.
- `registry/build_registry.py` adds:
  - slug ownership guard
  - slug history rows on slug change
  - conflict accumulation in deterministic order.

## 6) Market Normalization and Feature Computation

### Cross-platform normalization (`features/prediction_market_normalization.py`)

- `normalize_category_token(value)`: Standardizes category strings to lowercase with underscores.
- `infer_canonical_category(category, title, slug, platform)`: Maps platform-specific categories to canonical set via exact match table + keyword inference from title/slug/platform. Canonical set: `politics`, `crypto`, `macro`, `sports`, `science_health`, `technology`, `culture`, `business`, `weather`, `lifestyle`, `other`.
- `classify_market_structure(platform, title, slug, market_id)`: Detects market structure:
  - `combo_multi_leg`: Kalshi multi-clause combos (parlay, crosscategory, SGP tickers; multiple yes/no clauses or commas).
  - `player_prop`: Sports player prop patterns (e.g., "Player Name: 20+").
  - `standard_binary`: Default for normal binary markets.
- `augment_prediction_market_context(frame)`: Applies all normalization in one call, adding `canonical_category`, `market_structure`, `platform_category` (`{platform}:{canonical_category}`), and `is_standard_market` columns.

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

## 7) Alerting Logic

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

## 8) Resolved Model Training (`pipelines/train_resolved_model.py`)

### Segment routing

- `SegmentRoutingConfig` dataclass configures routing strategy, route key column, minimum segment rows, and gate parameters.
- Predefined strategies:
  - `crypto_vs_rest`: Segments crypto from all other categories.
  - `kalshi_vs_rest`: Segments by platform (Kalshi vs others).
  - Custom: Routes on any categorical column specified by `route_key`.
- `_segment_route_series()` returns a Series with segment labels for each row.

### Segmented resolved model

- `SegmentedResolvedModel` maintains a global `ResolvedLinearModel` (baseline) plus segment-specific models.
- `predict_frame()` generates predictions using the global model first, then routes each row to the appropriate segment model; keeps global as fallback.
- Full serialization via `to_payload()` / `from_payload()` preserving routing config and all segment models.

### Segment gating

- `_evaluate_segment_route_gate()` validates segments using walk-forward windows:
  - Measures weighted Brier score improvement per segment.
  - Activates only if: enough validation windows (`gate_min_windows`), average improvement exceeds `gate_min_improvement`, worst-case within `gate_worst_case_tolerance`.
- Gate metrics (activate, valid_windows, avg_improvement, worst_improvement) persisted in model payload.

### Segment-balanced sample weighting

- `_sample_weight_series()` computes per-row weights when `sample_weight_scheme="segment_balanced"`:
  - Segments by `sample_weight_key` column (default: `platform_category`).
  - Weight = `(median_count / segment_count) ^ sample_weight_power`, clipped to `[sample_weight_min, sample_weight_cap]`, normalized by mean.
- Applied in ridge solver, validation folds, and blend selection via `_weighted_brier_score()` / `_weighted_log_loss()`.

### Training features

- Numeric candidates include market prob, price action, volume, OI, TTE, template, news, poll, event context, and cross-platform features.
- Categorical candidates include `canonical_category`, `platform_category`, `market_structure`, `liquidity_bucket`, `tte_bucket`, `template_group`, `platform`.

## 9) TSFM Runner Service Internals

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

## 10) API and Derived Store Behavior

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

## 11) LLM-Specific Agent Implementation

- `llm/client.py` enforces deterministic sampling policy defaults (seed/temperature/top_p).
- Strict JSON parsing/validation in `llm/schemas.py` rejects missing/extra keys and invalid field types.
- `agents/question_quality_agent.py` retries up to 3 times on strict JSON violations.
- `agents/explain_agent.py` applies evidence-bound validation (`agents/explain_validator.py`) and line-level output policy.

## 12) Operational Scripts and Gates

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

