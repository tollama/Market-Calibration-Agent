# Forecasting Improvement Issue Templates

This document contains GitHub-ready issue drafts for improving MCA forecasting quality for prediction markets.

Suggested common labels:
- `forecasting`
- `prediction-markets`
- `research`
- `evaluation`

Suggested milestone order:
1. Benchmark and dataset
2. Features and models
3. Calibration and runtime
4. Monitoring and artifact pack

---

## T1. Build Forecasting Benchmark Contract

**Title**
`feat(eval): define forecasting benchmark contract for market vs model quality`

**Labels**
`forecasting`, `evaluation`, `research`

**Depends on**
- None

**Summary**
Define a stable offline evaluation contract for forecasting quality in prediction markets. The benchmark must compare MCA outputs against raw market probability, not only against internal model variants.

**Problem**
Current evaluation paths exist, but promotion criteria are not yet anchored to a committed benchmark contract and there are no committed benchmark artifacts proving current-state performance.

**Scope**
- Extend [pipelines/evaluate_tsfm_offline.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/pipelines/evaluate_tsfm_offline.py)
- Update [docs/ops/prd2-offline-eval.md](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/docs/ops/prd2-offline-eval.md)

**Acceptance Criteria**
- Offline eval compares `market_prob`, current MCA baseline, and future model variants in one output schema.
- Metrics include Brier, log-loss, ECE, pinball, coverage, mean width, hit rate, avg pnl, and avg abs edge.
- Output supports deterministic segmentation by `category`, `liquidity_bucket`, `horizon_hours`, and `tte_bucket`.
- Seeded reruns are reproducible.

**Implementation Checklist**
- Add market-baseline rows to eval outputs.
- Add a stable artifact schema version.
- Add segment-level output files or columns.
- Document exact pass/fail thresholds.
- Add tests for determinism and required columns.

**Validation**
- Run offline eval twice with identical seed and verify identical outputs.
- Verify benchmark artifacts are understandable without inspecting code.

---

## T2. Add Richer Walk-Forward and Event-Holdout Reporting

**Title**
`feat(backtest): add richer walk-forward and event-holdout reporting for forecasting quality`

**Labels**
`forecasting`, `evaluation`

**Depends on**
- T1

**Summary**
Upgrade offline backtest reporting so it shows worst-fold behavior, edge quality, and pass/fail status against promotion gates instead of only pooled averages.

**Scope**
- Extend [pipelines/generate_backtest_report.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/pipelines/generate_backtest_report.py)
- Update [docs/ops/backtest-reporting.md](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/docs/ops/backtest-reporting.md)

**Acceptance Criteria**
- Report includes worst-fold, median-fold, and pooled metrics.
- Event-holdout reporting is first-class, not an afterthought.
- Summary markdown clearly states pass/fail against promotion thresholds.
- No-leakage split behavior is covered by tests.

**Implementation Checklist**
- Add worst-fold summary artifact.
- Add segment and edge-threshold slices.
- Add report summary with decision field: `go`, `conditional_go`, or `no_go`.
- Add tests for walk-forward split correctness and embargo behavior if used.

**Validation**
- Use a synthetic dataset to verify fold construction and stable output layout.
- Confirm that a deliberately degraded model fails the report gate.

---

## T3. Densify the Resolved Training Dataset

**Title**
`feat(dataset): densify resolved training dataset with multiple as-of samples per market`

**Labels**
`forecasting`, `data`, `research`

**Depends on**
- T1

**Summary**
Turn the resolved training dataset into a more useful supervised table by emitting multiple lifecycle snapshots per market rather than only one selected row per horizon.

**Scope**
- Extend [pipelines/build_resolved_training_dataset.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/pipelines/build_resolved_training_dataset.py)
- Update [docs/ops/resolved-dataset.md](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/docs/ops/resolved-dataset.md)
- Add tests in [tests/unit/test_resolved_training_dataset.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/tests/unit/test_resolved_training_dataset.py)

**Acceptance Criteria**
- Dataset builder supports deterministic multi-sample selection across a market lifecycle.
- Each row includes `snapshot_gap_minutes`, `age_since_open`, `tte_bucket`, and `platform` where available.
- Sampling policy is documented and reproducible.
- Tests prove no future leakage.

**Implementation Checklist**
- Define allowed sampling modes, such as fixed cadence or capped per-horizon sampling.
- Add lifecycle metadata columns.
- Add leakage and duplicate-row tests.
- Document row semantics and expected row count growth.

**Validation**
- Compare old and new dataset sizes and segment coverage.
- Verify no rows are created after the label becomes known.

---

## T4. Expand Market Microstructure Features

**Title**
`feat(features): add prediction-market microstructure features for forecasting`

**Labels**
`forecasting`, `features`, `research`

**Depends on**
- T3

**Summary**
Expand deterministic feature generation beyond the current small set to include multi-window, gap-aware, and time-to-resolution-aware market features.

**Scope**
- Extend [features/build_features.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/features/build_features.py)
- Extend [pipelines/build_feature_frame.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/pipelines/build_feature_frame.py)
- Update [docs/ops/feature-specs-v1.md](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/docs/ops/feature-specs-v1.md)

**Acceptance Criteria**
- Add multi-window returns and volatility features.
- Add acceleration, reversal, and gap/staleness features.
- Add nonlinear TTE transforms and TTE buckets.
- All new features have leakage rules and unit coverage.

**Implementation Checklist**
- Define feature names and formulas in the spec.
- Implement deterministic sorting and missing-value policy.
- Add unit tests for short series, zero denominators, and timestamp gaps.
- Add initial ablation hooks for offline comparison.

**Validation**
- Run feature ablations against current baseline.
- Reject any feature group that materially hurts high-liquidity segments.

---

## T5. Add Event-Consensus and Cross-Market Disagreement Features

**Title**
`feat(features): add event-consensus and cross-market disagreement signals`

**Labels**
`forecasting`, `features`, `research`

**Depends on**
- T3
- T4

**Summary**
Use related markets tied to the same event or entity graph to build consensus and disagreement features that can identify where one market is stale or mispriced relative to nearby contracts.

**Scope**
- Extend [pipelines/build_feature_frame.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/pipelines/build_feature_frame.py)
- Reuse [registry/build_registry.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/registry/build_registry.py)
- Add tests in [tests/unit/test_feature_stage.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/tests/unit/test_feature_stage.py)

**Acceptance Criteria**
- Related markets can produce consensus/disagreement features using only as-of data.
- Missing related markets degrade gracefully.
- Cross-market features are deterministic and leakage-safe.
- Backtests expose lift by segment for these features.

**Implementation Checklist**
- Define event-level grouping logic.
- Add agreement, dispersion, and lag-to-consensus features.
- Add tests for sparse and conflicting related-market inputs.
- Add documentation for fallback behavior when registry linkage is weak.

**Validation**
- Verify no future timestamps are consulted.
- Confirm features are stable across reruns.

---

## T6. Strengthen External Enrichment

**Title**
`feat(features): strengthen external news and poll enrichment for forecasting`

**Labels**
`forecasting`, `features`, `research`

**Depends on**
- T3

**Summary**
Improve the current local-file enrichment so it provides stronger prediction-market signals based on recency, relevance, and match quality rather than only shallow counts.

**Scope**
- Extend [features/external_enrichment.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/features/external_enrichment.py)
- Add tests in [tests/unit/test_external_enrichment.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/tests/unit/test_external_enrichment.py)

**Acceptance Criteria**
- News and poll enrichment expose recency-aware and match-quality-aware features.
- Query matching remains deterministic.
- Sparse or missing enrichment data does not break training workflows.
- Tests cover empty, noisy, and partially matching inputs.

**Implementation Checklist**
- Normalize query-term handling.
- Add rolling recency and density features.
- Add match-strength metrics for polls and news.
- Document expected CSV contracts and fallback behavior.

**Validation**
- Verify feature generation on empty and malformed auxiliary files.
- Confirm enriched columns are stable under reruns.

---

## T7. Add a Residual Model Training Track

**Title**
`feat(model): train residual model against market probability baseline`

**Labels**
`forecasting`, `modeling`, `research`

**Depends on**
- T1
- T3
- T4
- T6

**Summary**
Move beyond the current ridge-style direct predictor by training a model that learns the residual between market probability and realized outcome.

**Scope**
- Extend [pipelines/train_resolved_model.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/pipelines/train_resolved_model.py)
- Update [docs/ops/resolved-model-training.md](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/docs/ops/resolved-model-training.md)
- Add tests in [tests/unit/test_train_resolved_model.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/tests/unit/test_train_resolved_model.py)

**Acceptance Criteria**
- Training supports a residual target based on `market_prob`.
- Horizon-specific models or horizon interactions are supported.
- Output artifacts compare raw market, ridge, residual, and blended predictions.
- New model beats raw market and current ridge on time split and event holdout.

**Implementation Checklist**
- Add residual-target option and artifact naming.
- Keep current ridge path as baseline.
- Add evaluation summary for direct vs residual targets.
- Add tests for serialization and prediction bounds.

**Validation**
- Run benchmark contract from T1.
- Do not promote if gains disappear in high-liquidity short-TTE segments.

---

## T8. Add Feature Ablation and Model Comparison Workflow

**Title**
`feat(research): add feature ablation and model comparison workflow`

**Labels**
`forecasting`, `research`, `evaluation`

**Depends on**
- T4
- T5
- T6
- T7

**Summary**
Make it easy to measure which feature groups and model variants are actually driving out-of-sample lift.

**Scope**
- Extend [pipelines/train_resolved_model.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/pipelines/train_resolved_model.py)
- Extend [pipelines/generate_backtest_report.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/pipelines/generate_backtest_report.py)

**Acceptance Criteria**
- Workflow supports feature-group ablation runs.
- Output ranks feature groups and model variants by out-of-sample lift.
- Results show aggregate and worst-segment effects.
- Output is stable enough for CI or release gating.

**Implementation Checklist**
- Define feature groups.
- Add repeatable ablation runner and artifact schema.
- Report lift vs market and vs prior MCA baseline.
- Add tests for artifact structure and deterministic ordering.

**Validation**
- Confirm that weak feature groups are visible and removable.
- Verify outputs can be consumed without manual spreadsheet work.

---

## T9. Make Conformal Calibration Segment-Aware

**Title**
`feat(calibration): add segment-aware conformal calibration and drift checks`

**Labels**
`forecasting`, `calibration`

**Depends on**
- T7

**Summary**
Upgrade conformal calibration to operate by segment so MCA can target the markets where calibration error is structurally different.

**Scope**
- Extend [calibration/conformal.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/calibration/conformal.py)
- Extend [pipelines/update_conformal_calibration.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/pipelines/update_conformal_calibration.py)
- Extend [calibration/drift.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/calibration/drift.py)
- Add tests in [tests/unit/test_conformal_pipeline_integration.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/tests/unit/test_conformal_pipeline_integration.py)

**Acceptance Criteria**
- Conformal state can be fit and applied by `liquidity_bucket` and `tte_bucket` at minimum.
- Drift checks report segment-level calibration failures.
- Low-sample segments fall back safely.
- Coverage improves without excessive interval widening.

**Implementation Checklist**
- Add segment key definition and storage format.
- Add fallback path for insufficient data.
- Extend metrics and logging for segment-level calibration.
- Add tests for update, skip, and fallback behavior.

**Validation**
- Verify target coverage is closer after calibration.
- Ensure no segment remains persistently undercovered without surfacing an alert.

---

## T10. Add Evidence-Based Model Routing to the Live Service

**Title**
`feat(runtime): route forecast requests by evidence-backed model policy`

**Labels**
`forecasting`, `runtime`, `prd2`

**Depends on**
- T7
- T9

**Summary**
Allow live forecast serving to route between market-only, residual-model, and TSFM paths based on offline evidence and segment suitability.

**Scope**
- Extend [runners/tsfm_service.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/runners/tsfm_service.py)
- Reuse [runners/baselines.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/runners/baselines.py)
- Update [docs/prd2-implementation-status.md](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/docs/prd2-implementation-status.md)
- Add tests in [tests/unit/test_tsfm_runner_service.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/tests/unit/test_tsfm_runner_service.py)

**Acceptance Criteria**
- Runtime can choose among at least three forecast routes: market-only, residual baseline, and TSFM.
- Response metadata includes the chosen route and fallback reason.
- Existing failure fallback behavior is preserved.
- No route can be turned on without offline evidence artifacts.

**Implementation Checklist**
- Define route policy config.
- Add response metadata fields for route selection.
- Add tests for route eligibility and fallback stability.
- Document rollout rules and restrictions.

**Validation**
- Verify route selection is deterministic for the same request.
- Confirm degraded and baseline-only service modes still work.

---

## T11. Add Forecast-Quality Monitoring and Promotion Gates

**Title**
`feat(monitoring): add forecast-quality dashboards and promotion gates`

**Labels**
`forecasting`, `monitoring`, `ops`

**Depends on**
- T1
- T9
- T10

**Summary**
Add production monitoring that distinguishes model-quality regression from runtime regression and define explicit rollback thresholds for both.

**Scope**
- Extend [monitoring/grafana/calibration-quality-dashboard.json](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/monitoring/grafana/calibration-quality-dashboard.json)
- Extend [monitoring/prometheus/calibration_quality_alerts.rules.yaml](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/monitoring/prometheus/calibration_quality_alerts.rules.yaml)
- Update [docs/ops/calibration-drift-runbook.md](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/docs/ops/calibration-drift-runbook.md)

**Acceptance Criteria**
- Dashboard shows quality by segment, model route, and edge bucket.
- Alerts cover Brier regression, ECE regression, undercoverage, and fallback-rate spikes.
- Runbook ties rollback actions to exact thresholds.
- Monitoring distinguishes inference outage from model-quality failure.

**Implementation Checklist**
- Add panels for route-level quality.
- Add Prometheus rules for model-quality regressions.
- Update runbook with rollback and investigation workflow.
- Verify metrics naming is stable and documented.

**Validation**
- Simulate one quality regression and one runtime regression and confirm alerts differ.
- Verify dashboard supports canary vs baseline comparison.

---

## T12. Commit Baseline Research Artifact Pack

**Title**
`docs(research): commit baseline artifact pack for forecasting improvement program`

**Labels**
`forecasting`, `documentation`, `research`

**Depends on**
- T1
- T2
- T7

**Summary**
Create a reproducible baseline artifact pack so later improvements can be compared to a fixed starting point.

**Scope**
- Update [docs/ops/prd2-offline-eval.md](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/docs/ops/prd2-offline-eval.md)
- Update [docs/ops/resolved-model-training.md](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/docs/ops/resolved-model-training.md)

**Acceptance Criteria**
- Repo contains one documented baseline artifact pack for current MCA forecasting quality.
- Pack includes dataset summary, benchmark summary, backtest report, and promotion decision.
- Commands and output locations are documented.
- Future model changes can reference this pack as the comparison baseline.

**Implementation Checklist**
- Generate baseline artifacts.
- Document generation commands.
- Record pass/fail result against benchmark gates.
- Link artifact pack from ops docs.

**Validation**
- A reviewer can regenerate the pack from documented commands.
- Artifact pack is sufficient to compare future runs without ad hoc analysis.

---

## Suggested Issue Creation Order

1. T1
2. T2
3. T3
4. T4
5. T6
6. T5
7. T7
8. T8
9. T9
10. T10
11. T11
12. T12

## Suggested GitHub Metadata

**Epic**
`Improve MCA forecasting quality for prediction markets`

**Milestones**
- `Forecast Benchmark`
- `Dataset and Features`
- `Model and Calibration`
- `Runtime and Monitoring`

**Recommended Project Fields**
- Status
- Priority
- Depends On
- Owner
- Validation Status
