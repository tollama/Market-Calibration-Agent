# PRD2 IMPLEMENTATION REPORT — TSFM Runner (via tollama)

## Scope completed
Implemented PRD2 sequentially (Stage 1..n), then extended with explicit runtime/throughput hardening.

> Support docs were later discovered and integrated:
> - `.openclaw-plans/PRD2_PERF_BLUEPRINT.md`
> - `.openclaw-plans/PRD2_LOADTEST_SPEC.md`
> - `.openclaw-plans/PRD2_TOLLAMA_HARDENING.md`
> 
> Integrated updates:
> - tightened adapter timeout to `1.2s`
> - connection pool defaults to `200/50`
> - exponential backoff + jitter retry behavior
> - circuit breaker profile aligned to `5 failures / 120s cooldown`
> - runtime config schema expanded for queue/concurrency/deadline budgets

## Stage-by-stage implementation
1. **Stage 1: API Contract**
   - Added TSFM request/response schemas and `/tsfm/forecast` endpoint.
2. **Stage 2: Tollama Adapter**
   - Added `TollamaAdapter` with timeout, retry(+jitter), normalized parsing.
3. **Stage 3: Runner Service**
   - Added `TSFMRunnerService` orchestration for preprocessing, inference, standardized output.
4. **Stage 4: Safety/Post-processing**
   - Added clipping to [0,1], quantile crossing fix, interval sanity width enforcement.
5. **Stage 5: Conformal hook**
   - Integrated optional conformal adjustment output (`conformal_last_step`) via existing calibration module.
6. **Stage 6: Baseline fallback**
   - Added fallback triggers and baseline generation (EWMA) with explicit metadata/warnings.
7. **Stage 7: Licensing guardrails**
   - Added model registry config with `license_tag` and test to prevent research-only models in prod allowlist.
8. **Stage 8: Functional tests/verification**
   - Added unit/API tests covering main path, fallback, post-processing safety, and license policy.
9. **Stage 9: Performance hardening + perf smoke benchmark**
   - Added request TTL cache, circuit breaker, pooled HTTP connections.
   - Added reproducible benchmark with built-in SLO budget checks.

## Performance-focused decisions (dedicated hardening pass)
- **Service cache (TTL 60s)**
  - Decision: request-hash cache in TSFM runner.
  - Why: top-N alert cycles commonly repeat near-identical calls within 1 minute.
  - Effect: cuts repeated tollama calls; lowers p95 and cycle time.
- **Circuit breaker hardened (5 failures, 120s cooldown)**
  - Decision: open breaker after 5 consecutive tollama failures; force baseline fallback during cooldown.
  - Why: deterministic degradation under prolonged runtime faults without hot-loop retries.
- **HTTP pooling tuned (200 max, 50 keepalive)**
  - Decision: persistent `httpx.Client` with explicit pool sizing aligned to PRD2 perf blueprint.
  - Why: better connection reuse with lower socket pressure.
- **Deterministic fallback protections**
  - Strict validation of adapter payload shape before acceptance:
    - quantile set must match expected set,
    - per-quantile horizon length must match request,
    - all values must be finite.
  - On violations, service deterministically falls back to baseline and records explicit reason (`meta.fallback_reason`).
- **Interval guardrail tightened**
  - `max_interval_width` reduced from `0.9` to `0.6` to avoid unusably wide degraded intervals.
- **Runtime perf config file added**
  - `configs/tsfm_runtime.yaml` with SLO/perf knobs for repeatable operations.

## Files changed
- `runners/tollama_adapter.py` (new, then hardened)
- `runners/tsfm_service.py` (new, then hardened)
- `api/schemas.py` (updated)
- `api/app.py` (updated)
- `configs/tsfm_models.yaml` (new)
- `configs/tsfm_runtime.yaml` (new)
- `tests/unit/test_tsfm_runner_service.py` (new, then extended)
- `tests/unit/test_api_tsfm_forecast.py` (new)
- `tests/unit/test_tsfm_model_license_guard.py` (new)
- `tests/integration/test_tollama_live_integration.py` (new)
- `.github/workflows/ci.yml` (new)
- `docs/ops/live-tollama-integration-runbook.md` (new)
- `pipelines/bench_tsfm_runner_perf.py` (new)
- `docs/prd2-implementation-status.md` (new, then updated)
- `README.md` (updated link)
- `.openclaw-plans/PRD2_IMPLEMENTATION_REPORT.md` (this file)

## Defaults chosen and rationale
- `freq=5m`, `horizon_steps=12`, `input_len_steps=288`: aligns with alert cadence + 24h context.
- `quantiles=[0.1,0.5,0.9]`: standard interval contract for gate/breach flow.
- `transform=logit`, `eps=1e-6`: stable bounded-probability modeling.
- `tollama timeout=1.2s`, `retry=1` (+exp backoff/jitter): better tail-latency control from hardening guide.
- `min_points_for_tsfm=32`: prevents unstable short-context inference.
- `baseline_method=EWMA`: low-latency robust fallback.
- `baseline_only_liquidity=low`: conservative operation for illiquid markets.
- `min_interval_width=0.02`, `max_interval_width=0.6`: prevents pathological overconfident or unusably wide bands.
- **Perf defaults**:
  - `cache_ttl_s=60`
  - `circuit_breaker_failures=5`
  - `circuit_breaker_cooldown_s=120`
  - `max_connections=200`
  - `max_keepalive_connections=50`

## Verification executed
### 1) Unit/API checks
```bash
python3 -m pytest tests/unit/test_tsfm_runner_service.py tests/unit/test_tsfm_perf_smoke.py tests/unit/test_api_tsfm_forecast.py tests/unit/test_tsfm_model_license_guard.py tests/unit/test_baseline_bands.py tests/unit/test_tsfm_base_contract.py
```
Result: **20 passed**.

### 2) Reproducible perf smoke benchmark + SLO budget checks
```bash
PYTHONPATH=. python3 pipelines/bench_tsfm_runner_perf.py --requests 200 --unique 20 --adapter-latency-ms 15 --budget-p95-ms 300 --budget-cycle-s 60
```
Observed:
- `elapsed_s=1.060`
- `throughput_rps=188.75`
- `latency_p95_ms=53.78`
- `cache_hit_rate=0.900`
- `SLO_PASS`

```bash
PYTHONPATH=. python3 pipelines/bench_tsfm_runner_perf.py --requests 200 --unique 200 --adapter-latency-ms 15 --budget-p95-ms 300 --budget-cycle-s 60
```
Observed (cold-ish, no cache reuse):
- `elapsed_s=10.396`
- `throughput_rps=19.24`
- `latency_p95_ms=75.85`
- `cache_hit_rate=0.000`
- `SLO_PASS`

## Run instructions
- Docs: `docs/prd2-implementation-status.md`
- Endpoint: `POST /tsfm/forecast`
- Start API: `uvicorn api.app:app --reload`
- Perf smoke: `PYTHONPATH=. python3 pipelines/bench_tsfm_runner_perf.py ...`

## Live integration CI
- Added live integration tests: `tests/integration/test_tollama_live_integration.py`
  - `TollamaAdapter` live request/response shape validation
  - `TSFMRunnerService` live-path assertion (`fallback_used=false` expected on healthy runtime)
- Added CI workflow: `.github/workflows/ci.yml`
  - `unit-tests` always run on PR/push/nightly/manual
  - `live-tollama-integration` runs only when gated:
    - event is nightly (`schedule`) **or** repo variable `ENABLE_LIVE_TOLLAMA_CI=true`
    - and secret `TOLLAMA_BASE_URL` is present
- Added ops runbook: `docs/ops/live-tollama-integration-runbook.md`
  - local env setup
  - skip/default safety behavior
  - CI secret/variable checklist
- Safety default for CI/local:
  - live tests are disabled unless `LIVE_TOLLAMA_TESTS=1`
  - tests skip (not fail) when tollama host:port is unreachable

## Remaining risks / follow-up
1. **tollama endpoint schema drift risk**: adapter isolates app contract but still requires updates if runtime schema changes.
2. **Conformal is currently request-time hook**: persistent rolling calibrator job + store can be expanded.
3. **Observability backend wiring pending**: metadata fields are in place; metrics sink/dashboard integration still needed.
