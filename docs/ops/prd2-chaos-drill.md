# PRD2 Chaos Drill Runbook (Tollama Failure Modes)

## Purpose
Exercise PRD2 degraded-mode behavior by simulating tollama runtime failures and confirming:
- deterministic fallback to baseline forecasts,
- safe response envelopes (`0 <= q10 <= q50 <= q90 <= 1`),
- circuit breaker short-circuiting after repeated failures.

## Failure modes covered
- `timeout`
- `5xx`
- `connection_drop`

All drills are local/staging-safe and use mock fault injection, not production runtime changes.

## Prerequisites
```bash
cd /Users/ychoi/Documents/GitHub/Market-Calibration-Agent
python -m pip install -e ".[dev]"
```

## 1) Run integration chaos tests
```bash
pytest -q tests/integration/test_prd2_chaos_drills.py
```

Expected pass criteria:
- all tests pass,
- each mode forces fallback (`meta.fallback_used=true`, `meta.runtime=baseline`),
- repeated calls with same signal inputs produce identical `yhat_q`,
- circuit breaker opens and avoids additional tollama calls once threshold is reached.

## 2) Run script-based drill (operator-facing)
The drill script supports env-driven mode selection.

### Timeout drill
```bash
CHAOS_MODE=timeout python scripts/chaos/prd2_tollama_chaos_drill.py
```

### 5xx drill
```bash
CHAOS_MODE=5xx python scripts/chaos/prd2_tollama_chaos_drill.py
```

### Connection drop drill
```bash
CHAOS_MODE=connection_drop python scripts/chaos/prd2_tollama_chaos_drill.py
```

Optional:
- `CHAOS_REPEATS` (default `2`) for repeatability checks.

Expected script output signals:
- `fallback_all: true`
- `baseline_all: true`
- `deterministic: true`
- `safety_errors: []`
- process exit code `0`

## Failure handling
If any drill fails:
1. Capture command output and mode.
2. Confirm no local code/config drift in `runners/tsfm_service.py` safety guards.
3. Re-run with `CHAOS_REPEATS=3` to confirm non-determinism vs transient issue.
4. Open incident ticket with the failing mode and fallback metadata.

## Notes
- Drills intentionally do not require live tollama.
- Live runtime validation remains covered by `tests/integration/test_tollama_live_integration.py`.
