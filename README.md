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
```

## Run

```bash
# bootstrap sanity check: load all config files
python -c "from pathlib import Path; import yaml; [yaml.safe_load(p.read_text()) for p in Path('configs').glob('*.yaml')]; print('Config load OK')"
```

## Test

```bash
pytest
```

## Config Files

- `configs/default.yaml` - application, data, and calibration defaults.
- `configs/alerts.yaml` - alert thresholds, cooldowns, and channels.
- `configs/models.yaml` - model profiles and feature settings.
- `configs/logging.yaml` - Python logging configuration.
