# Calibration Drift Runbook

## Overview

This runbook covers operational procedures when the calibration drift detection
system flags a significant base-rate shift in prediction markets.

## Alert Reference

| Alert                        | Condition                         | Severity |
|------------------------------|-----------------------------------|----------|
| `CalibrationDriftDetected`   | `calibration_drift_detected == 1` for 15m | warning  |
| `CalibrationBrierHigh`       | `calibration_brier_score > 0.25` for 30m  | warning  |
| `CalibrationECEHigh`         | `calibration_ece > 0.10` for 30m          | warning  |
| `ConformalCoverageLow`       | `calibration_conformal_coverage < 0.75` for 1h | warning |
| `ConformalCoverageCritical`  | `calibration_conformal_coverage < 0.65` for 30m | critical |

## Triage Steps

### 1. Verify the Alert

```bash
# Check current gauge values
curl -s http://localhost:8000/metrics | grep calibration_

# Check the calibration quality endpoint
curl -s http://localhost:8000/metrics/calibration_quality | python -m json.tool
```

### 2. Identify the Drift Source

Open the Grafana **Calibration Quality** dashboard:

- **Calibration Score Trends** panel: Is Brier increasing monotonically?
- **Conformal Coverage** panel: Has coverage dropped below the target line (0.80)?
- **Drift Status** panel: Shows `DRIFT` or `Stable`

Check the drift analysis windows:

```bash
# Inspect the pipeline's last drift result
cat data/derived/calibration/drift_result.json | python -m json.tool
```

Look for:
- `base_rate_swing` > 0.15 → strong distribution shift
- `brier_trend_increasing` = true → progressive model degradation
- Per-window `base_rate` and `mean_pred` divergence

### 3. Determine Root Cause

| Symptom | Likely Cause | Action |
|---------|-------------|--------|
| `base_rate_swing` > 0.15, single-window spike | External event moved market outcomes | Wait for mean-reversion; monitor |
| `base_rate_swing` > 0.15, sustained | Population-level shift in prediction targets | Trigger recalibration |
| `brier_trend_increasing`, low swing | Model degradation without distribution shift | Check feature pipeline, data freshness |
| High ECE, normal Brier | Systematic over/under-confidence | Recalibrate; check conformal |

### 4. Response Actions

#### 4a. Automatic Conformal Recalibration

The daily pipeline automatically triggers conformal recalibration when drift is
detected. Verify the conformal stage ran successfully:

```bash
# Check latest pipeline run
cat data/derived/checkpoints/daily-*.json | python -m json.tool | grep -A5 conformal
```

#### 4b. Manual Conformal Recalibration

If the automatic update failed or you need immediate recalibration:

```bash
python -m pipelines.update_conformal_calibration \
  --input data/derived/calibration/conformal_history.jsonl \
  --state-path data/derived/calibration/conformal_state.json \
  --target-coverage 0.80 \
  --window-size 2000 \
  --min-samples 100
```

#### 4c. Manual Prediction Recalibration

For severe drift where conformal adjustment is insufficient:

```python
from calibration.metrics import base_rate_drift, recalibrate_predictions

# Get drift details
drift = base_rate_drift(rows, time_key="ts")
latest_window = drift["windows"][-1]

# Apply base-rate shift correction
adjusted = recalibrate_predictions(
    preds, labels,
    recent_base_rate=latest_window["base_rate"],
    recent_n=latest_window["sample_size"],
)
```

### 5. Escalation Criteria

| Condition | Action |
|-----------|--------|
| `ConformalCoverageCritical` firing | Page on-call; immediate investigation |
| Drift persists > 24h after recalibration | Escalate to ML team lead |
| Brier > 0.35 for > 1h | Consider model retraining |
| Multiple concurrent alerts | Incident review; check data pipeline health |

### 6. Resolution

- Verify Brier and ECE return to normal range on Grafana dashboard
- Verify conformal coverage recovers to >= 0.80
- Verify `calibration_drift_detected` returns to 0
- Update the incident log if drift was caused by a known external event
