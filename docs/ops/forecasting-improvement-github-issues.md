# Forecasting Improvement GitHub Issues

This document contains GitHub-ready issue bodies for the forecasting improvement program.

---

## Epic

**Title**
`epic(forecasting): improve MCA forecasting quality for prediction markets`

**Labels**
`forecasting`, `prediction-markets`, `research`

**Body**

## Summary

Improve MCA forecasting quality with a repo-native program covering benchmark definition, resolved-dataset quality, feature expansion, stronger supervised modeling, segment-aware calibration, evidence-based runtime routing, and production monitoring.

## Goal

Produce forecasts that outperform raw market probabilities and the current MCA baseline on offline evaluation, while preserving calibration and operational safety.

## Problem

MCA already has strong calibration plumbing, backtesting scaffolding, and TSFM runtime hardening, but the supervised forecasting layer is still intentionally lightweight. The current system lacks a committed benchmark artifact pack proving where MCA currently beats the market, where it does not, and which model path should be promoted by segment.

## Scope

- In scope: benchmark contract, resolved dataset improvements, feature expansion, residual-model training, segment-aware conformal calibration, runtime route policy, monitoring, baseline artifact pack
- In scope: prediction-market-specific evaluation against raw market probability
- Out of scope: unrelated UI redesign, new exchange integrations unrelated to forecasting quality

## Success Metrics

- [ ] Brier improvement versus raw market baseline is defined and measured
- [ ] Log-loss improvement versus current MCA baseline is defined and measured
- [ ] ECE and interval coverage guardrails are defined
- [ ] Performance is reported by `category`, `liquidity_bucket`, `tte_bucket`, and `horizon_hours`
- [ ] Promotion requires time split and event-holdout evidence

## Milestones

- [ ] Forecast Benchmark
- [ ] Dataset and Features
- [ ] Model and Calibration
- [ ] Runtime and Monitoring

## Child Issues

- [ ] T1 Build Forecasting Benchmark Contract
- [ ] T2 Add Richer Walk-Forward and Event-Holdout Reporting
- [ ] T3 Densify the Resolved Training Dataset
- [ ] T4 Expand Market Microstructure Features
- [ ] T5 Add Event-Consensus and Cross-Market Disagreement Features
- [ ] T6 Strengthen External Enrichment
- [ ] T7 Add a Residual Model Training Track
- [ ] T8 Add Feature Ablation and Model Comparison Workflow
- [ ] T9 Make Conformal Calibration Segment-Aware
- [ ] T10 Add Evidence-Based Model Routing to the Live Service
- [ ] T11 Add Forecast-Quality Monitoring and Promotion Gates
- [ ] T12 Commit Baseline Research Artifact Pack

## Risks

- Risk: improvements may overfit illiquid or niche segments
- Mitigation: require segment-level reports and worst-fold review before promotion
- Risk: calibration gains may come from interval widening instead of better forecasts
- Mitigation: track width and coverage jointly

## Validation Plan

- [ ] Produce reproducible offline benchmark artifacts
- [ ] Require event-holdout and walk-forward validation
- [ ] Review segment-level regressions before rollout
- [ ] Gate runtime rollout on offline evidence

## References

- [forecasting-improvement-issue-templates.md](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/docs/ops/forecasting-improvement-issue-templates.md)
- [prd2-offline-eval.md](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/docs/ops/prd2-offline-eval.md)
- [resolved-model-training.md](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/docs/ops/resolved-model-training.md)

---

## T1 Build Forecasting Benchmark Contract

**Title**
`feat(eval): define forecasting benchmark contract for market vs model quality`

**Labels**
`forecasting`, `evaluation`, `research`

**Depends on**
- None

**Body**

## Summary

Define a stable offline evaluation contract for forecasting quality in prediction markets. The benchmark must compare MCA outputs against raw market probability, not only against internal model variants.

## Problem

Evaluation paths exist, but promotion criteria are not anchored to a committed benchmark contract and the repo does not yet contain a reference benchmark artifact pack.

## Scope

- In scope: extend offline eval schema and benchmark docs
- In scope: market-vs-model comparison, segment outputs, and deterministic artifacts
- Out of scope: changing live inference routing in this ticket

## Target Files

- [pipelines/evaluate_tsfm_offline.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/pipelines/evaluate_tsfm_offline.py)
- [docs/ops/prd2-offline-eval.md](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/docs/ops/prd2-offline-eval.md)

## Acceptance Criteria

- [ ] Offline eval compares `market_prob`, current MCA baseline, and future model variants in one contract
- [ ] Metrics include Brier, log-loss, ECE, pinball, coverage, mean width, hit rate, avg pnl, and avg abs edge
- [ ] Outputs support deterministic segmentation by `category`, `liquidity_bucket`, `horizon_hours`, and `tte_bucket`
- [ ] Seeded reruns are reproducible

## Implementation Checklist

- [ ] Add market-baseline rows to eval outputs
- [ ] Add stable artifact schema versioning
- [ ] Add segment-level output fields or artifacts
- [ ] Document pass/fail thresholds
- [ ] Add tests for determinism and required columns

## Validation

- [ ] Run eval twice with the same seed and verify identical outputs
- [ ] Verify output is understandable without code inspection

---

## T2 Add Richer Walk-Forward and Event-Holdout Reporting

**Title**
`feat(backtest): add richer walk-forward and event-holdout reporting for forecasting quality`

**Labels**
`forecasting`, `evaluation`

**Depends on**
- T1

**Body**

## Summary

Upgrade offline backtest reporting so it shows worst-fold behavior, edge quality, and pass/fail status against promotion gates instead of only pooled averages.

## Problem

Current reports are data-first, but they do not yet clearly expose worst-fold performance, benchmark decisions, or edge-quality slices needed for forecasting promotion.

## Scope

- In scope: richer report artifacts and benchmark decision summaries
- In scope: walk-forward and event-holdout comparability
- Out of scope: new model training logic

## Target Files

- [pipelines/generate_backtest_report.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/pipelines/generate_backtest_report.py)
- [docs/ops/backtest-reporting.md](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/docs/ops/backtest-reporting.md)

## Acceptance Criteria

- [ ] Report includes worst-fold, median-fold, and pooled metrics
- [ ] Event-holdout reporting is first-class
- [ ] Summary markdown clearly states pass/fail against promotion thresholds
- [ ] No-leakage split behavior is covered by tests

## Implementation Checklist

- [ ] Add worst-fold summary artifact
- [ ] Add segment and edge-threshold slices
- [ ] Add report-level decision field
- [ ] Add tests for split correctness and embargo behavior

## Validation

- [ ] Confirm a deliberately degraded model fails the report gate
- [ ] Verify stable layout for downstream review

---

## T3 Densify the Resolved Training Dataset

**Title**
`feat(dataset): densify resolved training dataset with multiple as-of samples per market`

**Labels**
`forecasting`, `data`, `research`

**Depends on**
- T1

**Body**

## Summary

Turn the resolved training dataset into a more useful supervised table by emitting multiple lifecycle snapshots per market rather than only one selected row per horizon.

## Problem

The current dataset builder leaves a large amount of market trajectory information unused and limits the ceiling of any supervised forecaster.

## Scope

- In scope: deterministic multi-sample lifecycle selection
- In scope: richer row metadata for TTE, staleness, and platform
- Out of scope: model changes in this ticket

## Target Files

- [pipelines/build_resolved_training_dataset.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/pipelines/build_resolved_training_dataset.py)
- [docs/ops/resolved-dataset.md](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/docs/ops/resolved-dataset.md)
- [tests/unit/test_resolved_training_dataset.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/tests/unit/test_resolved_training_dataset.py)

## Acceptance Criteria

- [ ] Builder supports deterministic multi-sample selection across market lifecycles
- [ ] Rows include `snapshot_gap_minutes`, `age_since_open`, `tte_bucket`, and `platform` where available
- [ ] Sampling policy is documented and reproducible
- [ ] Tests prove no future leakage

## Implementation Checklist

- [ ] Define lifecycle sampling modes
- [ ] Add lifecycle metadata columns
- [ ] Add no-leakage and duplicate-row tests
- [ ] Document expected row growth and row semantics

## Validation

- [ ] Compare old and new dataset sizes and segment coverage
- [ ] Verify no rows are created after label availability

---

## T4 Expand Market Microstructure Features

**Title**
`feat(features): add prediction-market microstructure features for forecasting`

**Labels**
`forecasting`, `features`, `research`

**Depends on**
- T3

**Body**

## Summary

Expand deterministic feature generation beyond the current small set to include multi-window, gap-aware, and time-to-resolution-aware market features.

## Problem

The current feature set is useful but too narrow for the structure of prediction markets, especially around staleness, nonlinear TTE effects, and short-horizon behavior.

## Scope

- In scope: deterministic feature expansion with leakage guards
- In scope: feature spec updates and unit coverage
- Out of scope: model selection in this ticket

## Target Files

- [features/build_features.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/features/build_features.py)
- [pipelines/build_feature_frame.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/pipelines/build_feature_frame.py)
- [docs/ops/feature-specs-v1.md](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/docs/ops/feature-specs-v1.md)

## Acceptance Criteria

- [ ] Add multi-window returns and volatility features
- [ ] Add acceleration, reversal, and gap/staleness features
- [ ] Add nonlinear TTE transforms and TTE buckets
- [ ] All new features have leakage rules and unit coverage

## Implementation Checklist

- [ ] Define feature names and formulas in the spec
- [ ] Implement deterministic missing-value policy
- [ ] Add unit tests for short series, zero denominators, and timestamp gaps
- [ ] Add initial ablation hooks

## Validation

- [ ] Run feature ablations against current baseline
- [ ] Reject feature groups that materially hurt high-liquidity segments

---

## T5 Add Event-Consensus and Cross-Market Disagreement Features

**Title**
`feat(features): add event-consensus and cross-market disagreement signals`

**Labels**
`forecasting`, `features`, `research`

**Depends on**
- T3
- T4

**Body**

## Summary

Use related markets tied to the same event or entity graph to build consensus and disagreement features that can identify where one market is stale or mispriced relative to nearby contracts.

## Problem

Prediction markets often reveal signal through disagreement across related contracts, but MCA does not currently encode that structure in the core feature frame.

## Scope

- In scope: event-level and related-market features using as-of data only
- In scope: graceful degradation when related-market coverage is sparse
- Out of scope: live routing changes

## Target Files

- [pipelines/build_feature_frame.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/pipelines/build_feature_frame.py)
- [registry/build_registry.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/registry/build_registry.py)
- [tests/unit/test_feature_stage.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/tests/unit/test_feature_stage.py)

## Acceptance Criteria

- [ ] Related markets can produce consensus/disagreement features using only as-of data
- [ ] Missing related markets degrade gracefully
- [ ] Cross-market features are deterministic and leakage-safe
- [ ] Backtests expose lift by segment for these features

## Implementation Checklist

- [ ] Define event-level grouping logic
- [ ] Add agreement, dispersion, and lag-to-consensus features
- [ ] Add tests for sparse and conflicting related-market inputs
- [ ] Document fallback behavior when registry linkage is weak

## Validation

- [ ] Verify no future timestamps are consulted
- [ ] Confirm feature stability across reruns

---

## T6 Strengthen External Enrichment

**Title**
`feat(features): strengthen external news and poll enrichment for forecasting`

**Labels**
`forecasting`, `features`, `research`

**Depends on**
- T3

**Body**

## Summary

Improve local-file enrichment so it provides stronger prediction-market signals based on recency, relevance, and match quality rather than only shallow counts.

## Problem

Current enrichment is intentionally light and likely leaves useful external structure under-modeled.

## Scope

- In scope: deterministic enrichment upgrades and tests
- In scope: better recency and match-strength features
- Out of scope: online retrieval systems

## Target Files

- [features/external_enrichment.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/features/external_enrichment.py)
- [tests/unit/test_external_enrichment.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/tests/unit/test_external_enrichment.py)

## Acceptance Criteria

- [ ] News and poll enrichment expose recency-aware and match-quality-aware features
- [ ] Query matching remains deterministic
- [ ] Sparse or missing enrichment data does not break training workflows
- [ ] Tests cover empty, noisy, and partially matching inputs

## Implementation Checklist

- [ ] Normalize query-term handling
- [ ] Add recency and density features
- [ ] Add match-strength metrics
- [ ] Document CSV contracts and fallback behavior

## Validation

- [ ] Verify empty and malformed auxiliary files do not break workflows
- [ ] Confirm enriched columns are stable under reruns

---

## T7 Add a Residual Model Training Track

**Title**
`feat(model): train residual model against market probability baseline`

**Labels**
`forecasting`, `modeling`, `research`

**Depends on**
- T1
- T3
- T4
- T6

**Body**

## Summary

Move beyond the current ridge-style direct predictor by training a model that learns the residual between market probability and realized outcome.

## Problem

For prediction markets, learning where the market is wrong is usually a better framing than relearning the market from scratch. MCA does not yet support that as a first-class training path.

## Scope

- In scope: residual-target training, artifacts, and comparisons
- In scope: horizon-specific or horizon-aware modeling
- Out of scope: live service routing in this ticket

## Target Files

- [pipelines/train_resolved_model.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/pipelines/train_resolved_model.py)
- [docs/ops/resolved-model-training.md](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/docs/ops/resolved-model-training.md)
- [tests/unit/test_train_resolved_model.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/tests/unit/test_train_resolved_model.py)

## Acceptance Criteria

- [ ] Training supports a residual target based on `market_prob`
- [ ] Horizon-specific models or horizon interactions are supported
- [ ] Output artifacts compare raw market, ridge, residual, and blended predictions
- [ ] New model beats raw market and current ridge on time split and event holdout

## Implementation Checklist

- [ ] Add residual-target option and artifact naming
- [ ] Keep current ridge path as baseline
- [ ] Add evaluation summary for direct vs residual targets
- [ ] Add tests for serialization and prediction bounds

## Validation

- [ ] Run benchmark contract from T1
- [ ] Do not promote if gains disappear in high-liquidity short-TTE segments

---

## T8 Add Feature Ablation and Model Comparison Workflow

**Title**
`feat(research): add feature ablation and model comparison workflow`

**Labels**
`forecasting`, `research`, `evaluation`

**Depends on**
- T4
- T5
- T6
- T7

**Body**

## Summary

Make it easy to measure which feature groups and model variants are actually driving out-of-sample lift.

## Problem

Without a repeatable ablation workflow, MCA risks accumulating features and model complexity without clear evidence of marginal value.

## Scope

- In scope: feature-group ablations and model comparison artifacts
- In scope: stable outputs suitable for CI or release review
- Out of scope: runtime serving changes

## Target Files

- [pipelines/train_resolved_model.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/pipelines/train_resolved_model.py)
- [pipelines/generate_backtest_report.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/pipelines/generate_backtest_report.py)

## Acceptance Criteria

- [ ] Workflow supports feature-group ablation runs
- [ ] Output ranks feature groups and model variants by out-of-sample lift
- [ ] Results show aggregate and worst-segment effects
- [ ] Output is stable enough for CI or release gating

## Implementation Checklist

- [ ] Define feature groups
- [ ] Add repeatable ablation runner and artifact schema
- [ ] Report lift vs market and vs prior MCA baseline
- [ ] Add tests for artifact structure and deterministic ordering

## Validation

- [ ] Confirm weak feature groups are visible and removable
- [ ] Verify outputs are reviewable without spreadsheet cleanup

---

## T9 Make Conformal Calibration Segment-Aware

**Title**
`feat(calibration): add segment-aware conformal calibration and drift checks`

**Labels**
`forecasting`, `calibration`

**Depends on**
- T7

**Body**

## Summary

Upgrade conformal calibration to operate by segment so MCA can target the markets where calibration error is structurally different.

## Problem

Aggregate calibration can hide persistent segment-level failures, especially across liquidity and TTE regimes.

## Scope

- In scope: segment-aware conformal state, application, and drift reporting
- In scope: safe fallback for low-sample segments
- Out of scope: changing benchmark contract in this ticket

## Target Files

- [calibration/conformal.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/calibration/conformal.py)
- [pipelines/update_conformal_calibration.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/pipelines/update_conformal_calibration.py)
- [calibration/drift.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/calibration/drift.py)
- [tests/unit/test_conformal_pipeline_integration.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/tests/unit/test_conformal_pipeline_integration.py)

## Acceptance Criteria

- [ ] Conformal state can be fit and applied by `liquidity_bucket` and `tte_bucket` at minimum
- [ ] Drift checks report segment-level calibration failures
- [ ] Low-sample segments fall back safely
- [ ] Coverage improves without excessive interval widening

## Implementation Checklist

- [ ] Add segment key definition and storage format
- [ ] Add low-sample fallback path
- [ ] Extend metrics and logging for segment-level calibration
- [ ] Add tests for update, skip, and fallback behavior

## Validation

- [ ] Verify target coverage is closer after calibration
- [ ] Ensure persistent undercoverage is surfaced

---

## T10 Add Evidence-Based Model Routing to the Live Service

**Title**
`feat(runtime): route forecast requests by evidence-backed model policy`

**Labels**
`forecasting`, `runtime`, `prd2`

**Depends on**
- T7
- T9

**Body**

## Summary

Allow live forecast serving to route between market-only, residual-model, and TSFM paths based on offline evidence and segment suitability.

## Problem

MCA has runtime hardening, but it does not yet have an evidence-based policy for which forecast path should be used in which segment.

## Scope

- In scope: route policy, metadata, and tests
- In scope: preserving existing fallback and degradation behavior
- Out of scope: redefining auth or API shape beyond route metadata

## Target Files

- [runners/tsfm_service.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/runners/tsfm_service.py)
- [runners/baselines.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/runners/baselines.py)
- [docs/prd2-implementation-status.md](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/docs/prd2-implementation-status.md)
- [tests/unit/test_tsfm_runner_service.py](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/tests/unit/test_tsfm_runner_service.py)

## Acceptance Criteria

- [ ] Runtime can choose among market-only, residual baseline, and TSFM routes
- [ ] Response metadata includes chosen route and fallback reason
- [ ] Existing failure fallback behavior is preserved
- [ ] No route can be enabled without offline evidence artifacts

## Implementation Checklist

- [ ] Define route policy config
- [ ] Add route metadata fields
- [ ] Add tests for route eligibility and fallback stability
- [ ] Document rollout rules and restrictions

## Validation

- [ ] Verify route selection is deterministic for the same request
- [ ] Confirm degraded and baseline-only modes still work

---

## T11 Add Forecast-Quality Monitoring and Promotion Gates

**Title**
`feat(monitoring): add forecast-quality dashboards and promotion gates`

**Labels**
`forecasting`, `monitoring`, `ops`

**Depends on**
- T1
- T9
- T10

**Body**

## Summary

Add production monitoring that distinguishes model-quality regression from runtime regression and define explicit rollback thresholds for both.

## Problem

Without route-aware and segment-aware quality monitoring, MCA cannot safely promote improved forecasters into production.

## Scope

- In scope: dashboards, alerts, and rollback rules
- In scope: separating quality regression from infra regression
- Out of scope: unrelated operational dashboards

## Target Files

- [monitoring/grafana/calibration-quality-dashboard.json](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/monitoring/grafana/calibration-quality-dashboard.json)
- [monitoring/prometheus/calibration_quality_alerts.rules.yaml](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/monitoring/prometheus/calibration_quality_alerts.rules.yaml)
- [docs/ops/calibration-drift-runbook.md](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/docs/ops/calibration-drift-runbook.md)

## Acceptance Criteria

- [ ] Dashboard shows quality by segment, model route, and edge bucket
- [ ] Alerts cover Brier regression, ECE regression, undercoverage, and fallback-rate spikes
- [ ] Runbook ties rollback actions to exact thresholds
- [ ] Monitoring distinguishes inference outage from model-quality failure

## Implementation Checklist

- [ ] Add route-level quality panels
- [ ] Add Prometheus rules for model-quality regressions
- [ ] Update runbook with rollback and investigation workflow
- [ ] Verify metrics naming is stable and documented

## Validation

- [ ] Simulate one quality regression and one runtime regression and confirm alerts differ
- [ ] Verify dashboard supports canary vs baseline comparison

---

## T12 Commit Baseline Research Artifact Pack

**Title**
`docs(research): commit baseline artifact pack for forecasting improvement program`

**Labels**
`forecasting`, `documentation`, `research`

**Depends on**
- T1
- T2
- T7

**Body**

## Summary

Create a reproducible baseline artifact pack so later improvements can be compared to a fixed starting point.

## Problem

The repo does not yet contain a canonical forecasting baseline pack that later model changes can be measured against.

## Scope

- In scope: baseline artifacts, commands, docs, and promotion decision
- In scope: reference point for all future forecasting changes
- Out of scope: ongoing automation of future research runs

## Target Files

- [docs/ops/prd2-offline-eval.md](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/docs/ops/prd2-offline-eval.md)
- [docs/ops/resolved-model-training.md](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/docs/ops/resolved-model-training.md)

## Acceptance Criteria

- [ ] Repo contains one documented baseline artifact pack for current MCA forecasting quality
- [ ] Pack includes dataset summary, benchmark summary, backtest report, and promotion decision
- [ ] Commands and output locations are documented
- [ ] Future model changes can reference this pack as the comparison baseline

## Implementation Checklist

- [ ] Generate baseline artifacts
- [ ] Document generation commands
- [ ] Record pass/fail result against benchmark gates
- [ ] Link artifact pack from ops docs

## Validation

- [ ] A reviewer can regenerate the pack from documented commands
- [ ] Artifact pack is sufficient to compare future runs without ad hoc analysis

