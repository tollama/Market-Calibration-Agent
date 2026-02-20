# PRD2 Performance Blueprint — TSFM Runner (via tollama)

Updated: 2026-02-21
Scope: p95 latency, throughput, graceful degradation for `/tsfm/forecast`

---

## 1) Current implementation state (from repo + uncommitted changes)

### What already exists
- `TSFMRunnerService` with:
  - in-memory request cache (`cache_ttl_s=60`)
  - circuit breaker (`failures=3`, cooldown `30s`)
  - fallback to baseline bands (`EWMA` default)
  - quantile crossing fix + [0,1] clipping
  - interval width guards (`min=0.02`, `max=0.9`)
- `TollamaAdapter` with:
  - `httpx.Client` connection pooling
  - timeout/retry/jitter (`2.0s`, `1 retry`, jitter only)
- API endpoint exists: `POST /tsfm/forecast`
- Perf smoke bench exists: `pipelines/bench_tsfm_runner_perf.py`

### Gaps vs PRD2 + stage plan
1. **No hard TSFM deadline budgeting** inside service (adapter may spend full timeout+retry).
2. **Circuit breaker too aggressive/short** vs stage plan (3/30s vs 5/120s).
3. **Cache is process-local only** and not keyed for cross-worker reuse.
4. **No batch concurrency control / top-N scheduler policy** for cycle throughput.
5. **Missingness/max_gap gating not enforced** in service path.
6. **No explicit degraded modes** (normal/degraded/baseline-only with auto recovery rules).
7. **Observability incomplete** for p95/p99, queue wait, fallback reason cardinality, cache effectiveness.
8. **No production perf acceptance gate** in CI with deterministic budgets.

---

## 2) Performance targets (measurable)

### Request-level SLO
- p50 latency: **<= 120ms**
- p95 latency: **<= 300ms**
- p99 latency: **<= 700ms**
- Baseline fallback latency p95: **<= 50ms**

### Cycle-level throughput SLO
- Top-N cycle (N=200 @ 5m cadence): **<= 60s** wall-clock
- Effective throughput target: **>= 4 req/s sustained** (with mixed cache-hit profile)

### Graceful degradation targets
- Fallback rate in normal mode: **< 10% (5m window)**
- Enter degraded mode if fallback rate **>= 25% for 3m**
- Enter baseline-only mode if fallback rate **>= 50% for 5m**
- Recovery to normal when fallback rate **< 15% for 10m** and tollama health green

---

## 3) Default runtime profile (v1.0)

Use these as exact defaults unless overridden:

```yaml
tsfm:
  freq: 5m
  input_len_steps: 288
  horizon_steps: 12
  quantiles: [0.1, 0.5, 0.9]
  transform: { space: logit, eps: 1e-6 }
  missing:
    max_gap_minutes: 60
    min_points_for_tsfm: 32
  adapter:
    timeout_s: 1.2
    retry_count: 1
    retry_backoff_ms: 120
    retry_jitter_ms: 80
    deadline_budget_ms: 1600
    max_connections: 200
    max_keepalive_connections: 50
  cache:
    ttl_s: 60
    max_entries: 50000
    stale_while_revalidate_s: 20
  circuit_breaker:
    failures_to_open: 5
    cooldown_s: 120
  perf:
    worker_concurrency: 32
    per_market_inflight_limit: 1
    queue_timeout_ms: 100
  fallback:
    baseline_method: EWMA
    baseline_only_liquidity_bucket: low
  interval_sanity:
    min_width: 0.02
    max_width: 0.60
```

Rationale:
- Tighten timeout budget to protect p95/p99.
- Increase connection pool + controlled concurrency for throughput.
- Increase breaker threshold/cooldown to avoid flapping.
- Narrow `max_width` from `0.9` to `0.60` per stage defaults.

---

## 4) Prioritized optimization actions

## P0 (must-do before broad rollout)

### P0-1. End-to-end latency budget + deadline propagation
- Implement request deadline budget (`deadline_budget_ms=1600`) and abort TSFM path if exceeded; return baseline immediately.
- Split budget:
  - queue wait <= 100ms
  - adapter call #1 <= 1200ms
  - retry envelope <= 250ms
  - postprocess + serialization <= 50ms
- Target impact: p95 from unbounded retry tail -> **<=300ms** under normal load; p99 tail cut by >40%.

### P0-2. Degradation state machine (normal/degraded/baseline-only)
- Add explicit mode transitions driven by rolling 3m/5m health windows.
- In degraded mode: disable retry (`retry_count=0`) + force shorter timeout (`900ms`).
- In baseline-only: bypass tollama entirely for selected/all markets.
- Target impact: maintain cycle completion <=60s during tollama incidents; prevent queue buildup.

### P0-3. Throughput control: bounded concurrency + queue guard
- Add global worker semaphore (`worker_concurrency=32`) and per-market inflight cap (`1`).
- Drop/fast-fallback queued requests exceeding `queue_timeout_ms=100`.
- Target impact: stable throughput >=4 req/s, avoid convoy and latency spikes.

### P0-4. Missingness/eligibility fast gate before adapter
- Enforce `max_gap_minutes=60`, `min_points_for_tsfm=32`, low-liquidity baseline-only gate.
- Execute gate before any adapter call.
- Target impact: reduce avoidable tollama calls by 10–25% on sparse markets; lower fallback/error rates.

### P0-5. Minimum observability for SLO enforcement
- Emit histograms/counters:
  - `tsfm_request_latency_ms` (p50/p95/p99)
  - `tsfm_queue_wait_ms`
  - `tollama_latency_ms`
  - `fallback_rate`, `fallback_reason_count`
  - `cache_hit_rate`
  - `degradation_mode`
- Add perf CI gate using bench script:
  - fail if p95 >300ms or cycle >60s under standard profile.
- Target impact: measurable, enforceable performance envelope.

## P1 (high value next)

### P1-1. Cache hardening
- Add cache bounds (`max_entries=50k`) + eviction policy.
- Add stale-while-revalidate (`20s`) to smooth bursts.
- Optional L2 shared cache (Redis) for multi-worker dedupe.
- Target: cache-hit profile >=40% on 5m cycles; p95 improvement 20–35% when hot.

### P1-2. Adapter endpoint fallback + error taxonomy
- Probe `/api/forecast` then `/v1/forecast` on 404 capability mismatch.
- Normalize retryable vs non-retryable errors (timeout, 5xx, schema, 4xx).
- Target: reduce false retries and cut noisy failure modes.

### P1-3. Batch execution policy for top-N
- Deterministic market ordering (liquidity/priority) + chunk size `32`.
- Early stop when cycle budget nearly exhausted (serve baseline for remainder).
- Target: >=99% cycle completion by 60s at N=200.

## P2 (optimization/scale)

### P2-1. Adaptive concurrency controller
- Auto-tune concurrency 16–64 based on recent p95 and error rate.
- Goal: maximize throughput while keeping p95 under budget.

### P2-2. Hedged requests for long-tail suppression (optional)
- For high-priority markets only, fire second request after 300ms if first not returned.
- Strict cap: <=5% traffic hedged.
- Goal: p99 reduction in noisy runtime conditions.

### P2-3. Persistent warm-start model/session strategy
- Keep hot models primed; schedule warmup every 10m.
- Goal: cold-start penalties reduced by >50%.

---

## 5) Measurement plan

## Load profiles
1. **Steady**: 200 requests, 20 unique keys, adapter latency 15ms.
2. **Mixed**: 200 requests, 100 unique keys, adapter latency 80ms.
3. **Degraded**: 20% adapter timeout injection + 10% 5xx.
4. **Incident**: 70% adapter failure for 10 minutes.

## Pass criteria
- Steady/mixed: p95 <=300ms, cycle <=60s.
- Degraded: cycle <=60s, fallback <=50%, no queue runaway.
- Incident: baseline-only auto-switch <=2 minutes, cycle still <=60s.

---

## 6) Rollout sequence

1. **Phase A (shadow)**: metrics + gates only, no behavior change.
2. **Phase B (guardrails on)**: deadline + queue guard + eligibility gate.
3. **Phase C (degradation modes)**: auto mode switching enabled.
4. **Phase D (cache hardening)**: bounded cache + SWR.
5. **Phase E (optional P2)** after 1 week stable SLO compliance.

Rollback rule: if breach precision drops >15% vs baseline over 3d or p95 SLO violated >30m continuously, force baseline-only.

---

## 7) Top risks and mitigations
- **Risk**: tighter timeout increases fallback rate.
  - Mitigation: degraded mode policy + per-segment tuning.
- **Risk**: higher concurrency overloads tollama.
  - Mitigation: bounded semaphore + adaptive cap + breaker.
- **Risk**: local cache memory growth.
  - Mitigation: max_entries + eviction + metrics.

---

## 8) Definition of done (performance)

- 7-day run with:
  - p95 <=300ms, p99 <=700ms
  - top-N cycle <=60s for >=99% cycles
  - fallback rate <10% in normal mode
  - incident auto-degradation verified by game-day test
- CI perf gate active and blocking on regression.
