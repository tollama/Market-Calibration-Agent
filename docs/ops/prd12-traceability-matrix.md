# PRD1 + PRD2 Traceability Matrix

Last updated: 2026-02-21 (Asia/Seoul)
Scope: documentation traceability against repository implementation and tests.

Status legend:
- **Implemented**: requirement intent is evidenced by code + tests/docs
- **Partial**: substantial implementation exists, but AC/operational proof is incomplete
- **Missing**: no clear implementation evidence in repo

---

## A) PRD1 traceability (I-01 ~ I-20)

| Req ID | Requirement (PRD1) | Implementation evidence | Test evidence | Status |
|---|---|---|---|---|
| I-01 | Gamma connector: pagination/retry/rate-limit + raw save | `connectors/polymarket_gamma.py`, `pipelines/ingest_gamma_raw.py` | `tests/unit/test_gamma_connector.py`, `test_gamma_raw_ingest*.py`, `test_i01_acceptance.py` | **Partial** |
| I-02 | Subgraph GraphQL connector + templates + partial-fail reporting | `connectors/polymarket_subgraph.py` | `tests/unit/test_subgraph_connector.py` | **Implemented** |
| I-03 | Market registry (ID mapping, slug history, conflicts) | `schemas/market_registry.py`, `registry/build_registry.py`, `registry/conflict_rules.py`, `pipelines/registry_linker.py` | `tests/unit/test_registry_conflicts.py`, `test_registry_linker.py` | **Implemented** |
| I-04 | Raw/derived storage split + partition rules | `storage/writers.py`, `storage/layout.md` | `tests/unit/test_storage_writers.py`, `test_derived_store_loaders.py` | **Implemented** |
| I-05 | Label/status resolver (RESOLVED/VOID/UNRESOLVED + multi-outcome handling) | `agents/label_resolver.py`, `calibration/labeling.py`, `pipelines/build_scoreboard_artifacts.py` | `tests/unit/test_label_resolver.py`, `test_labeling_filters.py`, `test_labeling_multi_outcome.py` | **Implemented** |
| I-06 | Cutoff snapshots (T-24h/T-1h/Daily + fallback) | `pipelines/build_cutoff_snapshots.py` | `tests/unit/test_cutoff_snapshots.py`, `test_cutoff_stage_source_rows.py` | **Implemented** |
| I-07 | Feature builder (returns/vol/velocity/oi/tte/liquidity) | `features/build_features.py`, `pipelines/build_feature_frame.py` | `tests/unit/test_feature_builder.py`, `test_feature_stage.py` | **Implemented** |
| I-08 | Baseline bands (EWMA/Kalman/Rolling quantile) | `runners/baselines.py` | `tests/unit/test_baseline_bands.py` | **Implemented** |
| I-09 | TSFM runner interface contract | `runners/tsfm_base.py` | `tests/unit/test_tsfm_base_contract.py` | **Implemented** |
| I-10 | Conformal calibration module + drift trigger | `calibration/conformal.py`, `calibration/drift.py`, `pipelines/update_conformal_calibration.py` | `tests/unit/test_conformal_calibration.py`, `test_drift_trigger.py` | **Implemented** |
| I-11 | LLM question quality scorer (strict JSON + retries) | `agents/question_quality_agent.py`, `llm/schemas.py` | `tests/unit/test_question_quality_agent_contract.py`, `test_question_quality_schema.py`, `test_question_quality_agent_defaults.py` | **Implemented** |
| I-12 | LLM cache + reproducibility controls | `llm/cache.py`, `llm/client.py`, `llm/policy.py`, `llm/sqlite_cache.py` | `tests/unit/test_llm_cache.py`, `test_llm_client_sqlite_cache_integration.py`, `test_llm_sampling_policy.py`, `test_llm_top_p_policy.py` | **Implemented** |
| I-13 | Calibration engine (Brier/LogLoss/ECE + segments) | `calibration/metrics.py`, `pipelines/build_scoreboard_artifacts.py` | `tests/unit/test_calibration_metrics*.py`, `test_scoreboard_artifacts*.py` | **Implemented** |
| I-14 | Trust score 0-100 + component logs + config weights | `calibration/trust_score.py`, `pipelines/trust_policy_loader.py`, `configs/default.yaml` | `tests/unit/test_trust_score.py`, `test_trust_policy_loader.py` | **Implemented** |
| I-15 | Alert engine (band breach + 3 gates + severity) | `agents/alert_agent.py`, `pipelines/build_alert_feed.py`, `pipelines/alert_policy_loader.py` | `tests/unit/test_alert_agent*.py`, `test_alert_feed_gate_rules.py`, `test_i15_acceptance.py` | **Partial** |
| I-16 | WS ingestion + 1m/5m aggregation | `connectors/polymarket_ws.py`, `pipelines/realtime_ws_job.py`, `pipelines/aggregate_intraday_bars.py` | `tests/unit/test_polymarket_ws_connector.py`, `test_intraday_aggregator.py`, `test_realtime_ws_job.py` | **Implemented** |
| I-17 | Explain-5-lines generator with evidence guardrails | `agents/explain_agent.py`, `agents/explain_validator.py` | `tests/unit/test_explain_agent_guardrails.py`, `test_explain_agent_policy.py`, `test_explain_validator.py` | **Implemented** |
| I-18 | Postmortem markdown auto-generation (deterministic naming) | `reports/postmortem.py`, `pipelines/build_postmortem_batch.py` | `tests/unit/test_postmortem_report.py`, `test_postmortem_batch.py` | **Implemented** |
| I-19 | Batch orchestration + checkpoint/retry/backfill | `pipelines/daily_job.py` | `tests/unit/test_daily_job_*.py` | **Implemented** |
| I-20 | Read-only API/CLI for scoreboard/alerts/postmortem | `api/app.py`, `api/dependencies.py`, `api/schemas.py` | `tests/unit/test_api_*.py`, `test_i20_acceptance.py` | **Implemented** |

Notes:
- I-01 partial reason: current raw path convention is dataset-scoped (`raw/gamma/{dataset}/dt=...`) vs PRD wording (`raw/gamma/dt=...`).
- I-15 partial reason: rule logic/unit tests are strong, but explicit network-including ingest→publish integration regression remains limited.

---

## B) PRD2 traceability (TSFM Runner via tollama)

| Req ID | Requirement (PRD2) | Implementation evidence | Test evidence | Status |
|---|---|---|---|---|
| P2-01 | Internal forecast API contract (`POST /tsfm/forecast`) | `api/app.py`, `api/schemas.py`, `runners/tsfm_service.py` | `tests/unit/test_api_tsfm_forecast.py`, `test_tsfm_runner_service.py` | **Implemented** |
| P2-02 | Tollama adapter (retry/timeout/parsing) | `runners/tollama_adapter.py` | `tests/unit/test_tsfm_runner_service.py`, `tests/integration/test_tollama_live_integration.py` | **Implemented** |
| P2-03 | Bounded series handling ([0,1], logit/inv-logit, clipping) | `runners/tsfm_service.py` | `tests/unit/test_tsfm_runner_service.py` | **Implemented** |
| P2-04 | Baseline fallback policy on TSFM failure/insufficient quality | `runners/tsfm_service.py`, `runners/baselines.py`, `configs/tsfm_runtime.yaml` | `tests/unit/test_tsfm_runner_service.py`, `test_prd2_fixture_loader.py`, `tests/integration/test_prd2_fixture_scenarios.py` | **Implemented** |
| P2-05 | Post-processing safety: quantile monotonicity, width sanity | `runners/tsfm_service.py` | `tests/unit/test_tsfm_runner_service.py` | **Implemented** |
| P2-06 | Rolling conformal calibration integration | `calibration/conformal.py`, `calibration/conformal_state.py`, `pipelines/update_conformal_calibration.py`, `docs/conformal-ops.md` | `tests/unit/test_conformal_calibration.py`, `test_conformal_state.py` | **Implemented** |
| P2-07 | Offline eval plan (time split + event-holdout + interval metrics) | `.openclaw-plans/PRD2_LOADTEST_SPEC.md`, `.openclaw-plans/PRD2_PERF_BLUEPRINT.md`, `pipelines/bench_tsfm_runner_perf.py` | `tests/unit/test_tsfm_perf_smoke.py` | **Partial** |
| P2-08 | SLO/perf targets (p95 latency, cycle time) with reproducible checks | `pipelines/bench_tsfm_runner_perf.py`, `.github/workflows/prd2-perf-gate.yml`, `scripts/validate_prd2_perf_bench.py`, `docs/ops/prd2-perf-gate.md` | `tests/unit/test_tsfm_perf_smoke.py` | **Implemented** |
| P2-09 | Observability metrics/logging and dashboards | `monitoring/grafana/prd2-observability-dashboard.json`, `monitoring/prometheus/tsfm_canary_alerts.rules.yaml`, `docs/ops/prd2-dashboards.md` | `scripts/evaluate_tsfm_canary_gate.py` (gate logic), no in-service metrics emitter test | **Partial** |
| P2-10 | Model licensing guardrail (`commercial_ok` enforcement) | `configs/tsfm_models.yaml` | `tests/unit/test_tsfm_model_license_guard.py` | **Implemented** |
| P2-11 | Security/deployment controls (private network, inbound auth/rate limit, breaker-driven degrade) | `runners/tollama_adapter.py` (outbound token), `runners/tsfm_service.py` (circuit/degradation) | Breaker behavior in `tests/unit/test_tsfm_runner_service.py`; no API auth/rate-limit tests | **Partial** |
| P2-12 | Deliverable: canary rollout + release audit automation | `docs/ops/tsfm-canary-rollout-runbook.md`, `docs/ops/prd2-release-audit.md`, `docs/ops/prd2-release-checklist.yaml`, `scripts/prd2_release_audit.py`, `scripts/prd2_verify_all.sh` | `tests/integration/test_prd2_chaos_drills.py` + checklist command gates | **Implemented** |

---

## C) Unresolved / action list

1. **Align I-01 raw path contract**
   - Decide canonical path contract: PRD wording (`raw/gamma/dt=...`) vs implemented dataset-scoped layout.
   - Update either PRD/docs or ingestion code/tests to remove ambiguity.

2. **Close I-15 full-path integration gap**
   - Add at least one network-including ingest→publish regression (Gamma/Subgraph/WS mocks or controlled live smoke).

3. **PRD2 observability implementation closure**
   - Add in-process metrics emission (e.g., Prometheus instrumentation for latency/error/fallback/crossing) and tests.
   - Keep dashboard/rules aligned to emitted metric names.

4. **PRD2 security hardening (service edge)**
   - Add inbound API auth and request rate-limiting at service layer or gateway contract.
   - Document enforcement point and add automated tests.

5. **PRD2 offline evaluation completeness**
   - Add explicit event-holdout evaluation pipeline/tests (not just perf smoke), and store reproducible artifacts.

6. **Track PRD2 open questions as decision records**
   - Record final decisions for tollama contract evolution, default y-definition fallback priority, calibration window default, and top-N selection strategy.

---

## D) Summary counts

Across PRD1 (20 rows) + PRD2 (12 rows) = **32 traceability rows**:

- **Implemented:** 26
- **Partial:** 6
- **Missing:** 0

(Partial items are listed in section C for closure.)
