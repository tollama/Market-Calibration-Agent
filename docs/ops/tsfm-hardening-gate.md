# TSFM Hardening Gate

This document captures the PRD2 hardening gate used to validate service security and API health before/alongside rollout.

## Purpose

Run `scripts/rollout_hardening_gate.sh` to execute a compact but strict sequence of checks:

- Live demo smoke
- Live demo security checks (auth + rate limit)
- PRD2 runtime metrics smoke
- TSFM benchmark sanity check
- OpenAPI contract smoke

## 사전조건

- Python 3.11+ installed (script default `PYTHON_BIN=python3.11`).
- `scripts/rollout_hardening_gate.sh` has execute permission.
- A real token is provided: `TSFM_FORECAST_API_TOKEN` (preferred) or `AUTH_TOKEN`.
  - Placeholder-like values are rejected by both script and API: `changeme`, `changemeplease`, `tsfm-dev-token`, `dev-token`, `demo-token`, `example`, `your-token`, `placeholder`, or empty string.
- Optional: no port conflict on target API port, or an already healthy API is reachable at `API_BASE`.
- If local derived artifacts are needed by smoke scripts, allow temp/derived writes in repo path.

## 실행

- Set variables as needed:

  - `PYTHON_BIN` (default `python3.11`)
  - `API_HOST` (default `127.0.0.1`)
  - `API_PORT` (default `8100`)
  - `API_BASE` (defaults to `http://$API_HOST:$API_PORT`)
  - `TSFM_FORECAST_API_TOKEN` or `AUTH_TOKEN`
  - `ROLLOUT_REPORT_DIR` (default `artifacts/rollout_gate`)
  - `ROLLOUT_GATE_DRY_RUN=1` (optional; logs command intent without execution)
  - `ROLLOUT_PERF_REQUESTS`, `ROLLOUT_PERF_UNIQUE`, `ROLLOUT_PERF_LATENCY_MS`, `ROLLOUT_PERF_P95_MS`, `ROLLOUT_PERF_CYCLE_S`
  - `MARKET_ID` (default `mkt-smoke-001`)
  - `HEALTH_TIMEOUT_SEC` (default `45`)

- Run:

```bash
scripts/rollout_hardening_gate.sh
```

## 검증

- Script exits `0` only when all checks succeed.
- Generated artifacts under `ROLLOUT_REPORT_DIR` and `.../logs`:
  - `rollout_hardening_gate_summary.json` (overall gate summary)
  - `live_demo_smoke_report.md`
  - `live_demo_security_report.md`
  - `logs/live_demo_smoke.log`
  - `logs/live_demo_security.log`
  - `logs/runtime_metrics_smoke.log`
  - `logs/perf_benchmark_full.log` (includes tee+validate trace for benchmark step)
  - `logs/perf_bench.log`
  - `logs/perf_bench_result.json`
  - `logs/openapi_smoke.log`
  - `logs/openapi_smoke_report.json`
- Common failure mode validation:
  - `ROLLOUT_GATE_DRY_RUN=1` shows each step command and log path.
  - `ROLLOUT` summary file status should be `success` when no step fails.

## 실패시 대응

- **토큰/환경 확인 실패**
  - `Missing or placeholder ...` 출력 시 토큰 값을 실제 비밀값으로 교체 후 재실행.
- **API 준비 실패**
  - `api.log` 또는 step log를 보고 포트/의존성/마이그레이션 이슈를 확인.
  - 실행 전 `API_BASE`가 이미 사용 중인 healthy 서비스인지 확인하면 게이트는 기존 서버로 자동 진행 가능.
- **체크 단계 실패**
  - `rollout_hardening_gate_summary.json`의 `steps[].name`으로 실패 단계 확인.
  - 대응 실패 로그는 해당 로그 파일을 기준으로 조치 후 `scripts/rollout_hardening_gate.sh` 재실행.

## Related docs

- `docs/ops/tsfm-canary-rollout-runbook.md`
- `scripts/rollout_hardening_gate.sh`
- `scripts/openapi_smoke.py`
