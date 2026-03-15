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

set_priority() {
  local issue_number="$1"
  local priority_label="$2"
  local -a cmd=(
    gh issue edit "${issue_number}"
    --repo "${REPO}"
    --remove-label "priority:p0"
    --remove-label "priority:p1"
    --remove-label "priority:p2"
    --add-label "${priority_label}"
  )

  if [[ "${MODE}" == "preview" ]]; then
    printf '[preview] issue #%s -> %s\n' "${issue_number}" "${priority_label}"
    printf '  %q' "${cmd[@]}"
    printf '\n\n'
  else
    printf '[priority] issue #%s -> %s\n' "${issue_number}" "${priority_label}"
    "${cmd[@]}"
    printf '\n'
  fi
}

ensure_priority_labels() {
  ensure_label "priority:p0" "B60205" "Critical path work needed before broader forecasting rollout"
  ensure_label "priority:p1" "FBCA04" "Important follow-on work with high impact"
  ensure_label "priority:p2" "0E8A16" "Useful supporting work after the main path is established"
}

ensure_priority_labels

set_priority "${EPIC}" "priority:p0"
set_priority "${T1}" "priority:p0"
set_priority "${T2}" "priority:p0"
set_priority "${T3}" "priority:p0"
set_priority "${T4}" "priority:p1"
set_priority "${T5}" "priority:p1"
set_priority "${T6}" "priority:p1"
set_priority "${T7}" "priority:p0"
set_priority "${T8}" "priority:p1"
set_priority "${T9}" "priority:p1"
set_priority "${T10}" "priority:p1"
set_priority "${T11}" "priority:p1"
set_priority "${T12}" "priority:p2"
