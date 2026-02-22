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

## Dependency locking (optional)

See [dependency lockfile strategy](docs/dependency-lockfile-strategy.md).

## Config Files

- `configs/default.yaml` - application, data, and calibration defaults.
- `configs/alerts.yaml` - alert thresholds, cooldowns, and channels.
- `configs/models.yaml` - model profiles and feature settings.
- `configs/logging.yaml` - Python logging configuration.

## Architecture / Notes

- [PRD1 구현 상태 (I-01~I-20)](docs/prd1-implementation-status.md) - 최신 판정, 남은 갭, 실행 백로그
- [PRD2 TSFM Runner 구현 상태](docs/prd2-implementation-status.md) - tollama 기반 TSFM runner, fallback, post-processing, conformal, 운영 가이드
- [PRD2 Dashboards (TSFM observability)](docs/ops/prd2-dashboards.md) - Grafana dashboard import/provisioning and panel expectations
- [Conformal calibration ops guide](docs/conformal-ops.md) - rolling updater, state persistence, manual/cron runbook
- [Label resolver defaults and precedence](docs/label-resolver-defaults.md)
