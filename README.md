# Market Calibration Agent

Bootstrap repository for calibrating market probabilities from streaming and historical market data.

## MVP-1

- Ingest market data via HTTP and websocket feeds.
- Normalize and store tabular snapshots with `pandas`/`pyarrow`.
- Run a baseline calibration pipeline from configurable YAML settings.
- Emit threshold-based alerts using configurable rules.

## MVP-2

- Add multiple model profiles and model selection by market regime.
- Introduce richer alert routing and suppression windows.
- Add service endpoints for health, metrics, and calibration outputs.
- Expand test coverage for config loading, calibration logic, and alerting.

## Quick Start

## Performance Improvements

We recently conducted a profiling session on the core entry points (`api/app.py` and `runners/tsfm_service.py`). The resulting flamegraphs (`fastapi.svg`, `tsfm.svg`) highlight CPU‑intensive functions and I/O bottlenecks. These insights guided targeted refactors such as:

- Introducing async I/O for blocking network and file operations.
- Caching repetitive computations with `functools.lru_cache`.
- Switching to generators for large JSONL streams to reduce memory churn.

Please refer to the profiling artifacts in the repository for detailed analysis.

```bash
python -m venv .venv
source .venv/bin/activate
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
- Install with `uv pip sync --frozen requirements.lock`

See [dependency lockfile strategy](docs/dependency-lockfile-strategy.md).

## TSFM forecast API hardening notes

- Inbound auth: set `TSFM_FORECAST_API_TOKEN` (or `AUTH_TOKEN`) to a non-placeholder secret (`demo-token`/`tsfm-dev-token`/`changeme` 등 금지), and call `/tsfm/forecast` with `Authorization: Bearer <token>` (or `X-API-Key: <token>`).
- Runtime integration tokens: live tollama calls read `TOLLAMA_TOKEN` when calling downstream model runtime.
- Forecast request constraints and fallback behavior are documented in [TSFM Forecast Operational Policy](docs/ops/tsfm-forecast-operational-policy.md).
- Hardening preflight command is documented in [TSFM Hardening Gate](docs/ops/tsfm-hardening-gate.md):

```bash
API_BASE=http://127.0.0.1:8100 TSFM_FORECAST_API_TOKEN=<real-secret> scripts/rollout_hardening_gate.sh
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
