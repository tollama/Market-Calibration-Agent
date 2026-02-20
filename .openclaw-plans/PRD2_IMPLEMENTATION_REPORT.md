# PRD2 IMPLEMENTATION REPORT — TSFM Runner (via tollama)

## Scope completed
Implemented PRD2 sequentially (Stage 1..n), then extended with explicit runtime/throughput hardening.

> Note: requested support docs were checked but not present at run time:
> - `.openclaw-plans/PRD2_PERF_BLUEPRINT.md`
> - `.openclaw-plans/PRD2_LOADTEST_SPEC.md`
> - `.openclaw-plans/PRD2_TOLLAMA_HARDENING.md`

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

## Performance-focused decisions (new)
- **Service cache (TTL 60s)**
  - Decision: request-hash cache in TSFM runner.
  - Why: top-N alert cycles commonly repeat near-identical calls within 1 minute.
  - Effect: cuts repeated tollama calls; lowers p95 and cycle time.
- **Circuit breaker (3 failures, 30s cooldown)**
  - Decision: open breaker after 3 consecutive tollama failures; force baseline fallback during cooldown.
  - Why: avoid timeout storms and protect cycle SLO.
- **HTTP pooling in adapter (100 max, 20 keepalive)**
  - Decision: persistent `httpx.Client` with explicit limits.
  - Why: reduce connection setup overhead and improve throughput under burst loads.
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
- `pipelines/bench_tsfm_runner_perf.py` (new)
- `docs/prd2-implementation-status.md` (new, then updated)
- `README.md` (updated link)
- `.openclaw-plans/PRD2_IMPLEMENTATION_REPORT.md` (this file)

## Defaults chosen and rationale
- `freq=5m`, `horizon_steps=12`, `input_len_steps=288`: aligns with alert cadence + 24h context.
- `quantiles=[0.1,0.5,0.9]`: standard interval contract for gate/breach flow.
- `transform=logit`, `eps=1e-6`: stable bounded-probability modeling.
- `tollama timeout=2.0s`, `retry=1`: resilience without overshooting p95 target.
- `min_points_for_tsfm=32`: prevents unstable short-context inference.
- `baseline_method=EWMA`: low-latency robust fallback.
- `baseline_only_liquidity=low`: conservative operation for illiquid markets.
- `min_interval_width=0.02`, `max_interval_width=0.9`: prevents pathological overconfident or unusably wide bands.
- **Perf defaults**:
  - `cache_ttl_s=60`
  - `circuit_breaker_failures=3`
  - `circuit_breaker_cooldown_s=30`
  - `max_connections=100`
  - `max_keepalive_connections=20`

## Verification executed
### 1) Unit/API checks
```bash
python3 -m pytest tests/unit/test_tsfm_runner_service.py tests/unit/test_api_tsfm_forecast.py tests/unit/test_tsfm_model_license_guard.py tests/unit/test_baseline_bands.py tests/unit/test_tsfm_base_contract.py
```
Result: **17 passed**.

### 2) Reproducible perf smoke benchmark + SLO budget checks
```bash
PYTHONPATH=. python3 pipelines/bench_tsfm_runner_perf.py --requests 200 --unique 20 --adapter-latency-ms 15 --budget-p95-ms 300 --budget-cycle-s 60
```
Observed:
- `elapsed_s=0.977`
- `throughput_rps=204.81`
- `latency_p95_ms=49.94`
- `cache_hit_rate=0.900`
- `SLO_PASS`

```bash
PYTHONPATH=. python3 pipelines/bench_tsfm_runner_perf.py --requests 200 --unique 200 --adapter-latency-ms 15 --budget-p95-ms 300 --budget-cycle-s 60
```
Observed (cold-ish, no cache reuse):
- `elapsed_s=10.591`
- `throughput_rps=18.88`
- `latency_p95_ms=75.71`
- `cache_hit_rate=0.000`
- `SLO_PASS`

## Run instructions
- Docs: `docs/prd2-implementation-status.md`
- Endpoint: `POST /tsfm/forecast`
- Start API: `uvicorn api.app:app --reload`
- Perf smoke: `PYTHONPATH=. python3 pipelines/bench_tsfm_runner_perf.py ...`

## Remaining risks / follow-up
1. **tollama endpoint schema drift risk**: adapter isolates app contract but still requires updates if runtime schema changes.
2. **No live tollama integration in CI**: current coverage is unit-level with adapter stubs.
3. **Conformal is currently request-time hook**: persistent rolling calibrator job + store can be expanded.
4. **Observability backend wiring pending**: metadata fields are in place; metrics sink/dashboard integration still needed.
