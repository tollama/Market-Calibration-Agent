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

## Conformal ops
- Follow-up #7 implemented: moved conformal calibration toward rolling operational flow with persisted state.
- Added rolling conformal updater pipeline: `pipelines/update_conformal_calibration.py`
  - Reads calibration history from JSONL/CSV (`q10,q50,q90,actual` or `resolved_prob`).
  - Applies rolling-window fit (`--window-size`, `--min-samples`, `--target-coverage`).
  - Computes pre/post empirical coverage and persists state.
- Added persistence module: `calibration/conformal_state.py`
  - Default state path: `data/derived/calibration/conformal_state.json`
  - Save/load helpers with schema version and metadata.
- Wired inference-time consumption in `TSFMRunnerService`
  - Auto-loads conformal state on startup when present.
  - Preserves previous behavior when state is missing/invalid.
  - Emits `meta.conformal_state_loaded` and (if loaded) `conformal_last_step`.
- Added tests:
  - `tests/unit/test_conformal_state.py` (load/save round-trip, missing-file fallback, legacy flat payload)
  - `tests/unit/test_tsfm_runner_service.py` extensions (auto-load usage + missing-state fallback)
- Added runbook: `docs/conformal-ops.md` (manual run + cron schedule examples)

## Final integration verification (2026-02-21, Python 3.11)
Executed final end-to-end release checks after integrating all recent PRD2 commits (fixture pack, chaos drills, core hardening, Python runtime gate, rolling conformal ops).

```bash
PYTHON_BIN=python3.11 python3 scripts/prd2_release_audit.py
PRD2_VERIFY_PYTHON_BIN=python3.11 scripts/prd2_verify_all.sh
```

Observed results:
- `PRD2 Release Audit: PASS`
- `scripts/prd2_verify_all.sh`: all 4 steps PASS (unit selection, integration selection, perf benchmark, release audit)
- machine-readable verification summary written to:
  - `artifacts/prd2_verify_summary.json`

## Remaining risks / follow-up
1. **tollama endpoint schema drift risk**: adapter isolates app contract but still requires updates if runtime schema changes.
2. **Conformal coverage monitoring still needed in prod dashboards**: updater/state are in place, but alert thresholds for calibration drift should be wired to observability.
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

## Python runtime gate (3.11+) for PRD2 release checks
Addressed false-fail class caused by interpreter mismatch (`python3` resolving to <3.11 in some environments):

- Updated package runtime requirement in `pyproject.toml`:
  - `requires-python` from `>=3.10` -> `>=3.11`
- Hardened release auditor `scripts/prd2_release_audit.py`:
  - Added explicit runtime precheck (`Python >=3.11`) before gate execution.
  - Added consistent interpreter selection via `--python-bin` / `PYTHON_BIN`.
  - Added actionable failure messages (binary missing / version too old + quick fix command).
  - Added command rendering support for `{PYTHON_BIN}` placeholder in checklist commands.
- Updated release checklist `docs/ops/prd2-release-checklist.yaml`:
  - Added explicit blocker `RB-000` (Python runtime 3.11+).
  - Switched all Python command checks from hardcoded `python3` to `{PYTHON_BIN}`.
- Updated one-command verifier `scripts/prd2_verify_all.sh`:
  - Release-audit stage now executes `scripts/prd2_release_audit.py` with the same selected interpreter (`PRD2_VERIFY_PYTHON_BIN`).
- Updated operator docs:
  - `docs/ops/prd2-release-audit.md`
  - `docs/ops/prd2-verify-all.md`
  - Included Python version requirement and quick-fix examples.

### Runtime-gate demonstration (current env)
`python3` in current environment resolves to 3.9, so the precheck fails fast with a clear fix:

```bash
python3 scripts/prd2_release_audit.py --skip-commands
```

Observed output:

```text
Python runtime precheck failed.
Python runtime too old: python3 resolved to 3.9; PRD2 release audit requires >= 3.11 (StrEnum-dependent codepath).
Quick fix:
  1) Install Python 3.11+
  2) Run with explicit interpreter:
     PYTHON_BIN=python3.11 python3 scripts/prd2_release_audit.py
```

Validation with explicit interpreter:

```bash
PYTHON_BIN=python3.11 python3 scripts/prd2_release_audit.py --skip-commands
```

Observed output (excerpt):

```text
Using Python runtime: python3.11 (3.11)
PRD2 Release Audit: PASS
- python_bin=python3.11
```

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

## Release-blocker core hardening
Implemented remaining core release blockers in service/runtime path with deterministic behavior:

- **Explicit degradation state machine** (`normal -> degraded -> baseline-only`) in `TSFMRunnerService`.
  - States are now explicit (`meta.degradation_state`) and transition from rolling-window failure rate thresholds.
  - Recovery is deterministic and stepwise (`baseline-only -> degraded -> normal`) via configured exit thresholds.
- **Cache hardening with stale-if-error**
  - TTL cache now keeps a bounded stale window (`cache.stale_if_error_s`).
  - On tollama failure, expired-but-still-stale cached response is served deterministically with
    `meta.fallback_reason=stale_if_error`, `meta.cache_stale=true`.
- **Circuit breaker hardening**
  - Replaced consecutive-only behavior with rolling-window failure-rate breaker.
  - Added explicit breaker states (`closed/open/half-open`) and half-open probe logic.
  - Probe success closes breaker; probe failure re-opens with cooldown.
- **Fast eligibility gates before tollama call**
  - `min_points_for_tsfm` gate retained.
  - `baseline_only_liquidity_bucket` gate retained.
  - Added `max_gap_minutes` gate using request-provided `max_gap_minutes` or inferred `y_ts/observed_ts` gaps.
- **Runtime config wiring**
  - Added new knobs in `configs/tsfm_runtime.yaml` and wired loading via `TSFMRunnerService.from_runtime_config()`.
  - API now bootstraps service from runtime config file (`api/app.py`).

### Hardening defaults chosen
- `cache.stale_if_error_s=120`
- `circuit_breaker.window_s=300`
- `circuit_breaker.min_requests=5`
- `circuit_breaker.failure_rate_to_open=1.0`
- `circuit_breaker.cooldown_s=120`
- `circuit_breaker.half_open_probe_requests=2`
- `circuit_breaker.half_open_successes_to_close=2`
- `degradation.window_s=300`
- `degradation.min_requests=5`
- `degradation.degraded_enter_failure_rate=0.30`
- `degradation.baseline_only_enter_failure_rate=0.70`
- `degradation.degraded_exit_failure_rate=0.15`
- `degradation.baseline_only_exit_failure_rate=0.25`

### Determinism/behavior tests added
- stale-if-error cache serving
- rolling-window breaker open + half-open recovery
- max-gap fast-gate fallback
- degradation state machine transitions

## Chaos drill suite
Implemented a PRD2 chaos drill suite isolated to scripts/tests/docs (no core runtime code changes).

### Added artifacts
- `scripts/chaos/prd2_tollama_chaos_drill.py`
  - Env-driven fault injection via `CHAOS_MODE=timeout|5xx|connection_drop`
  - Repeated drill runs (`CHAOS_REPEATS`) for deterministic fallback checks
  - JSON report output and non-zero exit on failed pass criteria
- `tests/integration/test_prd2_chaos_drills.py`
  - Verifies deterministic baseline fallback for timeout/5xx/connection-drop modes
  - Verifies response safety (`finite`, `[0,1]`, `q10 <= q50 <= q90`)
  - Verifies circuit breaker opens and short-circuits adapter calls after threshold failures
- `docs/ops/prd2-chaos-drill.md`
  - Operator runbook with commands, expected outcomes, and escalation path

### Validation executed
```bash
pytest -q tests/integration/test_prd2_chaos_drills.py
```
Result: **all tests passed locally**.
- Added dedicated operator drill script under `scripts/chaos/` for timeout/5xx/connection-drop simulation.

## Fixture pack
- Refreshed fixture pack with reusable scenario datasets and loader-backed tests (commit `499b966`).
- Added reusable PRD2 fixture dataset under `tests/fixtures/prd2/`:
  - `D1_normal.json`
  - `D2_jumpy.json`
  - `D3_illiquid.json`
  - `D4_failure-template.json`
- Added loader utilities at `tests/helpers/prd2_fixtures.py` for fixture path/request/expectation/adapter quantile loading.
- Extended tests to consume fixture pack:
  - `tests/unit/test_tsfm_runner_service.py` (parameterized fixture scenarios)
  - `tests/unit/test_api_tsfm_forecast.py` (API contract payload from fixture)
  - `tests/integration/test_prd2_fixture_scenarios.py` (integration-style scenario coverage)
- Added ops documentation: `docs/ops/prd2-test-fixtures.md`.

## PRD1+PRD2 market-pipeline gap closure
Addressed remaining gaps in market data pipeline/feature preparation paths that were not fully aligned with PRD1 I-06/I-07 and PRD2 Data Prep defaults.

### Gaps closed
1. **Cutoff fallback policy was too strict by default**
   - Before: nearest-before selection enforced a hard `max_lookback_seconds=900` cap, which could drop valid fallback rows.
   - After: default lookback cap is now unbounded (`None`), matching PRD fallback intent (“nearest earlier”).
   - Kept explicit guardrail support by allowing opt-in `max_lookback_seconds` when callers need stricter behavior.

2. **Feature stage ignored optional high-frequency aggregates**
   - Before: `stage_build_features` always computed features from cutoff rows only.
   - After: stage now resolves optional high-frequency aggregate inputs from state (`high_freq_agg`, `high_freq_agg_rows`, `intraday_agg_rows`) and passes them into `build_features(...)` so overlay fields can be applied deterministically.

3. **Default config lacked PRD2 data-prep defaults in shared app config**
   - Added `data.prep` defaults in `configs/default.yaml`:
     - `freq: 5m`
     - `y_definition: mid_or_last`
     - `max_trade_staleness_minutes: 60`
     - `clip_eps: 1e-6`
     - `max_gap_minutes: 60`

### Tests added/updated
- Updated `tests/unit/test_cutoff_snapshots.py`:
  - verifies nearest-earlier fallback now works without implicit 15m cap
  - verifies explicit `max_lookback_seconds` still enforces strict filtering
- Updated `tests/unit/test_feature_stage.py`:
  - verifies high-frequency aggregate overlay is used when present in stage state

## PRD1+PRD2 test coverage gap closure
Added focused acceptance-gap tests under `tests/unit/test_prd12_acceptance_gap_closure.py`:
- `test_prd1_i15_min_trust_score_boundary_is_inclusive`
  - Traceability: **PRD1 I-15 AC** (`min_trust_score` boundary + strict-gate pass path).
  - Verifies threshold is inclusive (`trust_score == min_trust_score` passes, below threshold is filtered).
- `test_prd2_ac_operational_meta_contains_observability_fields`
  - Traceability: **PRD2 AC #3 Operational**.
  - Verifies forecast response includes operational observability primitives (`runtime`, `latency_ms`, `fallback_used`, cache flags, breaker/degradation state, warnings).
- `test_prd2_ac_product_alignment_band_breach_signal_is_deterministic`
  - Traceability: **PRD2 AC #4 Product alignment**.
  - Verifies TSFM-produced bands yield deterministic `BAND_BREACH` signal and consistent severity for Gate-1-compatible alerting.

### Matrix-targeted unresolved-gap acceptance tests (P2-11, P2-09, P2-07, I-15, I-01)
Added targeted tests to mirror `.openclaw-plans/PRD12_GAP_MATRIX.md` unresolved entries:
- **P2-11**
  - `tests/unit/test_api_tsfm_auth.py::test_p2_11_tsfm_forecast_requires_inbound_auth_token`
  - `tests/unit/test_api_tsfm_rate_limit.py::test_p2_11_tsfm_forecast_enforces_rate_limit_with_retry_after`
  - Current run status: **Fail-before** (API currently allows unauthenticated/unlimited calls).
- **P2-09**
  - `tests/unit/test_tsfm_metrics_emission.py::test_p2_09_metrics_endpoint_is_exposed_for_runtime_observability`
  - Current run status: **Fail-before** (`/metrics` not exposed in current app routes).
- **P2-07**
  - `tests/unit/test_interval_metrics.py::{test_p2_07_interval_metrics_module_exists,test_p2_07_offline_eval_pipeline_exists}`
  - Current run status: partial (**interval_metrics.py exists**, **evaluate_tsfm_offline.py missing**).
- **I-15**
  - `tests/integration/test_alert_end_to_end_pipeline.py::test_i15_end_to_end_alert_gate_transitions_are_deterministic`
  - Current run status: **Pass** (gate/severity transition determinism covered).
- **I-01**
  - `tests/unit/test_gamma_raw_path_contract.py::test_i01_gamma_raw_path_contract_exposes_canonical_prd_dt_partition`
  - Current run status: **Pass** (canonical `raw/gamma/dt=...` metadata contract asserted).
  - Existing legacy acceptance tests (`tests/unit/test_i01_acceptance.py`) currently fail against additional `gamma_dt/*` keys, indicating contract drift that should be normalized in product path/output schema.

## PRD1+PRD2 forecast-serving gap closure
- Wired `TSFMRunnerService.from_runtime_config()` to instantiate `TollamaAdapter` from `tsfm.adapter` runtime fields (timeout/retry/backoff/jitter/pool), closing config-to-runtime drift in serving path.
- Aligned default tollama timeout to PRD2 default (`2.0s`) in both adapter defaults and `configs/tsfm_runtime.yaml`.
- Exposed gap-gating request fields in API schema (`y_ts`, `observed_ts`, `max_gap_minutes`) so `/tsfm/forecast` can enforce PRD2 missing-gap fallback policy through API callers (not just internal calls).
- Enforced runtime cache bound via `cache.max_entries` to prevent unbounded in-memory growth in serving runtime.
- Added unit/API coverage for each fix:
  - runtime adapter config wiring + conversion of ms backoff/jitter to seconds
  - cache max-entry eviction behavior
  - API acceptance/pass-through of gap metadata fields
