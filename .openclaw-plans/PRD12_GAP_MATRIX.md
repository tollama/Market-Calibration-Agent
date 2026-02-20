# PRD1 + PRD2 Gap Matrix

Last audited: 2026-02-21 (Asia/Seoul)
Repo: `/Users/ychoi/Documents/GitHub/Market-Calibration-Agent`
Scope: Requirement-level comparison of PRD1/PRD2 vs current implementation (planning/audit only; no product-code edits)

Status legend:
- **Implemented**: Requirement intent + AC largely satisfied with code/tests
- **Partial**: Significant implementation exists but AC/operational closure incomplete
- **Missing**: No concrete implementation path yet for the requirement

---

## A) PRD1 (I-01 ~ I-20)

| Req | Requirement | Status | Evidence (code/tests) |
|---|---|---|---|
| I-01 | Gamma connector + pagination + retry + raw store contract | **Partial** | `connectors/polymarket_gamma.py`, `pipelines/ingest_gamma_raw.py`, `tests/unit/test_gamma_connector.py`, `tests/unit/test_i01_acceptance.py` |
| I-02 | Subgraph GraphQL connector + templates + partial failure reporting | **Implemented** | `connectors/polymarket_subgraph.py`, `tests/unit/test_subgraph_connector.py` |
| I-03 | Market registry (ID mapping + slug history + conflict rule) | **Implemented** | `schemas/market_registry.py`, `registry/build_registry.py`, `registry/conflict_rules.py`, `pipelines/registry_linker.py`, tests for registry conflicts/linking |
| I-04 | Raw/derived separation + partition convention | **Implemented** | `storage/writers.py`, `storage/layout.md`, `tests/unit/test_storage_writers.py` |
| I-05 | Label/status resolver (RESOLVED_TRUE/FALSE, VOID, UNRESOLVED) | **Implemented** | `agents/label_resolver.py`, `calibration/labeling.py`, labeling tests |
| I-06 | Standard cutoff snapshots (T-24h/T-1h/Daily) + fallback | **Implemented** | `pipelines/build_cutoff_snapshots.py`, cutoff tests |
| I-07 | Feature builder (returns/vol/velocity/OI/TTE/liquidity) | **Implemented** | `features/build_features.py`, feature tests |
| I-08 | Baseline bands (EWMA/Kalman/Rolling quantile) | **Implemented** | `runners/baselines.py`, `tests/unit/test_baseline_bands.py` |
| I-09 | TSFM base interface contract | **Implemented** | `runners/tsfm_base.py`, `tests/unit/test_tsfm_base_contract.py` |
| I-10 | Conformal calibration + drift retrain trigger | **Implemented** | `calibration/conformal.py`, `calibration/drift.py`, conformal/drift tests |
| I-11 | Question-quality LLM scorer (strict JSON + retries) | **Implemented** | `agents/question_quality_agent.py`, `llm/schemas.py`, question-quality tests |
| I-12 | LLM cache + reproducibility controls | **Implemented** | `llm/cache.py`, `llm/client.py`, `llm/policy.py`, SQLite cache tests |
| I-13 | Calibration engine (Brier/LogLoss/ECE + segments + markdown/parquet output) | **Implemented** | `calibration/metrics.py`, `pipelines/build_scoreboard_artifacts.py`, calibration/scoreboard tests |
| I-14 | Trust score (0-100) + component logs + config weights | **Implemented** | `calibration/trust_score.py`, `pipelines/trust_policy_loader.py`, trust-score tests |
| I-15 | Alert engine (band breach + 3 gates + severity) | **Partial** | `agents/alert_agent.py`, `pipelines/build_alert_feed.py`, `tests/unit/test_i15_acceptance.py` |
| I-16 | WS ingestor + 1m/5m aggregation | **Implemented** | `connectors/polymarket_ws.py`, `pipelines/realtime_ws_job.py`, intraday/ws tests |
| I-17 | Explain-5-lines generator with evidence guardrail | **Implemented** | `agents/explain_agent.py`, `agents/explain_validator.py`, explain tests |
| I-18 | Postmortem markdown auto-generation | **Implemented** | `reports/postmortem.py`, `pipelines/build_postmortem_batch.py`, postmortem tests |
| I-19 | Daily orchestration (idempotent, checkpoint, backfill/retry) | **Implemented** | `pipelines/daily_job.py`, daily job tests |
| I-20 | Read-only API endpoints for scoreboard/alerts/postmortem | **Implemented** | `api/app.py`, `api/schemas.py`, API tests |

---

## B) PRD2 (TSFM Runner via tollama)

| Req | Requirement | Status | Evidence (code/tests) |
|---|---|---|---|
| P2-01 | `/tsfm/forecast` contract | **Implemented** | `api/app.py`, `api/schemas.py`, `tests/unit/test_api_tsfm_forecast.py` |
| P2-02 | Tollama adapter (timeout/retry/parsing) | **Implemented** | `runners/tollama_adapter.py`, runner/integration tests |
| P2-03 | Bounded-series handling (logit + clipping) | **Implemented** | `runners/tsfm_service.py`, `tests/unit/test_tsfm_runner_service.py` |
| P2-04 | Baseline fallback policy | **Implemented** | `runners/tsfm_service.py`, `runners/baselines.py`, fixture/integration tests |
| P2-05 | Post-processing safety (crossing fix + width sanity) | **Implemented** | `runners/tsfm_service.py`, runner service tests |
| P2-06 | Rolling conformal integration + persisted state | **Implemented** | `calibration/conformal*.py`, `pipelines/update_conformal_calibration.py`, conformal docs/tests |
| P2-07 | Offline eval: time split + event-holdout + interval metrics | **Missing** | Perf smoke exists (`pipelines/bench_tsfm_runner_perf.py`) but no dedicated event-holdout evaluation pipeline/artifact path |
| P2-08 | SLO/perf gates (p95 latency + batch cycle) | **Implemented** | perf bench + gate workflow + validation scripts |
| P2-09 | Observability metrics emission (latency/error/fallback/crossing/coverage) + dashboards | **Partial** | Dashboard/rules exist under `monitoring/`, but service-level metric emitter instrumentation is not wired in runtime path |
| P2-10 | Model license guardrail (`commercial_ok`) | **Implemented** | `configs/tsfm_models.yaml`, `tests/unit/test_tsfm_model_license_guard.py` |
| P2-11 | Security edge controls (inbound auth/rate limit + breaker degrade) | **Partial** | breaker/degradation implemented in `runners/tsfm_service.py`; inbound API auth/rate limiting not implemented at app layer |
| P2-12 | Operational release assets (canary, chaos drill, release audit) | **Implemented** | runbooks/checklists/scripts/workflow + integration drill tests |

---

## C) Concrete gaps (all Partial/Missing only)

| Gap ID | Linked req | Why gap remains | Exact files to modify | Acceptance tests (add/run) |
|---|---|---|---|---|
| G-01 | I-01 | Raw path contract ambiguity vs PRD wording (`raw/gamma/dt=...` vs dataset-scoped `raw/gamma/{dataset}/dt=...`) | `pipelines/ingest_gamma_raw.py`, `storage/layout.md`, `docs/prd1-implementation-status.md`, optionally `PRD1 - Polymarket Market Calibration Agent.md` (if choosing doc-alignment) | **Add** `tests/unit/test_gamma_raw_path_contract.py` to assert selected canonical path. **Run** `tests/unit/test_i01_acceptance.py` and gamma ingest tests. |
| G-02 | I-15 | Strong unit coverage exists, but limited full ingest→publish regression with realistic multi-source fixtures | `pipelines/daily_job.py`, `pipelines/build_alert_feed.py`, `tests/integration/test_alert_end_to_end_pipeline.py` (new), `tests/helpers/prd2_fixtures.py` (extend fixtures) | **Add** integration test: Gamma/Subgraph/WS fixture chain -> alert feed output with gate transitions and severity checks. **Run** existing `tests/unit/test_i15_acceptance.py` + new integration. |
| G-03 | P2-07 | No event-holdout offline evaluation pipeline producing reproducible interval-quality artifacts (coverage/width/pinball) | `pipelines/evaluate_tsfm_offline.py` (new), `calibration/interval_metrics.py` (new), `docs/ops/prd2-offline-eval.md` (new), optional CI hook `.github/workflows/prd2-perf-gate.yml` extension | **Add** `tests/unit/test_interval_metrics.py`, `tests/integration/test_tsfm_event_holdout_eval.py`. Require output artifact checks for time-split + event-holdout reports. |
| G-04 | P2-09 | Monitoring assets exist, but runtime does not emit required observability metrics in-process | `runners/tsfm_service.py`, `api/app.py` (metrics middleware/endpoint), optional `monitoring/prometheus/tsfm_service_metrics.rules.yaml`, update `monitoring/grafana/prd2-observability-dashboard.json` | **Add** `tests/unit/test_tsfm_metrics_emission.py` verifying latency/error/fallback/crossing counters/histograms emitted with expected names. |
| G-05 | P2-11 | Outbound token + breaker exist; inbound auth and request rate-limit for `/tsfm/forecast` absent | `api/app.py`, `api/dependencies.py`, `configs/tsfm_runtime.yaml` (auth/rate-limit config), docs runbook updates | **Add** `tests/unit/test_api_tsfm_auth.py` (401/403), `tests/unit/test_api_tsfm_rate_limit.py` (429 behavior + retry-after semantics). |

---

## D) Totals

- Total requirements audited: **32** (PRD1: 20, PRD2: 12)
- Implemented: **27**
- Partial: **4**
- Missing: **1**

Highest-priority closure sequence:
1. **P2-11 inbound auth/rate-limit** (security/abuse risk)
2. **P2-09 runtime observability emission** (operational blind spots)
3. **P2-07 event-holdout offline eval** (model quality governance)
4. **I-15 full-path alert integration regression** (alert confidence)
5. **I-01 path contract normalization** (spec/implementation consistency)
