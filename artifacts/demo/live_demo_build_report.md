# Live Demo Build Report

## Implemented
- Backend endpoints added:
  - `GET /markets`
  - `GET /markets/{market_id}`
  - `GET /markets/{market_id}/metrics`
  - `POST /markets/{market_id}/comparison`
- GUI app added: `demo/live_demo_app.py` (Streamlit)
  - Overview, Market Detail, Compare, Observability pages
  - KR/EN labels + explainability + safe disclaimer
- Run script: `scripts/run_live_demo.sh`
- Runbook: `docs/ops/live-demo-gui-runbook.md`

## Endpoints Smoke-tested
- `/markets`
- `/markets/{market_id}`
- `/markets/{market_id}/metrics`
- `/markets/{market_id}/comparison`
- Existing: `/scoreboard`, `/alerts`, `/postmortem/{market_id}`

## App Start Command
```bash
./scripts/run_live_demo.sh
```

## Sample Outputs
- `GET /markets` → `{ "total": 1, "items": [{"market_id":"mkt-90", ...}] }`
- `GET /markets/mkt-90/metrics` → includes `scoreboard_by_window`, `alert_total`, `alert_severity_counts`
- `POST /markets/mkt-90/comparison` → includes `baseline`, `tollama`, `delta_last_q50`
