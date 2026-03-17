# Federation Smoke Runbook

## Purpose
Validate the local four-service federation path across:

- `News-Agent`
- `Financial-Agent`
- `tollama`
- `Market-Calibration-Agent`

The smoke covers service startup, direct compatibility endpoints, tollama live connector health, remote payload assembly, and MCA trust explanation availability.

## Preconditions
- Workspace contains sibling repos under one parent directory:
  - `Market-Calibration-Agent`
  - `News-Agent`
  - `Financial-Agent`
  - `tollama`
- `uv`, `curl`, and `python3.11` are installed.
- Ports `8001`, `8090`, `8091`, and `11435` are free.

## What The Script Does
Script:
[scripts/federation_smoke.sh](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/scripts/federation_smoke.sh)

It performs these steps:

1. Seeds a persisted `News-Agent` trust payload for `story-smoke-001`.
2. Starts `News-Agent` on `127.0.0.1:8090`.
3. Starts `Financial-Agent` on `127.0.0.1:8091` with provider-backed bootstrap.
4. Starts `MCA` on `127.0.0.1:8001`.
5. Starts `tollama` on `127.0.0.1:11435` with live connectors enabled.
6. Verifies:
   - `News-Agent` `/stories/story-smoke-001`
   - `Financial-Agent` `/instruments/AAPL`
   - `MCA` `/markets/mkt-90/trust-explanation`
   - `tollama` `/api/xai/connectors/health`
   - raw `News-Agent` `contradiction_score` remains low and is not inverted
   - tollama connector assembly against live `news` and `financial_market` services
   - tollama interprets that same news payload as `contradiction_penalty.score = 1 - contradiction_score`
7. Writes a markdown report and shuts down all started processes.

## Local Execution
```bash
cd /Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent
bash scripts/federation_smoke.sh
```

Optional overrides:
```bash
PYTHON311_BIN=/opt/homebrew/bin/python3.11 \
REPORT_PATH=artifacts/federation/local_smoke.md \
bash scripts/federation_smoke.sh
```

## Expected Results
- Exit code `0`
- Report written to:
  - `artifacts/federation/federation_smoke_report.md`
- Report contains PASS lines for:
  - News service startup
  - Financial service startup
  - MCA startup
  - tollama startup
  - news fixture payload
  - news contradiction raw score
  - financial provider-backed payload
  - MCA trust explanation
  - tollama connector health
  - tollama news assembly
  - tollama news contradiction semantics
  - tollama financial assembly

## Failure Interpretation
- `news_agent_health` fail:
  - Check `NEWS_AGENT_DATA_DIR`
  - Check `uv` environment creation and port `8090`
- `financial_provider_payload` fail:
  - Financial service may be running without provider-backed connectors
  - Check `configs/default.yaml` and Yahoo availability
- `mca_trust_payload` fail:
  - MCA derived data may be missing or route regression reintroduced
- `tollama_connector_health` fail:
  - Live connector env vars or service ports are wrong
- `tollama_*_assembly` fail:
  - Federation contract drift or remote payload schema breakage

## Notes
- The script intentionally seeds the `News-Agent` smoke fixture locally instead of depending on live provider ingest.
- The financial smoke path is provider-backed and intentionally uses `AAPL` so the returned trust payload is not a default empty signal.
