#!/usr/bin/env bash
set -euo pipefail

REPO="${GITHUB_REPO:-tollama/Market-Calibration-Agent}"
MODE="${1:-preview}"

if [[ "${MODE}" != "preview" && "${MODE}" != "--execute" ]]; then
  echo "Usage: $0 [preview|--execute]" >&2
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI is required" >&2
  exit 1
fi

TMPDIR="$(mktemp -d)"
trap 'rm -rf "${TMPDIR}"' EXIT

DOC_URL="https://github.com/tollama/Market-Calibration-Agent/blob/main/docs/ops/forecasting-improvement-github-issues.md"
PACK_URL="https://github.com/tollama/Market-Calibration-Agent/blob/main/docs/ops/forecasting-improvement-issue-templates.md"

EPIC=1
T1=2
T2=3
T3=4
T4=5
T5=6
T6=7
T7=8
T8=9
T9=10
T10=11
T11=12
T12=13

edit_issue() {
  local issue_number="$1"
  local body_file="$2"
  local -a cmd=(
    gh issue edit "${issue_number}"
    --repo "${REPO}"
    --body-file "${body_file}"
  )

  if [[ "${MODE}" == "preview" ]]; then
    printf '[preview] issue #%s\n' "${issue_number}"
    printf '  %q' "${cmd[@]}"
    printf '\n  body-file=%s\n\n' "${body_file}"
  else
    printf '[edit] issue #%s\n' "${issue_number}"
    "${cmd[@]}"
    printf '\n'
  fi
}

cat > "${TMPDIR}/epic.md" <<EOF
## Summary

Improve MCA forecasting quality for prediction markets through benchmark hardening, resolved-dataset improvements, feature expansion, stronger supervised modeling, segment-aware calibration, evidence-based runtime routing, and production monitoring.

## Goal

Produce forecasts that outperform raw market probabilities and the current MCA baseline on offline evaluation, while preserving calibration and operational safety.

## Execution Order

1. #${T1} benchmark contract
2. #${T2} richer backtest reporting
3. #${T3} densify resolved dataset
4. #${T4} microstructure features
5. #${T6} external enrichment
6. #${T5} event-consensus features
7. #${T7} residual model track
8. #${T8} ablation workflow
9. #${T9} segment-aware conformal
10. #${T10} runtime routing
11. #${T11} monitoring and promotion gates
12. #${T12} baseline artifact pack

## Child Issues

- [ ] #${T1} Build Forecasting Benchmark Contract
- [ ] #${T2} Add Richer Walk-Forward and Event-Holdout Reporting
- [ ] #${T3} Densify the Resolved Training Dataset
- [ ] #${T4} Expand Market Microstructure Features
- [ ] #${T5} Add Event-Consensus and Cross-Market Disagreement Features
- [ ] #${T6} Strengthen External Enrichment
- [ ] #${T7} Add a Residual Model Training Track
- [ ] #${T8} Add Feature Ablation and Model Comparison Workflow
- [ ] #${T9} Make Conformal Calibration Segment-Aware
- [ ] #${T10} Add Evidence-Based Model Routing to the Live Service
- [ ] #${T11} Add Forecast-Quality Monitoring and Promotion Gates
- [ ] #${T12} Commit Baseline Research Artifact Pack

## Success Metrics

- Define and measure Brier and log-loss improvement versus raw market baseline
- Preserve calibration quality and interval coverage
- Require time-split and event-holdout evidence before rollout
- Report results by category, liquidity, TTE, and horizon segments

## References

- Canonical issue bodies: ${DOC_URL}
- Issue pack: ${PACK_URL}
EOF

cat > "${TMPDIR}/t1.md" <<EOF
Parent epic: #${EPIC}

Blocks: #${T2}, #${T3}, #${T7}, #${T11}, #${T12}

## Summary

Define a stable offline evaluation contract for forecasting quality in prediction markets. The benchmark must compare MCA outputs against raw market probability, not only against internal model variants.

## Acceptance Criteria

- Offline eval compares market baseline, current MCA baseline, and future model variants
- Metrics include Brier, log-loss, ECE, pinball, coverage, mean width, hit rate, avg pnl, and avg abs edge
- Outputs support deterministic segmentation by category, liquidity bucket, horizon hours, and TTE bucket
- Seeded reruns are reproducible

## Target Files

- pipelines/evaluate_tsfm_offline.py
- docs/ops/prd2-offline-eval.md

## References

- ${DOC_URL}
EOF

cat > "${TMPDIR}/t2.md" <<EOF
Parent epic: #${EPIC}

Depends on: #${T1}

Blocks: #${T12}

## Summary

Upgrade offline backtest reporting so it shows worst-fold behavior, edge quality, and pass/fail status against promotion gates instead of only pooled averages.

## Acceptance Criteria

- Report includes worst-fold, median-fold, and pooled metrics
- Event-holdout reporting is first-class
- Summary markdown clearly states pass/fail against promotion thresholds
- No-leakage split behavior is covered by tests

## Target Files

- pipelines/generate_backtest_report.py
- docs/ops/backtest-reporting.md

## References

- ${DOC_URL}
EOF

cat > "${TMPDIR}/t3.md" <<EOF
Parent epic: #${EPIC}

Depends on: #${T1}

Blocks: #${T4}, #${T5}, #${T6}, #${T7}

## Summary

Turn the resolved training dataset into a more useful supervised table by emitting multiple lifecycle snapshots per market rather than only one selected row per horizon.

## Acceptance Criteria

- Builder supports deterministic multi-sample selection across market lifecycles
- Rows include snapshot gap, age since open, TTE bucket, and platform where available
- Sampling policy is documented and reproducible
- Tests prove no future leakage

## Target Files

- pipelines/build_resolved_training_dataset.py
- docs/ops/resolved-dataset.md
- tests/unit/test_resolved_training_dataset.py

## References

- ${DOC_URL}
EOF

cat > "${TMPDIR}/t4.md" <<EOF
Parent epic: #${EPIC}

Depends on: #${T3}

Blocks: #${T5}, #${T7}, #${T8}

## Summary

Expand deterministic feature generation beyond the current small set to include multi-window, gap-aware, and time-to-resolution-aware market features.

## Acceptance Criteria

- Add multi-window returns and volatility features
- Add acceleration, reversal, and gap/staleness features
- Add nonlinear TTE transforms and TTE buckets
- All new features have leakage rules and unit coverage

## Target Files

- features/build_features.py
- pipelines/build_feature_frame.py
- docs/ops/feature-specs-v1.md

## References

- ${DOC_URL}
EOF

cat > "${TMPDIR}/t5.md" <<EOF
Parent epic: #${EPIC}

Depends on: #${T3}, #${T4}

Blocks: #${T8}

## Summary

Use related markets tied to the same event or entity graph to build consensus and disagreement features that can identify where one market is stale or mispriced relative to nearby contracts.

## Acceptance Criteria

- Related markets can produce consensus/disagreement features using only as-of data
- Missing related markets degrade gracefully
- Cross-market features are deterministic and leakage-safe
- Backtests expose lift by segment

## Target Files

- pipelines/build_feature_frame.py
- registry/build_registry.py
- tests/unit/test_feature_stage.py

## References

- ${DOC_URL}
EOF

cat > "${TMPDIR}/t6.md" <<EOF
Parent epic: #${EPIC}

Depends on: #${T3}

Blocks: #${T7}, #${T8}

## Summary

Improve local-file enrichment so it provides stronger prediction-market signals based on recency, relevance, and match quality rather than only shallow counts.

## Acceptance Criteria

- News and poll enrichment expose recency-aware and match-quality-aware features
- Query matching remains deterministic
- Sparse or missing enrichment data does not break training workflows
- Tests cover empty, noisy, and partially matching inputs

## Target Files

- features/external_enrichment.py
- tests/unit/test_external_enrichment.py

## References

- ${DOC_URL}
EOF

cat > "${TMPDIR}/t7.md" <<EOF
Parent epic: #${EPIC}

Depends on: #${T1}, #${T3}, #${T4}, #${T6}

Blocks: #${T8}, #${T9}, #${T10}, #${T12}

## Summary

Move beyond the current ridge-style direct predictor by training a model that learns the residual between market probability and realized outcome.

## Acceptance Criteria

- Training supports a residual target based on market probability
- Horizon-specific models or horizon interactions are supported
- Output artifacts compare raw market, ridge, residual, and blended predictions
- New model beats raw market and current ridge on time split and event holdout

## Target Files

- pipelines/train_resolved_model.py
- docs/ops/resolved-model-training.md
- tests/unit/test_train_resolved_model.py

## References

- ${DOC_URL}
EOF

cat > "${TMPDIR}/t8.md" <<EOF
Parent epic: #${EPIC}

Depends on: #${T4}, #${T5}, #${T6}, #${T7}

## Summary

Make it easy to measure which feature groups and model variants are actually driving out-of-sample lift.

## Acceptance Criteria

- Workflow supports feature-group ablation runs
- Output ranks feature groups and model variants by out-of-sample lift
- Results show aggregate and worst-segment effects
- Output is stable enough for CI or release gating

## Target Files

- pipelines/train_resolved_model.py
- pipelines/generate_backtest_report.py

## References

- ${DOC_URL}
EOF

cat > "${TMPDIR}/t9.md" <<EOF
Parent epic: #${EPIC}

Depends on: #${T7}

Blocks: #${T10}, #${T11}

## Summary

Upgrade conformal calibration to operate by segment so MCA can target the markets where calibration error is structurally different.

## Acceptance Criteria

- Conformal state can be fit and applied by liquidity bucket and TTE bucket at minimum
- Drift checks report segment-level calibration failures
- Low-sample segments fall back safely
- Coverage improves without excessive interval widening

## Target Files

- calibration/conformal.py
- pipelines/update_conformal_calibration.py
- calibration/drift.py
- tests/unit/test_conformal_pipeline_integration.py

## References

- ${DOC_URL}
EOF

cat > "${TMPDIR}/t10.md" <<EOF
Parent epic: #${EPIC}

Depends on: #${T7}, #${T9}

Blocks: #${T11}

## Summary

Allow live forecast serving to route between market-only, residual-model, and TSFM paths based on offline evidence and segment suitability.

## Acceptance Criteria

- Runtime can choose among market-only, residual baseline, and TSFM routes
- Response metadata includes chosen route and fallback reason
- Existing failure fallback behavior is preserved
- No route can be enabled without offline evidence artifacts

## Target Files

- runners/tsfm_service.py
- runners/baselines.py
- docs/prd2-implementation-status.md
- tests/unit/test_tsfm_runner_service.py

## References

- ${DOC_URL}
EOF

cat > "${TMPDIR}/t11.md" <<EOF
Parent epic: #${EPIC}

Depends on: #${T1}, #${T9}, #${T10}

## Summary

Add production monitoring that distinguishes model-quality regression from runtime regression and define explicit rollback thresholds for both.

## Acceptance Criteria

- Dashboard shows quality by segment, model route, and edge bucket
- Alerts cover Brier regression, ECE regression, undercoverage, and fallback-rate spikes
- Runbook ties rollback actions to exact thresholds
- Monitoring distinguishes inference outage from model-quality failure

## Target Files

- monitoring/grafana/calibration-quality-dashboard.json
- monitoring/prometheus/calibration_quality_alerts.rules.yaml
- docs/ops/calibration-drift-runbook.md

## References

- ${DOC_URL}
EOF

cat > "${TMPDIR}/t12.md" <<EOF
Parent epic: #${EPIC}

Depends on: #${T1}, #${T2}, #${T7}

## Summary

Create a reproducible baseline artifact pack so later improvements can be compared to a fixed starting point.

## Acceptance Criteria

- Repo contains one documented baseline artifact pack for current MCA forecasting quality
- Pack includes dataset summary, benchmark summary, backtest report, and promotion decision
- Commands and output locations are documented
- Future model changes can reference this pack as the comparison baseline

## Target Files

- docs/ops/prd2-offline-eval.md
- docs/ops/resolved-model-training.md

## References

- ${DOC_URL}
EOF

edit_issue "${EPIC}" "${TMPDIR}/epic.md"
edit_issue "${T1}" "${TMPDIR}/t1.md"
edit_issue "${T2}" "${TMPDIR}/t2.md"
edit_issue "${T3}" "${TMPDIR}/t3.md"
edit_issue "${T4}" "${TMPDIR}/t4.md"
edit_issue "${T5}" "${TMPDIR}/t5.md"
edit_issue "${T6}" "${TMPDIR}/t6.md"
edit_issue "${T7}" "${TMPDIR}/t7.md"
edit_issue "${T8}" "${TMPDIR}/t8.md"
edit_issue "${T9}" "${TMPDIR}/t9.md"
edit_issue "${T10}" "${TMPDIR}/t10.md"
edit_issue "${T11}" "${TMPDIR}/t11.md"
edit_issue "${T12}" "${TMPDIR}/t12.md"
