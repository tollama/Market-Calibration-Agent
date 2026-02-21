# Live Demo Security Validation Check

- Executed at (UTC): 2026-02-21T15:35:48Z
- API base: http://127.0.0.1:8000
- Script: scripts/live_demo_security_check.sh

## Results

| Check | Expected | Observed | Status |
|---|---:|---:|---|
| Unauthorized request to POST /tsfm/forecast | 401 | 401 | PASS |
| Valid token happy path | 200 | 200 | PASS |
| Burst rate limit | 429 + Retry-After | 429 + 57 | PASS |

## Happy Path Response Summary

~~~json
{"market_id": "prd2-d1-normal", "q50_len": 3, "runtime": "baseline", "fallback_used": true}
~~~

## Public Demo Safe Guidance

- Use a non-production demo token only; rotate it after the session.
- Never display raw secrets on screen (terminal history, env dumps, CI logs).
- Keep auth enabled for demo API endpoints; do not disable require_auth.
- Keep rate-limit protection enabled to prevent accidental burst abuse during live Q&A.
- If a check fails, stop the public demo and fix configuration before continuing.
- Share only status codes and high-level behavior publicly; avoid exposing internals (stack traces, private endpoints, infrastructure details).

## Repro Command

~~~bash
scripts/live_demo_security_check.sh
~~~
