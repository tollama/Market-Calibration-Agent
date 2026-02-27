# Market Calibration Agent

Market Calibration Agent is a production-oriented toolkit for monitoring, calibrating, and serving prediction-market probabilities from live and historical data.

It combines data ingestion, calibration metrics, trust scoring, alerting, and forecast serving into one system.

## What This App Can Do

- Ingest Polymarket market/event data from REST, websocket, and subgraph sources.
- Build deterministic feature frames and cutoff snapshots for calibration workflows.
- Compute calibration metrics (Brier, log-loss, ECE, segments) and trust scores.
- Generate alert feeds with configurable thresholds and gating policies.
- Serve a read-only API for scoreboards, alerts, market summaries, and postmortems.
- Serve TSFM forecast inference with runtime hardening:
  - auth/rate-limit guard
  - cache + stale-if-error
  - circuit breaker + degradation modes
  - baseline fallback and interval sanity checks
- Run a Streamlit live demo UI for operational visibility.

## Typical Use Cases

- Quant/research teams validating market probability quality over time.
- Ops teams monitoring market reliability and high-severity alert candidates.
- Platform teams exposing calibrated market artifacts via API.
- Model teams comparing baseline vs TSFM interval behavior in controlled rollouts.

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install uv
uv pip sync requirements.lock
pip install -e .[dev]

# For the live demo runtime (API + Streamlit UI):
pip install -e .[server,demo]
```

## Run

```bash
# bootstrap sanity check: load all config files
python -c "from pathlib import Path; import yaml; [yaml.safe_load(p.read_text()) for p in Path('configs').glob('*.yaml')]; print('Config load OK')"
```

## Test

```bash
pip install -e .[test]
pytest
```

## Dependency locking (required)

This repository uses a committed frozen lockfile:
- `requirements.lock`
- Install with `uv pip sync requirements.lock` (or `uv pip sync --system requirements.lock` in CI/non-venv environments)

See [dependency lockfile strategy](docs/dependency-lockfile-strategy.md).

## TSFM forecast API hardening notes

- Inbound auth: set `TSFM_FORECAST_API_TOKEN` (or `AUTH_TOKEN`) to a non-placeholder secret (`demo-token`/`tsfm-dev-token`/`changeme` 등 금지), and call `/tsfm/forecast` with `Authorization: Bearer <token>` (or `X-API-Key: <token>`).
- Runtime integration tokens: live tollama calls read `TOLLAMA_TOKEN` when calling downstream model runtime.
- Forecast request constraints and fallback behavior are documented in [TSFM Forecast Operational Policy](docs/ops/tsfm-forecast-operational-policy.md).
- Hardening preflight command is documented in [TSFM Hardening Gate](docs/ops/tsfm-hardening-gate.md):

```bash
API_BASE=http://127.0.0.1:8100 TSFM_FORECAST_API_TOKEN=<real-secret> scripts/rollout_hardening_gate.sh
```

### KPI 계약 N-run 리포트 (Go/No-Go)

```bash
python3 scripts/kpi_contract_report.py \
  --input scripts/examples/kpi_runs_sample.jsonl \
  --n 5 \
  --stage canary \
  --thresholds configs/kpi_contract_thresholds.json \
  --output-json artifacts/ops/kpi_contract_report_sample.json
```

### 사전조건/실행/검증/실패시 대응

- **사전조건**: Python 3.11+, `requirements.lock` 동기화 상태 점검, 실운영 토큰 미설정/placeholder 확인.
- **실행**: 위 하드닝 게이트 문서의 환경변수를 설정 후 실행.
- **검증**: `artifacts/rollout_gate/rollout_hardening_gate_summary.json`의 `overall_status`가 `success`인지 확인하고, step 로그를 통해 실패 지점을 확인.
- **실패시 대응**: 토큰·포트·Tollama 경로·레이트리밋 실패를 순차 점검 후 수정하고 게이트를 재실행.

## Config Files

- `configs/default.yaml` - application, data, and calibration defaults.
- `configs/alerts.yaml` - alert thresholds, cooldowns, and channels.
- `configs/models.yaml` - model profiles and feature settings.
- `configs/logging.yaml` - Python logging configuration.
- `configs/tsfm_runtime.yaml` - TSFM runtime/adapter thresholds and circuit breaker.
- `configs/tsfm_models.yaml` - TSFM model list and metadata.

## Architecture / Notes

- [Architecture overview](docs/architecture-overview.md) - system components, runtime flows, storage contracts, and reliability controls
- [Technology stack](docs/technology-stack.md) - runtime dependencies, config model, external integrations, and CI/tooling
- [Implementation details](docs/implementation-details.md) - module-level behavior across connectors, pipelines, API, and TSFM service internals
- [PRD1 구현 상태 (I-01~I-20)](docs/prd1-implementation-status.md) - 최신 판정, 남은 갭, 실행 백로그
- [PRD2 TSFM Runner 구현 상태](docs/prd2-implementation-status.md) - tollama 기반 TSFM runner, fallback, post-processing, conformal, 운영 가이드
- [PRD2 Dashboards (TSFM observability)](docs/ops/prd2-dashboards.md) - Grafana dashboard import/provisioning and panel expectations
- [Conformal calibration ops guide](docs/conformal-ops.md) - rolling updater, state persistence, manual/cron runbook
- [Label resolver defaults and precedence](docs/label-resolver-defaults.md)
- [Single App 운영 Runbook](docs/ops/single-app-ops-runbook.md) - ADMIN 토큰 로테이션, compose 운영 기준, dryRun=false 안전 카나리
- [KPI 계약(Go/No-Go)](docs/ops/kpi-contract-go-nogo.md) - Brier/ECE/realized slippage/execution fail rate 기준 + N-run 자동 판정 리포트
