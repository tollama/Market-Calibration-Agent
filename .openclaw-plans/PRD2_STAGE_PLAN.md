# PRD2 Stage Implementation Plan — TSFM Runner (via tollama)

## Scope interpreted
Read and aligned with:
- `PRD2 — TSFM Runner (via tollama).md`
- `PRD1 - Polymarket Market Calibration Agent.md` (I-08/I-09/I-10/I-15 dependencies)
- `README.md`
- Existing implementation baseline (`runners/*`, `calibration/*`, `api/*`, `pipelines/*`, `configs/*`)
- tollama upstream README (runtime/API capabilities, `/api/forecast` and fallback `/v1/forecast` patterns)

This plan is **planning-only** (no code changes).

---

## Global defaults (deterministic choices)

These defaults are used unless explicitly overridden:

- **Primary cadence**: `freq=5m`
- **Input length**: `input_len_steps=288` (24h @ 5m)
- **Forecast horizon**: `horizon_steps=12` (1h @ 5m)
- **Quantiles**: `[0.1, 0.5, 0.9]`
- **Transform**: `logit`, `eps=1e-6`
- **y definition**: `mid` if bid/ask present, else `last_trade` if age `<=15m`, else ffill
- **Missingness rule**: forward-fill allowed up to `max_gap_minutes=60`; above this => TSFM disabled, baseline-only
- **Tollama timeout/retry**: `timeout_s=2.0`, `retry_count=1`, `retry_backoff_ms=200`, `retry_jitter_ms=100`
- **Circuit breaker**: open after `5` consecutive tollama failures, cool-down `120s`
- **Fallback baseline priority**: `EWMA -> KALMAN -> ROLLING_QUANTILE` (first valid wins)
- **Illiquidity baseline-only threshold**: `liquidity_bucket=LOW` OR `volume_24h < 5000`
- **Interval sanity guards**: `min_width=0.02`, `max_width=0.60`
- **Conformal**: enabled, rolling window `14d`, target coverage `0.9`, minimum calibration samples `500`
- **Top-N inference selection**: `N=200` per cycle; score = `0.6*z(volume_24h)+0.4*z(open_interest)`
- **Cache TTL**: `60s` for identical forecast requests
- **SLO targets**: p95 per-request `<=300ms`; top-N batch cycle `<=60s`; baseline fallback `<=50ms`

---

## Stage 1 — Contract, config, and schema extension

**Objective**
Define a stable internal TSFM forecast contract and config surface that isolates tollama API evolution.

**Files to create/modify**
- **Create**: `docs/prd2-defaults.md`
- **Create**: `schemas/tsfm.py` (request/response/meta models)
- **Modify**: `configs/default.yaml` (tsfm, fallback, conformal, selection, cache sections)
- **Modify**: `configs/models.yaml` (active TSFM model profiles, production-safe flags)
- **Modify**: `schemas/contracts.py` (export/registration of TSFM contract if used centrally)

**Acceptance checks**
- Config loads with strict validation and all new keys documented.
- `POST /tsfm/forecast` payload/response schema represented in pydantic models.
- Defaults match PRD2 and are centrally discoverable.

**Default values chosen in this stage**
- `model.provider=tollama`
- `model_name=chronos2` (default)
- `model_version=auto`
- `quantiles=[0.1,0.5,0.9]`, `freq=5m`, `horizon_steps=12`

---

## Stage 2 — Tollama adapter (runtime boundary)

**Objective**
Implement a thin resilient adapter converting internal TSFM contract <-> tollama API.

**Files to create/modify**
- **Create**: `runners/tollama_adapter.py`
- **Create**: `runners/tollama_client.py` (HTTP client with retry/timeout/circuit breaker)
- **Modify**: `runners/tsfm_base.py` (if needed to add adapter-friendly metadata fields)
- **Create**: `tests/runners/test_tollama_adapter.py`
- **Create**: `tests/runners/test_tollama_client.py`

**Acceptance checks**
- Adapter handles success path and normalizes quantile output to internal shape.
- Timeout/error/invalid-response paths are mapped to typed fallback reasons.
- Supports tollama endpoint preference order: `/api/forecast` then `/v1/forecast` on 404.

**Default values chosen in this stage**
- `base_url=http://127.0.0.1:11435`
- `auth_mode=bearer_optional`
- request header `x-request-id` required for traceability

---

## Stage 3 — TSFM runner service endpoint

**Objective**
Expose internal service API `POST /tsfm/forecast` and wire request validation + runner orchestration.

**Files to create/modify**
- **Modify**: `api/app.py` (new endpoint)
- **Create**: `api/tsfm_dependencies.py` (adapter + config injection)
- **Modify**: `api/schemas.py` or use new `schemas/tsfm.py`
- **Create**: `tests/api/test_tsfm_forecast_endpoint.py`

**Acceptance checks**
- Valid request returns q10/q50/q90 arrays for requested horizon.
- Response includes required meta: runtime/model/version/latency/input_len/transform/fallback_used/warnings.
- Invalid inputs (bad quantiles, horizon<=0, freq mismatch) return 422 with clear error.

**Default values chosen in this stage**
- If quantiles omitted: `[0.1,0.5,0.9]`
- If transform omitted: `{space: logit, eps: 1e-6}`
- Max request input length accepted: `2000` steps (hard cap)

---

## Stage 4 — Baseline fallback and post-processing safety

**Objective**
Guarantee robust output under runtime/data issues and enforce interval safety invariants.

**Files to create/modify**
- **Modify**: `runners/baselines.py` (multi-step quantile array compatibility if needed)
- **Create**: `runners/fallback_policy.py`
- **Create**: `runners/postprocess.py` (bounds, monotonic fix, width guards)
- **Create**: `tests/runners/test_fallback_policy.py`
- **Create**: `tests/runners/test_postprocess.py`

**Acceptance checks**
- Any tollama failure yields baseline output with `fallback_used=true` and reason code.
- All outputs clipped to `[0,1]`.
- Quantile crossing fixed per timestep; crossing metric increments.
- Width below/above limits adjusted or flagged deterministically.

**Default values chosen in this stage**
- Width guard: `min_width=0.02`, `max_width=0.60`
- Baseline choice precedence: `EWMA`, then `KALMAN`, then `ROLLING_QUANTILE`

---

## Stage 5 — Conformal calibration integration (rolling)

**Objective**
Integrate rolling conformal adjustment into serving flow while storing raw + adjusted bands.

**Files to create/modify**
- **Modify**: `calibration/conformal.py` (rolling window utility + per-horizon adjustments)
- **Create**: `calibration/conformal_store.py` (window artifacts and parameters)
- **Modify**: `pipelines/daily_job.py` (scheduled calibration refresh)
- **Create**: `tests/calibration/test_conformal_rolling.py`

**Acceptance checks**
- Raw and conformal-adjusted outputs are both persisted/returnable.
- Calibration parameters are versioned by as-of date and segment key.
- Validation report shows target coverage reached within tolerance.

**Default values chosen in this stage**
- `rolling_window_days=14`
- `target_coverage=0.9`
- coverage tolerance for AC: `±0.03`
- segment keys enabled: `liquidity_bucket`, `tte_bucket`, `category`

---

## Stage 6 — Offline evaluation pipeline (interval-first)

**Objective**
Operationalize offline evaluation for baseline vs TSFM using time split + event holdout.

**Files to create/modify**
- **Create**: `pipelines/eval_tsfm.py`
- **Create**: `reports/tsfm_eval_summary.py`
- **Create**: `docs/tsfm-eval.md`
- **Create**: `tests/pipelines/test_eval_tsfm.py`

**Acceptance checks**
- Produces interval metrics: coverage@80/90, width, pinball, optional winkler.
- Produces operational proxies: breach rate and follow-through rate.
- Compares TSFM/raw, TSFM/conformal, baseline under same splits.

**Default values chosen in this stage**
- Time split: latest `20%` as validation
- Event-holdout: hold out `20%` events stratified by category
- Meaningful move threshold for follow-through: absolute move `>=0.03` within `6h`

---

## Stage 7 — Observability, SLO enforcement, and deployment guardrails

**Objective**
Ship production-readiness controls (metrics, logs, health, licensing, circuit fallback mode).

**Files to create/modify**
- **Create**: `monitoring/metrics_tsfm.py` (or integrate existing metrics module)
- **Modify**: `configs/logging.yaml` (structured fields for TSFM)
- **Modify**: `configs/models.yaml` (license tags and prod eligibility)
- **Create**: `tests/config/test_model_license_guardrail.py`
- **Create**: `docs/tsfm-ops-runbook.md`

**Acceptance checks**
- Metrics emitted: latency/error/fallback/crossing/coverage/interval-width/breach rates.
- Structured logs include market_id/as_of/model/version/input_len/missingness/warnings.
- Prod config rejects `research_only` models in CI.
- Health degradation triggers baseline-only mode.

**Default values chosen in this stage**
- health probe interval: `30s`
- baseline-only auto-switch when fallback_rate `>0.5` for `5m`
- alert thresholds: p95 latency `>300ms` or error_rate `>5%` for `10m`

---

## Stage 8 — Rollout and alert-engine integration

**Objective**
Integrate TSFM bands into alert Gate1 safely with phased rollout.

**Files to create/modify**
- **Modify**: `agents/alert_agent.py` (consume TSFM/conformal band source with fallback tags)
- **Modify**: `pipelines/build_alert_feed.py` (source selection and metadata propagation)
- **Modify**: `configs/alerts.yaml` (band source and breach thresholds)
- **Create**: `docs/tsfm-rollout-plan.md`
- **Create**: `tests/agents/test_alert_agent_tsfm_gate1.py`

**Acceptance checks**
- Gate1 breach uses conformal-adjusted band by default; raw/baseline switchable.
- Alert payload includes `band_source` and `fallback_used` evidence.
- Can run canary rollout with percentage-based market subset and rollback toggle.

**Default values chosen in this stage**
- rollout phases: `shadow(100%) -> canary(10%) -> ramp(50%) -> full(100%)`
- default Gate1 band source: `tsfm_conformal`
- automatic rollback if canary breach precision drops by `>15%` vs baseline over `3d`

---

## Completion definition (overall)

PRD2 is considered done when:
1. `/tsfm/forecast` is stable with tollama + fallback in production-like load.
2. Interval safety invariants hold (bounded + monotonic quantiles).
3. Conformal-adjusted coverage reaches target (0.9 ± 0.03) on validation.
4. SLOs and observability are live with actionable alerts.
5. Alert Gate1 can consume TSFM bands with controlled rollout + rollback.
