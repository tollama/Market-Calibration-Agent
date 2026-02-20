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

## Observability & rollout gates
### Added artifacts
- `monitoring/prometheus/tsfm_canary_alerts.rules.yaml`
  - Concrete Prometheus alert rules for:
    - p95 latency
    - error rate
    - fallback rate
    - breaker-open rate
    - invalid output rate
  - Includes explicit rollback-trigger alerts aligned with PRD2 load-test spec.
- `docs/ops/tsfm-canary-rollout-runbook.md`
  - Canary promotion flow: `5% -> 25% -> 100%`
  - Gate windows: `30m -> 60m -> 24h`
  - Exact immediate rollback triggers (ANY):
    1) p95 > 400ms for 2 consecutive 5m windows
    2) error_rate > 2% for any 5m window
    3) invalid_output_rate > 0
    4) fallback_rate > 20% for 15m
    5) breaker_open_rate > 30% for 15m
- `scripts/evaluate_tsfm_canary_gate.py`
  - JSON metrics input -> deterministic gate verdict output (`gate_passed`, `rollback_triggered`, reasons)
  - Exit code: `0` on pass, `2` on fail (CI-friendly)
- Example inputs:
  - `scripts/examples/canary_gate_pass.json`
  - `scripts/examples/canary_gate_fail_rollback.json`

### Smoke validation
```bash
python3 scripts/evaluate_tsfm_canary_gate.py --input scripts/examples/canary_gate_pass.json --stage canary_5
```
Expected: `gate_passed=true`, `rollback_triggered=false`

```bash
python3 scripts/evaluate_tsfm_canary_gate.py --input scripts/examples/canary_gate_fail_rollback.json --stage canary_25
```
Expected: `gate_passed=false`, `rollback_triggered=true` with rollback reasons.

### Doc wiring updates
- Ops index added: `docs/ops/README.md` links runbook/rules/evaluator assets.
- Canary runbook references monitor rule file + evaluator usage for on-call handoff.

## Remaining risks / follow-up
1. **tollama endpoint schema drift risk**: adapter isolates app contract but still requires updates if runtime schema changes.
2. **Conformal is currently request-time hook**: persistent rolling calibrator job + store can be expanded.
3. **Observability backend wiring pending**: rules/runbook/evaluator are added; metrics exporter/dashboard integration still needed per environment.

## Perf CI gate
- Added isolated workflow: `.github/workflows/prd2-perf-gate.yml`.
- Trigger mode: `push`, `pull_request`, and `workflow_dispatch`.
- Workflow executes deterministic benchmark via `pipelines/bench_tsfm_runner_perf.py` with strict budgets:
  - `latency_p95_ms <= 300`
  - `elapsed_s <= 60`
- Added helper parser/validator: `scripts/validate_prd2_perf_bench.py`.
  - Parses benchmark stdout (`key=value`) into normalized JSON.
  - Validates thresholds and returns non-zero on regression.
- Added operations doc: `docs/ops/prd2-perf-gate.md` with local run commands and output format.

## One-command verification
- Added `scripts/prd2_verify_all.sh` as a deterministic single entrypoint for PRD2 release checks.
- Execution order is fixed: unit selection → integration selection → perf benchmark → release audit.
- Script hardening:
  - `set -euo pipefail`
  - timestamped logs
  - per-step log files under `artifacts/prd2_verify_logs/`
  - non-zero exit on any failed step
- Added machine-readable summary output: `artifacts/prd2_verify_summary.json`.
- Added operations doc: `docs/ops/prd2-verify-all.md` (local + CI usage, dry-run mode, artifact expectations).

## Release audit automation
- Added machine-readable checklist: `docs/ops/prd2-release-checklist.yaml`
  - Encodes PRD2 release blockers and P1 checks as explicit `file` and `command` gates.
- Added automated auditor: `scripts/prd2_release_audit.py`
  - Loads YAML checklist and validates required artifacts/commands.
  - Emits human-readable and JSON (`--json`) PASS/FAIL reports.
  - Returns exit code `0/1/2` for CI-friendly gating.
- Added usage guide: `docs/ops/prd2-release-audit.md`
  - Documents run commands, output interpretation, and examples.
- Current status verification command:
  - `python3 scripts/prd2_release_audit.py`

## Dashboard pack
Added static Grafana observability artifacts for PRD2 under `monitoring/grafana/`:
- `prd2-observability-dashboard.json`
- `prd2-observability-dashboard.provider.yaml`

Dashboard includes required panels:
- request latency p50/p95/p99
- error rate
- fallback rate by reason
- breaker-open rate
- cache hit rate
- top-N cycle time (p95 by `market_id`)

Added concise ops doc:
- `docs/ops/prd2-dashboards.md` (UI import, file provisioning, expected PromQL/metrics)

Quick sanity checks performed:
- JSON parse validation for dashboard file: PASS
- YAML parse validation for provider file: PASS
- `monitoring/grafana/` and docs references present in git diff.
