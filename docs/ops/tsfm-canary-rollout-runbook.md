# TSFM Canary Rollout Runbook (5% -> 25% -> 100%)

This runbook operationalizes PRD2 load-test rollout gates and rollback policy.

Source of truth:
- `.openclaw-plans/PRD2_LOADTEST_SPEC.md` sections 6, 7, 8
- `monitoring/prometheus/tsfm_canary_alerts.rules.yaml`
- `scripts/evaluate_tsfm_canary_gate.py`

## 1) Promotion gates

- **Gate C (canary_5)**: 30 minutes clean window
- **Gate D (canary_25)**: 60 minutes clean window
- **Gate E (full_100)**: 24 hours clean window

A clean window requires:
- `p95_latency_ms <= 300`
- `error_rate <= 0.01`
- `invalid_output_rate == 0`
- `fallback_rate <= 0.08` (canary_5)
- `fallback_rate <= 0.10` (canary_25/full_100)
- no rollback trigger fired

## 2) Exact rollback triggers (immediate)

Rollback to baseline-only if **ANY** occurs:
1. `p95 > 400ms` for **2 consecutive 5-minute windows**
2. `error_rate > 0.02` for **any 5-minute window**
3. `invalid_output_rate > 0` (any safety violation)
4. `fallback_rate > 0.20` for **15 minutes** (outside planned incident drill)
5. `breaker_open_rate > 0.30` for **15 minutes**

## 3) Rollback actions

1. Freeze promotion; stop traffic increase immediately.
2. Shift TSFM traffic to 0% (baseline-only).
3. Open incident and preserve logs for affected windows:
   - request ids
   - fallback reasons
   - breaker state transitions
   - output validation failures
4. Keep rollback state until post-incident review signs off.

## 4) Step-by-step rollout checklist

### Pre-flight (before 5%)
- [ ] Latest commit deployed with monitoring rules loaded.
- [ ] Dashboard has p95/error/fallback/breaker/invalid-output panels.
- [ ] `scripts/evaluate_tsfm_canary_gate.py` dry-run passes on fresh metrics snapshot.
- [ ] On-call owner assigned.

### Promote to 5%
- [ ] Set routing to 5% TSFM.
- [ ] Observe for 30 minutes.
- [ ] Run gate evaluator with stage `canary_5`.
- [ ] If PASS, continue; if FAIL, rollback.

### Promote to 25%
- [ ] Set routing to 25% TSFM.
- [ ] Observe for 60 minutes.
- [ ] Run gate evaluator with stage `canary_25`.
- [ ] If PASS, continue; if FAIL, rollback.

### Promote to 100%
- [ ] Set routing to 100% TSFM.
- [ ] Observe for 24 hours.
- [ ] Run gate evaluator with stage `full_100`.
- [ ] If PASS, rollout complete; if FAIL, rollback.

## 5) Gate evaluation command

```bash
python3 scripts/evaluate_tsfm_canary_gate.py \
  --input scripts/examples/canary_gate_pass.json \
  --stage canary_5
```

Expected output fields:
- `gate_passed` (boolean)
- `rollback_triggered` (boolean)
- `rollback_reasons` (array)
- `gate_fail_reasons` (array)

## 6) Metrics JSON shape expected by evaluator

```json
{
  "window_minutes": 5,
  "metrics": {
    "p95_latency_ms": [240, 260, 255, 250, 245, 252],
    "error_rate": [0.002, 0.001, 0.003, 0.002, 0.001, 0.002],
    "fallback_rate": [0.04, 0.05, 0.06, 0.05, 0.04, 0.05],
    "breaker_open_rate": [0.01, 0.02, 0.01, 0.00, 0.01, 0.00],
    "invalid_output_rate": [0, 0, 0, 0, 0, 0]
  }
}
```

All arrays must be aligned by 5-minute window.
