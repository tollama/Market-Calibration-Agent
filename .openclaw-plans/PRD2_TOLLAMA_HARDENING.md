# PRD2 Tollama Runtime Hardening Guide (Performance + Reliability)

## 0) Scope and current baseline (inspected)

Inspected files:
- `runners/tollama_adapter.py`
- `runners/tsfm_service.py`
- `configs/tsfm_runtime.yaml`
- `PRD2 — TSFM Runner (via tollama).md`
- `docs/prd2-implementation-status.md`

Current implemented defaults:
- Tollama timeout: `2.0s`
- Retry: `1` (jitter only, no exponential backoff)
- HTTP pool: `max_connections=100`, `max_keepalive_connections=20`
- Service cache TTL: `60s` (in-memory)
- Circuit breaker: `3 consecutive failures`, `30s cooldown`
- Fallback: EWMA baseline on tollama errors / short history / low liquidity
- SLO targets in PRD2: p95 `<=300ms`, top-N cycle `<=60s`

---

## 1) Hardening goals

1. Keep forecast endpoint predictable under degradation (no latency spikes/cascades).
2. Reduce unnecessary fallback rate during transient runtime/network blips.
3. Preserve service continuity with explicit failure classes + deterministic fallback order.
4. Make behavior tunable by env (dev/staging/prod) rather than one-size-fits-all.

---

## 2) Timeout + retry policy

## 2.1 Timeout policy (recommended)
Use split timeouts (connect/read/write/pool), not one global timeout.

Recommended semantics:
- `connect_timeout_s`: connection setup budget
- `read_timeout_s`: inference response budget
- `write_timeout_s`: request body send budget
- `pool_timeout_s`: waiting for idle pooled connection
- `request_deadline_s`: hard end-to-end cap per call

Operational target:
- Keep p95 under 300ms during normal operation
- Fail fast before cycle budget is threatened

## 2.2 Retry policy (recommended)
Retry **only** transient classes:
- network transient (`ConnectError`, `ReadTimeout`, `RemoteProtocolError`)
- HTTP `429`, `502`, `503`, `504`

Do **not** retry:
- HTTP `4xx` (except 429)
- schema/validation errors
- deterministic bad request

Backoff:
- exponential with full jitter
- base `100ms`, cap `800ms`
- stop when `request_deadline_s` is exceeded

---

## 3) Connection pool / keepalive sizing

Current: 100 / 20.

Recommendation:
- Size by expected concurrent in-flight requests per API process.
- Rule of thumb:
  - `max_connections = 2x~4x peak_inflight`
  - `max_keepalive_connections = 50%~75% of max_connections`
- Add keepalive expiry (`30~60s`) to avoid stale sockets.

If top-N fanout grows, prefer multiple worker processes with moderate pools over one huge pool.

---

## 4) Circuit-breaker policy

Current breaker is simple consecutive-failure counter (good MVP).

Recommended hardened breaker:
- Trigger by rolling-window failures (not only consecutive), e.g.:
  - open if `N failures in 30s` OR failure ratio above threshold with minimum volume
- States: `closed -> open -> half_open -> closed`
- Half-open probes: allow small probe budget (`k` calls); re-open on first probe failure
- Cooldown has jitter to avoid synchronized re-entry storms

Suggested fallback action while open:
- Immediately use baseline path (no tollama attempts)
- Emit single throttled warning + metric increments

---

## 5) Cache strategy

Current: in-process TTL cache 60s.

Recommended:
1. L1 cache (existing): request-hash key, TTL 60s
2. Add `stale-if-error` window (e.g., +120s):
   - if tollama fails and fresh cache miss, return stale cached response before baseline (with warning tag)
3. For staging/prod multi-instance: optional L2 shared cache (Redis) with same key schema
4. Negative cache for repeated deterministic bad requests (short TTL 5-15s)

Cache metadata tags to add:
- `cache_tier`: `l1|l2|none`
- `cache_state`: `fresh|stale_if_error|miss`

---

## 6) Model warmup

Warmup policy:
- On service startup:
  1) health-check tollama endpoint
  2) send synthetic tiny forecast request for each configured model profile
- Keepwarm job every 2-5 minutes for active model(s)
- After deployment/roll restart, gate traffic until warmup succeeds or baseline-only mode is explicitly enabled

Expected benefit: reduce cold-start latency spikes and first-request failures.

---

## 7) Failure taxonomy (standardize)

Use stable error classes/codes in `meta` and logs:
- `INPUT_INVALID` (bad request/schema)
- `INPUT_INSUFFICIENT_HISTORY` (too few points)
- `INPUT_LOW_LIQUIDITY_BASELINE_ONLY`
- `RUNTIME_TIMEOUT`
- `RUNTIME_RATE_LIMITED`
- `RUNTIME_5XX`
- `RUNTIME_NETWORK`
- `RUNTIME_BAD_RESPONSE_SCHEMA`
- `CIRCUIT_OPEN`
- `CACHE_STALE_SERVED`
- `BASELINE_FALLBACK`

This enables clear dashboards and policy tuning by cause.

---

## 8) Fallback behavior (deterministic order)

Recommended fallback chain:
1. Fresh cache hit -> return
2. Tollama call attempt(s) under retry policy
3. If fails and stale cache exists -> return stale (`fallback_used=true`, reason `CACHE_STALE_SERVED`)
4. Else baseline forecast (`runtime=baseline`, explicit reason code)
5. If baseline fails (rare) -> fail closed with typed error and no partial response

Policy constraints:
- If circuit is open, skip tollama attempts entirely.
- For low-liquidity bucket, direct baseline path remains correct.

---

## 9) Recommended defaults by environment

## 9.1 Dev
- `connect_timeout_s: 0.5`
- `read_timeout_s: 2.0`
- `write_timeout_s: 0.5`
- `pool_timeout_s: 0.25`
- `request_deadline_s: 2.5`
- `retry_count: 1`
- `retry_backoff_base_ms: 100`
- `retry_backoff_cap_ms: 500`
- `max_connections: 32`
- `max_keepalive_connections: 16`
- `keepalive_expiry_s: 30`
- `cache_ttl_s: 30`
- `cache_stale_if_error_s: 60`
- `breaker_failures_30s: 5`
- `breaker_cooldown_s: 15`
- `breaker_half_open_probe: 2`

## 9.2 Staging
- `connect_timeout_s: 0.3`
- `read_timeout_s: 1.5`
- `write_timeout_s: 0.3`
- `pool_timeout_s: 0.2`
- `request_deadline_s: 2.0`
- `retry_count: 2`
- `retry_backoff_base_ms: 100`
- `retry_backoff_cap_ms: 800`
- `max_connections: 128`
- `max_keepalive_connections: 64`
- `keepalive_expiry_s: 45`
- `cache_ttl_s: 60`
- `cache_stale_if_error_s: 120`
- `breaker_failures_30s: 8`
- `breaker_cooldown_s: 20`
- `breaker_half_open_probe: 3`

## 9.3 Prod (top defaults)
- `connect_timeout_s: 0.25`
- `read_timeout_s: 1.2`
- `write_timeout_s: 0.25`
- `pool_timeout_s: 0.15`
- `request_deadline_s: 1.8`
- `retry_count: 2` (transient errors only)
- `retry_backoff_base_ms: 100`
- `retry_backoff_cap_ms: 800`
- `max_connections: 256`
- `max_keepalive_connections: 128`
- `keepalive_expiry_s: 60`
- `cache_ttl_s: 60`
- `cache_stale_if_error_s: 180`
- `breaker_failures_30s: 12` (with min volume gate)
- `breaker_cooldown_s: 30`
- `breaker_half_open_probe: 5`
- `baseline_only_liquidity_bucket: low` (keep)

---

## 10) Gap checklist vs current implementation

1. Split timeout controls (currently single timeout).
2. Retry filter by error/status + exponential jitter (currently retry-all exception path with jitter-only).
3. Rolling-window + half-open circuit breaker (currently consecutive-only).
4. `stale-if-error` cache behavior (currently TTL fresh only).
5. Warmup/keepwarm hooks for tollama/model profiles.
6. Structured failure taxonomy codes for metrics/alerts.
7. Environment-specific runtime config wiring from `configs/tsfm_runtime.yaml` (current service mostly relies on dataclass defaults).

---

## 11) Minimum-safe prod starter set (if only 5 knobs are exposed)

1. `request_deadline_s = 1.8`
2. `retry_count = 2` (transient only, exp-jitter)
3. `max_connections/max_keepalive = 256/128`
4. `breaker = 12 failures/30s, cooldown 30s, half-open 5`
5. `cache_ttl_s = 60, stale_if_error_s = 180`

These five alone provide the largest reliability gain with low complexity cost.
