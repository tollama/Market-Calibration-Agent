# Low-Confidence Period Runbook

## Overview

Markets with fewer than 30 prediction observations are flagged as
**low-confidence**. During periods when many markets are in this state
(e.g., after onboarding a wave of new markets or during low-activity
periods), calibration metrics become unreliable and alert severities
are automatically dampened.

## How Low-Confidence Works

### Detection

```python
from calibration.metrics import assess_confidence

result = assess_confidence(sample_size=15)
# → {"sample_size": 15, "low_confidence": True, "min_confidence_samples": 30}
```

The threshold (`min_confidence_samples`) is configurable in `configs/default.yaml`:

```yaml
calibration:
  min_confidence_samples: 30
```

### Alert Severity Dampening

When `low_confidence=True` on a market row, alert severity is automatically
downgraded one level:

| Original Severity | Dampened Severity |
|-------------------|-------------------|
| HIGH              | MED               |
| MED               | FYI               |
| FYI               | FYI (unchanged)   |

Dampened alerts include `"dampened_by_low_confidence": true` in their evidence
dict so that consumers can trace the decision.

The dampening behavior is controlled by the `dampen_low_confidence` parameter
in `build_alert_feed_rows()` (default: `True`).

### Prometheus Monitoring

| Metric | Description |
|--------|-------------|
| `calibration_low_confidence_markets` | Count of markets with `low_confidence=True` |
| `calibration_total_markets` | Total market count |

The ratio `calibration_low_confidence_markets / calibration_total_markets` is
monitored by the `HighLowConfidenceMarketRatio` alert rule (fires when > 30%).

## Alert Reference

| Alert | Condition | Severity |
|-------|-----------|----------|
| `HighLowConfidenceMarketRatio` | > 30% markets are low-confidence for 1h | warning |

## Triage Steps

### 1. Check Current State

```bash
# API endpoint
curl -s http://localhost:8000/metrics/calibration_quality | python -m json.tool

# Look for:
#   "total_market_count": 50,
#   "low_confidence_market_count": 18,

# Prometheus metrics
curl -s http://localhost:8000/metrics | grep calibration_low_confidence
```

### 2. Identify Affected Markets

```bash
# Check scoreboard for low_confidence markets
curl -s "http://localhost:8000/scoreboard?window=90d" | \
  python -c "import sys,json; d=json.load(sys.stdin); \
  lc=[i for i in d['items'] if i.get('low_confidence')]; \
  print(f'{len(lc)}/{d[\"total\"]} low-confidence'); \
  [print(f'  {i[\"market_id\"]}: n={i.get(\"sample_size\",\"?\")}') for i in lc[:10]]"
```

### 3. Determine Root Cause

| Symptom | Likely Cause | Action |
|---------|-------------|--------|
| Many new markets with n < 30 | Recent market onboarding wave | Expected; wait for data accumulation |
| Existing markets dropped to n < 30 | Data pipeline issue; ingestion gap | Investigate pipeline logs |
| Ratio > 50% | System-wide data availability problem | Check data sources; page on-call |
| Ratio > 30% sustained > 48h | Slow market activity | Consider lowering threshold or extending window |

### 4. Response Actions

#### 4a. Expected Low-Confidence Period (New Markets)

No action required. Low-confidence flags will resolve naturally as
observations accumulate. Verify:

- Daily pipeline is running and ingesting new data
- Market observation counts are trending upward
- Alerts are being dampened correctly (not generating false HIGH alerts)

#### 4b. Unexpected Low-Confidence Period (Pipeline Issue)

1. Check daily pipeline logs for ingestion failures
2. Verify data source connectivity
3. Check for timestamp/schema issues in raw data

```bash
# Check latest pipeline run
cat data/derived/checkpoints/daily-*.json | python -m json.tool
```

#### 4c. Adjusting the Threshold

If the default threshold (30) is too aggressive for your use case:

```yaml
# configs/default.yaml
calibration:
  min_confidence_samples: 20  # Lower threshold
```

**Warning**: Lowering the threshold increases the risk of unreliable
metrics being treated as trustworthy.

### 5. Interpreting Dampened Alerts

When reviewing alerts during a low-confidence period:

- **Dampened alerts** (`dampened_by_low_confidence: true`): Treat these as
  informational. The underlying signal may be real but lacks statistical
  support.
- **Non-dampened alerts**: These come from markets with sufficient data.
  Treat at face value.

### 6. Resolution

The low-confidence period resolves when:

- Market observation counts exceed `min_confidence_samples`
- `calibration_low_confidence_markets` gauge decreases
- `HighLowConfidenceMarketRatio` alert stops firing

No manual intervention is needed for natural resolution.
