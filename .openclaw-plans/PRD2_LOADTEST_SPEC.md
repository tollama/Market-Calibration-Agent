# PRD2 Load/Performance Validation Spec — TSFM Runner

## 1) Scope and baseline

This spec validates PRD2 TSFM Runner (`POST /tsfm/forecast`) for:
- functional smoke correctness,
- performance/load against PRD2 SLO,
- resilience (fallback/circuit-breaker),
- canary rollout safety with explicit rollback triggers.

Grounded in current implementation:
- `runners/tsfm_service.py` (cache TTL=60s, breaker=3 fails/30s, fallback, post-processing)
- `runners/tollama_adapter.py` (timeout=2s, retry=1, pooled connections)
- `configs/tsfm_runtime.yaml` SLO: p95 <= 300ms, top-N cycle <= 60s
- `pipelines/bench_tsfm_runner_perf.py` perf smoke harness

---

## 2) Test environments

- **Local perf env**: developer machine, tollama mocked via `_BenchAdapter` (deterministic).
- **Staging env**: real tollama runtime + real network path.
- **Canary env**: production-like routing with traffic split.

Required setup:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

---

## 3) Reproducible datasets/scenarios

Use these request patterns (no source changes required):

### D1. Normal liquid market (happy path)
- `y` length 288, smooth bounded series around 0.4~0.6
- quantiles [0.1,0.5,0.9], horizon 12
- liquidity_bucket != low

### D2. High-volatility/jump market
- same shape as D1 but include jumps (e.g., 0.35 -> 0.75 -> 0.45)
- validates clipping/crossing fix + interval sanity.

### D3. Illiquid / forced fallback
- `liquidity_bucket=low` or `len(y)<32`
- expect baseline fallback deterministically.

### D4. Runtime failure simulation
- staging: temporarily point tollama host to invalid endpoint or block connectivity
- expect fallback + breaker-open behavior.

---

## 4) Validation tiers and commands

## T0. Preflight (must pass)
```bash
python -c "from pathlib import Path; import yaml; [yaml.safe_load(p.read_text()) for p in Path('configs').glob('*.yaml')]; print('Config load OK')"
pytest tests/unit/test_tsfm_runner_service.py tests/unit/test_api_tsfm_forecast.py tests/unit/test_tsfm_model_license_guard.py -q
```
Pass criteria:
- all tests pass
- no schema/config load errors

## T1. API smoke
```bash
uvicorn api.app:app --host 127.0.0.1 --port 8000
```
```bash
curl -s -X POST http://127.0.0.1:8000/tsfm/forecast \
  -H 'content-type: application/json' \
  -d '{
    "market_id":"m-smoke-1",
    "as_of_ts":"2026-02-20T12:00:00Z",
    "freq":"5m",
    "horizon_steps":12,
    "quantiles":[0.1,0.5,0.9],
    "y":[0.41,0.42,0.40,0.43,0.44,0.45,0.46,0.45,0.44,0.43,0.42,0.41,0.40,0.41,0.42,0.43,0.44,0.45,0.46,0.47,0.48,0.47,0.46,0.45,0.44,0.43,0.42,0.41,0.40,0.41,0.42,0.43],
    "transform":{"space":"logit","eps":1e-6},
    "model":{"provider":"tollama","model_name":"chronos","params":{}}
  }'
```
Pass criteria:
- response contains `yhat_q` for 0.1/0.5/0.9, each length=12
- all values in [0,1]
- per step monotonic: q10 <= q50 <= q90

## T2. Perf smoke (deterministic harness)
```bash
python pipelines/bench_tsfm_runner_perf.py \
  --requests 1000 \
  --unique 100 \
  --adapter-latency-ms 15 \
  --budget-p95-ms 300 \
  --budget-cycle-s 60
```
Pass criteria:
- prints `SLO_PASS`
- `latency_p95_ms <= 300`
- `elapsed_s <= 60`

## T3. Service load (real API, concurrent)
Example reproducible runner:
```bash
python - <<'PY'
import asyncio, json, time
import httpx
URL='http://127.0.0.1:8000/tsfm/forecast'
payload={
  'market_id':'m-load-1','as_of_ts':'2026-02-20T12:00:00Z','freq':'5m','horizon_steps':12,
  'quantiles':[0.1,0.5,0.9],'y':[0.45]*288,
  'transform':{'space':'logit','eps':1e-6},
  'model':{'provider':'tollama','model_name':'chronos','params':{}}
}
N=2000; C=50
lat=[]; err=0; fb=0
sem=asyncio.Semaphore(C)
async def one(i,client):
  nonlocal err,fb
  p=dict(payload); p['market_id']=f"m-{i%200}"; p['as_of_ts']=f"2026-02-20T12:{i%60:02d}:00Z"
  async with sem:
    t=time.perf_counter()
    try:
      r=await client.post(URL,json=p)
      dt=(time.perf_counter()-t)*1000; lat.append(dt)
      if r.status_code!=200: err+=1; return
      j=r.json(); fb += int(bool(j.get('meta',{}).get('fallback_used')))
      q=j['yhat_q'];
      for a,b,c in zip(q['0.1'],q['0.5'],q['0.9']):
        if not (0<=a<=b<=c<=1): err+=1; break
    except Exception:
      err+=1
async def main():
  async with httpx.AsyncClient(timeout=5.0) as client:
    await asyncio.gather(*(one(i,client) for i in range(N)))
  lat.sort(); p95=lat[int(0.95*(len(lat)-1))] if lat else 9999
  print(json.dumps({'requests':N,'concurrency':C,'p95_ms':p95,'error_rate':err/max(N,1),'fallback_rate':fb/max(N,1)}))
asyncio.run(main())
PY
```
Pass criteria (staging normal condition):
- p95 <= 300ms
- error_rate <= 1.0%
- fallback_rate <= 5.0%
- quantile-order/bounds violations = 0

## T4. Failure-mode load (forced tollama degradation)
Run T3 while inducing tollama timeout/network failure.
Pass criteria:
- service remains available (HTTP success >= 99%)
- fallback_rate rises (expected), but response validity remains 100%
- no crash loop; breaker behavior observed (fallback reason includes `circuit_breaker_open`)

---

## 5) Pass/Fail thresholds (release-critical)

1. **Latency SLO**: p95 <= 300ms (PRD2)
2. **Cycle SLO**: top-N cycle <= 60s (PRD2)
3. **Reliability**: HTTP error rate <= 1% (normal staging load)
4. **Output safety**: 100% outputs bounded [0,1], 0 quantile crossing after post-processing
5. **Fallback health (normal)**: fallback_rate <= 5%
6. **Fallback health (failure drill)**: fallback allowed to spike, but success rate >= 99% and payload correctness maintained

Any miss above = **FAIL / no promotion**.

---

## 6) Rollout gates

- **Gate A (local)**: T0/T1/T2 pass.
- **Gate B (staging)**: T3 pass for 3 consecutive runs.
- **Gate C (canary 5%)**: 30 minutes clean window.
- **Gate D (canary 25%)**: 60 minutes clean window.
- **Gate E (100%)**: 24h monitoring window with no rollback triggers.

Promotion requires all prior gates green.

---

## 7) Canary monitoring checks (production)

Track at 5-minute windows + 1-hour rolling:
- `tsfm_request_p95_ms`
- `tsfm_error_rate`
- `tsfm_fallback_rate`
- `tsfm_invalid_output_rate` (out-of-bounds or crossing after response validation)
- `tollama_error_rate`
- `breaker_open_rate`

Expected canary-safe envelope:
- p95 <= 300ms
- error_rate <= 1%
- invalid_output_rate = 0
- fallback_rate <= 8% at 5% canary, <= 10% at 25% canary

---

## 8) Rollback triggers (immediate)

Trigger rollback to baseline-only routing if ANY occurs:
1. p95 > 400ms for 2 consecutive 5-min windows
2. error_rate > 2% for any 5-min window
3. invalid_output_rate > 0 (any safety violation)
4. fallback_rate > 20% for 15 minutes (without planned incident drill)
5. breaker_open_rate > 30% for 15 minutes

Rollback actions:
- stop TSFM traffic promotion (freeze at current or drop to 0%)
- route inference calls to baseline-only path in caller/orchestrator
- open incident + preserve logs for window (request/meta/fallback reason)

---

## 9) Reporting template (per run)

Record:
- commit SHA, env, tollama model/version
- load profile (`N`, concurrency, unique keys)
- p50/p95 latency, cycle time, throughput
- error/fallback/breaker rates
- safety validation counts
- PASS/FAIL verdict + blocking reasons

This report is required for each rollout gate approval.
