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
BRIEF_URL="https://github.com/tollama/Market-Calibration-Agent/blob/main/docs/ops/forecasting-improvement-execution-brief.md"

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

ensure_label() {
  local name="$1"
  local color="$2"
  local description="$3"
  local -a cmd=(
    gh label create "${name}"
    --repo "${REPO}"
    --color "${color}"
    --description "${description}"
    --force
  )

  if [[ "${MODE}" == "preview" ]]; then
    printf '[preview] label %s\n' "${name}"
    printf '  %q' "${cmd[@]}"
    printf '\n\n'
  else
    printf '[label] %s\n' "${name}"
    "${cmd[@]}"
    printf '\n'
  fi
}

set_labels() {
  local issue_number="$1"
  shift
  local -a labels=("$@")
  local -a cmd=(
    gh issue edit "${issue_number}"
    --repo "${REPO}"
  )
  for label in "${labels[@]}"; do
    cmd+=(--add-label "${label}")
  done

  if [[ "${MODE}" == "preview" ]]; then
    printf '[preview] labels issue #%s\n' "${issue_number}"
    printf '  %q' "${cmd[@]}"
    printf '\n\n'
  else
    printf '[labels] issue #%s\n' "${issue_number}"
    "${cmd[@]}"
    printf '\n'
  fi
}

edit_epic() {
  local body_file="$1"
  local -a cmd=(
    gh issue edit "${EPIC}"
    --repo "${REPO}"
    --body-file "${body_file}"
  )

  if [[ "${MODE}" == "preview" ]]; then
    printf '[preview] epic body\n'
    printf '  %q' "${cmd[@]}"
    printf '\n  body-file=%s\n\n' "${body_file}"
  else
    printf '[edit] epic body\n'
    "${cmd[@]}"
    printf '\n'
  fi
}

ensure_milestone_labels() {
  ensure_label "milestone:forecast-benchmark" "0366D6" "Benchmark contract and reporting work"
  ensure_label "milestone:dataset-and-features" "0E8A16" "Dataset quality and feature engineering work"
  ensure_label "milestone:model-and-calibration" "5319E7" "Model training, ablation, and calibration work"
  ensure_label "milestone:runtime-and-monitoring" "B60205" "Runtime routing, monitoring, and artifact pack work"
}

cat > "${TMPDIR}/epic.md" <<EOF
## Summary

Improve MCA forecasting quality for prediction markets through benchmark hardening, resolved-dataset improvements, feature expansion, stronger supervised modeling, segment-aware calibration, evidence-based runtime routing, and production monitoring.

## Goal

Produce forecasts that outperform raw market probabilities and the current MCA baseline on offline evaluation, while preserving calibration and operational safety.

## Backlog Groups

### Milestone 1: Forecast Benchmark

- #${T1} benchmark contract
- #${T2} richer walk-forward and event-holdout reporting

### Milestone 2: Dataset and Features

- #${T3} densify resolved dataset
- #${T4} microstructure features
- #${T6} external enrichment
- #${T5} event-consensus and cross-market disagreement

### Milestone 3: Model and Calibration

- #${T7} residual model track
- #${T8} feature ablation and model comparison
- #${T9} segment-aware conformal calibration

### Milestone 4: Runtime and Monitoring

- #${T10} evidence-based runtime routing
- #${T11} monitoring and promotion gates
- #${T12} baseline artifact pack

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
- Execution brief: ${BRIEF_URL}
EOF

ensure_milestone_labels

edit_epic "${TMPDIR}/epic.md"

set_labels "${EPIC}" \
  "milestone:forecast-benchmark"
set_labels "${T1}" \
  "milestone:forecast-benchmark"
set_labels "${T2}" \
  "milestone:forecast-benchmark"
set_labels "${T3}" \
  "milestone:dataset-and-features"
set_labels "${T4}" \
  "milestone:dataset-and-features"
set_labels "${T5}" \
  "milestone:dataset-and-features"
set_labels "${T6}" \
  "milestone:dataset-and-features"
set_labels "${T7}" \
  "milestone:model-and-calibration"
set_labels "${T8}" \
  "milestone:model-and-calibration"
set_labels "${T9}" \
  "milestone:model-and-calibration"
set_labels "${T10}" \
  "milestone:runtime-and-monitoring"
set_labels "${T11}" \
  "milestone:runtime-and-monitoring"
set_labels "${T12}" \
  "milestone:runtime-and-monitoring"
