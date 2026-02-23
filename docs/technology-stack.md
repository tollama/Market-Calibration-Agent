# Market Calibration Agent Technology Stack

## Runtime and Language

- Python `>=3.11` (declared in `pyproject.toml`).
- Packaging/build: `setuptools` (`pyproject.toml`).
- Dependency lock strategy: committed `requirements.lock` + `uv pip sync --frozen`.

## Core Application Libraries

- API and schema:
  - `fastapi` for HTTP API (`api/app.py`).
  - `pydantic v2` for request/response and domain validation (`api/schemas.py`, `schemas/*`).
- Data and numerics:
  - `pandas` for tabular transforms and aggregation.
  - `numpy` for numeric cleanup and feature helpers.
  - `pyarrow` for parquet read/write.
- Connectivity:
  - `httpx` for Gamma API and tollama runtime HTTP clients.
  - `websockets` for realtime stream ingestion.
- Config and metadata:
  - `pyyaml` for runtime and policy configs (`configs/*.yaml`).

## Optional/Environment-Specific Dependencies

- Server runtime:
  - `uvicorn[standard]` via `[project.optional-dependencies.server]`.
- Demo UI:
  - `streamlit` via `[project.optional-dependencies.demo]`.
- Testing:
  - `pytest` via `[project.optional-dependencies.test]`.

## Data and Persistence Strategy

- Raw datasets: line-delimited JSON under `raw/<dataset>/dt=YYYY-MM-DD/*.jsonl`.
- Derived datasets: parquet partitions under `derived/<dataset>/dt=YYYY-MM-DD/*.parquet`.
- Additional derived API artifacts:
  - JSON scoreboards/alerts and markdown postmortems in `data/derived/*`.
- LLM cache options:
  - in-memory SHA-256 key cache (`llm/cache.py`)
  - sqlite persistent cache (`llm/sqlite_cache.py`)

## Forecast Runtime Stack (PRD2)

- Service orchestrator: `runners/tsfm_service.py`.
- Runtime adapter: `runners/tollama_adapter.py` (HTTP, retries, jitter, pooled connections).
- Baseline fallback models: `runners/baselines.py` (EWMA/Kalman/Rolling Quantile).
- Calibration overlay: `calibration/conformal.py` + state load/save in `calibration/conformal_state.py`.
- Observability emitter: `runners/tsfm_observability.py` (Prometheus-style counters/gauges/histograms).

## External Integrations

- Polymarket Gamma REST API (`connectors/polymarket_gamma.py`).
- Polymarket market websocket stream (`connectors/polymarket_ws.py`).
- Polymarket subgraph GraphQL endpoint (`connectors/polymarket_subgraph.py`).
- tollama-compatible time-series forecast endpoint (`configs/tsfm_models.yaml` + adapter config).

## Configuration Model

- `configs/default.yaml`: app defaults, prep/calibration/trust/API settings.
- `configs/alerts.yaml`: alert thresholds and trust gate.
- `configs/models.yaml`: baseline model family and feature selection.
- `configs/tsfm_runtime.yaml`: TSFM runtime, fallback, cache, breaker, degradation, SLO defaults.
- `configs/tsfm_models.yaml`: model catalog, license tags, environment allowlists.
- `configs/logging.yaml`: Python logging setup.

## Testing and CI Stack

- Test layout:
  - unit tests in `tests/unit`
  - integration tests in `tests/integration`
- CI gates (`.github/workflows/ci.yml`):
  - lockfile sync and hardening checks
  - unit tests + PRD1 acceptance selections
  - PRD2 one-command release verification and artifact upload
  - optional scheduled live tollama integration tests

