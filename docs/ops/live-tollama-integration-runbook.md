# Live Tollama Integration Runbook

## Purpose
Validate the real TSFM runtime path (`TollamaAdapter` + `TSFMRunnerService`) against a live tollama instance.

## Defaults and Safety
- Live tests are **off by default**.
- Tests run only when `LIVE_TOLLAMA_TESTS=1` (or `true/yes/on`).
- Even when enabled, tests will `skip` if the tollama host:port is unreachable.

## Required Environment Variables
- `LIVE_TOLLAMA_TESTS=1`
- `TOLLAMA_BASE_URL` (default: `http://localhost:11435`)

Optional:
- `TOLLAMA_TOKEN`
- `TOLLAMA_ENDPOINT` (default: `/v1/timeseries/forecast`)
- `TOLLAMA_MODEL_NAME` (default: `chronos`)
- `TOLLAMA_MODEL_VERSION`
- `TOLLAMA_TIMEOUT_S` (default in test: `8`)
- `TOLLAMA_RETRY_COUNT` (default in test: `0`)

## Local Execution
```bash
cd /Users/ychoi/Documents/GitHub/Market-Calibration-Agent
python -m pip install -e ".[dev]"

export LIVE_TOLLAMA_TESTS=1
export TOLLAMA_BASE_URL="http://localhost:11435"
# export TOLLAMA_TOKEN="..."  # optional

pytest -q tests/integration/test_tollama_live_integration.py
```

## CI Gating
Workflow: `.github/workflows/ci.yml`
- `unit-tests` job: always runs.
- `live-tollama-integration` job runs only if:
  - event is nightly schedule **or** repo variable `ENABLE_LIVE_TOLLAMA_CI=true`, and
  - secret `TOLLAMA_BASE_URL` is configured.

Recommended repo settings:
- Secrets: `TOLLAMA_BASE_URL`, `TOLLAMA_TOKEN` (if needed)
- Variables: `ENABLE_LIVE_TOLLAMA_CI`, `TOLLAMA_ENDPOINT`, `TOLLAMA_MODEL_NAME`, `TOLLAMA_MODEL_VERSION`
