# **PRD2 — TSFM Runner (via tollama)**

*(Updated: use [https://github.com/tollama/tollama](https://github.com/tollama/tollama) as the time‑series model runtime)*

## **1\. Purpose**

Build a **Time‑Series Foundation Model (TSFM) Runner** for Polymarket probability series that is **served through `tollama`** (single runtime \+ REST interface), producing **forecast bands (quantiles)** and metadata for downstream systems:

* **Baseline Bands (PRD1 I‑08)**  
* **TSFM Runner (PRD1 I‑09)**  
* **Conformal Calibration (PRD1 I‑10)**  
* **Alert Engine (PRD1 I‑15)** uses “band breach” as Gate 1

This PRD prioritizes **operational stability and forecast-interval quality (coverage & width)** over point accuracy.

---

## **2\. Non‑Goals**

* No trading execution, order placement, or portfolio optimization.  
* No claim of “predicting real-world outcomes” (this runner is **price/probability time‑series**, not event resolution probability).  
* No requirement that every market runs TSFM in real-time (must support selective inference on top‑N markets).

---

## **3\. Background & Key Product Insight**

Polymarket “probability/price” series have properties that make interval forecasts critical:

* Bounded in **\[0, 1\]**  
* Liquidity varies widely (sparse trades, large spreads)  
* Regime shifts and jumps (news-driven)  
* Label is “future price/probability,” not ground-truth event resolution

Therefore, the runner must:

1. Handle bounds robustly  
2. Provide **quantile bands** (e.g., q10/q50/q90)  
3. Provide strong fallback to baselines  
4. Support post-hoc calibration (Conformal) and monitoring

---

## **4\. User Stories**

1. **Calibration agent** requests 1h/6h/24h forecast bands for a market to compute “normal range” and detect breaches.  
2. **Alert system** needs 5‑minute cadence forecasts for a set of top markets, with predictable latency.  
3. **Researcher** runs backtests across many markets and compares models (baseline vs tollama TSFM) on interval metrics.

---

## **5\. System Overview**

### **5.1 Components**

* **(A) Data Prep / Feature Builder** (upstream, PRD1 I‑07)  
  Produces cleaned, resampled probability series \+ optional covariates.  
* **(B) TSFM Runner Service (this PRD)**  
  Calls **tollama** as the model runtime.  
* **(C) Baseline Band Generator (PRD1 I‑08)**  
  Always available; used for fallback.  
* **(D) Conformal Calibrator (PRD1 I‑10)**  
  Adjusts predicted intervals to meet target coverage.

### **5.2 High-Level Flow**

1. Ingest raw market data → choose **y definition** (mid/last)  
2. Resample to fixed cadence (e.g., 5m) and fill gaps with rules  
3. Transform to logit space (optional)  
4. Query tollama for quantile forecasts  
5. Validate outputs (quantile monotonicity, bounds)  
6. Apply conformal calibration (optional/rolling)  
7. Store forecast \+ metadata → consumed by Alert engine / UI

---

## **6\. Data Definitions**

### **6.1 Target series `y_t` (probability)**

**Default rule** (to reduce noise and encourage stationarity):

* If best bid/ask available:  
  `y_t = mid = (best_bid + best_ask) / 2`  
* Else if last trade price exists within a max staleness window:  
  `y_t = last_trade`  
* Else:  
  forward-fill from previous `y`

**Additional constraints**

* Clip to `[eps, 1-eps]`, eps default `1e-6`, before logit transform.

### **6.2 Resampling cadence**

* Default: **5 minutes** (aligns with alerting)  
* Backtest: support 1m / 15m / 1h

**Missingness handling**

* Forward-fill allowed up to `max_gap` (default: 60 minutes)  
* Beyond `max_gap`, mark segment as invalid for TSFM; force baseline-only

### **6.3 Optional covariates (future/past)**

Supported but not required for MVP:

* Past covariates: volume, OI change, spread, depth, volatility proxy  
* Future covariates: known calendars (e.g., scheduled announcement time) *if available*

---

## **7\. Model Runtime: tollama**

### **7.1 Why tollama**

We standardize TS forecasting through **tollama** so we can:

* Swap TSFMs without changing application logic  
* Run locally or in controlled infrastructure  
* Keep inference interface uniform across models  
* Control rollout: baseline-only → TSFM-on-top

### **7.2 Assumption**

`tollama` provides an API to run time-series models (e.g., Chronos/TimesFM class models) and return forecasts/quantiles.  
*(Exact endpoints may evolve; we treat tollama as the system-of-record runtime, and wrap it with our own adapter.)*

---

## **8\. Interfaces**

### **8.1 Internal Runner API (our service)**

#### **`POST /tsfm/forecast`**

Request:

{  
  "market\_id": "string",  
  "as\_of\_ts": "2026-02-20T12:00:00Z",  
  "freq": "5m",  
  "horizon\_steps": 12,  
  "quantiles": \[0.1, 0.5, 0.9\],  
  "y": \[0.41, 0.42, 0.40, "..."\],  
  "x\_past": {  
    "volume": \[ ... \],  
    "spread": \[ ... \]  
  },  
  "x\_future": {},  
  "transform": {  
    "space": "logit",  
    "eps": 1e-6  
  },  
  "model": {  
    "provider": "tollama",  
    "model\_name": "chronos|timesfm|...",  
    "model\_version": "optional",  
    "params": {  
      "temperature": 0.0  
    }  
  }  
}

Response:

{  
  "market\_id": "string",  
  "as\_of\_ts": "2026-02-20T12:00:00Z",  
  "freq": "5m",  
  "horizon\_steps": 12,  
  "quantiles": \[0.1, 0.5, 0.9\],  
  "yhat\_q": {  
    "0.1": \[ ... \],  
    "0.5": \[ ... \],  
    "0.9": \[ ... \]  
  },  
  "meta": {  
    "runtime": "tollama",  
    "model\_name": "chronos",  
    "model\_version": "2026-02-01",  
    "latency\_ms": 42,  
    "input\_len": 288,  
    "transform": "logit",  
    "fallback\_used": false,  
    "warnings": \[\]  
  }  
}

### **8.2 Adapter: tollama client (our code)**

We implement a **thin adapter** that:

* Converts our request format → tollama inference call  
* Converts tollama outputs → our standardized response  
* Handles retries, timeouts, and circuit breaking  
* Emits structured logs & metrics

---

## **9\. Baselines & Fallback (MUST)**

Even with tollama, we must always support fallback. Baselines produce bands directly.

Baselines (same as PRD1 direction):

1. **EWMA band** (mean \+ scale from EWMA variance)  
2. **Local-level Kalman band**  
3. **Rolling quantile band**

Fallback logic:

* If tollama times out / errors / returns invalid quantiles → baseline bands  
* If series has large missing gaps or too few points → baseline bands  
* If market is extremely illiquid (below threshold) → baseline-only (configurable)

---

## **10\. Post-processing & Safety Checks**

### **10.1 Bounds**

After inverse transform (if logit):

* Clip outputs to `[0,1]`

### **10.2 Quantile monotonicity (avoid “quantile crossing”)**

If any step violates `q10 <= q50 <= q90`, apply monotonic fix:

* Sort quantiles per timestep (rearrangement)  
* Record warning \+ counter metric

### **10.3 Interval sanity checks**

* If interval width is unreasonably narrow on a jumpy market (below min width), expand to min width (configurable)  
* If interval width is absurdly wide (above max width), clamp or flag

---

## **11\. Conformal Calibration**

### **11.1 Goal**

For each horizon and quantile band, achieve target coverage (e.g., 80% or 90%) under nonstationarity.

### **11.2 Method (Rolling)**

* Maintain **rolling calibration window** of recent errors (e.g., last 14 days)  
* Compute adjustment to widen/narrow bands so empirical coverage matches target  
* Support **conditional coverage monitoring** by:  
  * liquidity bucket  
  * time-to-expiry (TTE) bucket  
  * category

### **11.3 Outputs**

Store both:

* raw TSFM bands  
* conformal-adjusted bands  
  plus the calibration window parameters used.

---

## **12\. Evaluation Plan (Offline)**

### **12.1 Splits**

* Primary: time-based split  
* Secondary: **event-holdout split** (hold out entire events to avoid leakage)

### **12.2 Metrics**

**Interval metrics (primary)**

* Empirical coverage @ 80/90%  
* Average interval width  
* Winkler score (optional)  
* Pinball loss (quantile loss)

**Operational metrics (product-aligned)**

* Band breach precision proxy:  
  * fraction of breaches followed by “meaningful move” within X hours  
* Alert usefulness:  
  * breach \+ confirmation gate hit rate

**Point metrics (secondary)**

* MAE / RMSE on median (q50)

---

## **13\. Runtime / Performance Requirements (SLO)**

### **13.1 MVP SLO**

* Batch (top N markets): complete within **≤ 60s** per cycle (configurable N)  
* Per-request p95 latency: **≤ 300ms** (excluding queueing), baseline fallback ≤ 50ms  
* Timeout to tollama: 2s (default), retry 1x with jitter

### **13.2 Scaling Strategy**

* Inference is only for top‑N markets selected by:  
  * volume/OI  
  * user watchlists  
  * alert candidate list  
* Cache identical requests within a short TTL (e.g., 1 minute)

---

## **14\. Observability**

### **14.1 Metrics**

* `tollama_latency_ms` (p50/p95/p99)  
* `tollama_error_rate`  
* `fallback_rate` (baseline fallback fraction)  
* `quantile_crossing_rate`  
* `coverage_rolling_{bucket}` (by liquidity/TTE/category)  
* `interval_width_{bucket}`  
* `breach_rate` and `breach_followthrough_rate`

### **14.2 Logs**

Structured logs with:

* market\_id  
* as\_of\_ts  
* model\_name/version  
* input length, missingness ratio  
* warnings (crossing, clipping, fallback reason)

---

## **15\. Model Selection & Licensing Policy**

### **15.1 Principle**

Only models allowed for production must be:

* commercially usable under their license  
* supported by tollama runtime

### **15.2 Enforcement (hard guardrail)**

* Model registry includes `license_tag = {commercial_ok | research_only}`  
* Production deploy config rejects `research_only`  
* CI test ensures no research-only model is referenced in prod config

---

## **16\. Security & Deployment**

* tollama runs in a private network segment (no public exposure)  
* Runner service authenticates to tollama with:  
  * network allowlist \+ token  
* Rate limit incoming inference requests  
* Circuit breaker: if tollama unhealthy, switch to baseline-only mode

---

## **17\. Deliverables**

1. `TollamaAdapter` library (client wrapper \+ retries \+ parsing)  
2. `TSFMRunnerService` (`/tsfm/forecast`)  
3. Baseline band module \+ fallback policy  
4. Post-processing checks: clipping \+ monotonic quantiles  
5. Rolling conformal calibration module  
6. Offline eval notebooks/pipeline with:  
   * time split \+ event-holdout split  
   * interval/operational metrics dashboard  
7. Monitoring dashboards & alerts (latency/error/fallback/coverage)

---

## **18\. Acceptance Criteria (AC)**

1. **Functional**  
* Given a valid `y` series, runner returns q10/q50/q90 forecasts for the requested horizon.  
* If tollama fails, baseline bands are returned with `fallback_used=true`.  
2. **Correctness**  
* All outputs are within \[0,1\].  
* No quantile crossing after post-processing.  
* Conformal-adjusted bands meet target coverage ± tolerance on validation.  
3. **Operational**  
* Meets SLO (p95 latency, batch cycle time).  
* Observability metrics are emitted and dashboards can be built.  
4. **Product alignment**  
* Band breach events computed from these bands are stable enough to support Gate 1 alerting.

---

## **19\. Open Questions (to resolve during implementation)**

* Exact tollama API contract (endpoints, payload schema, model naming).  
  → Solution: our adapter isolates this; update adapter as tollama evolves.  
* Default y-definition: mid vs last trade for markets without active quotes.  
* Default calibration window length (tradeoff: responsiveness vs noise).  
* Top‑N selection strategy for inference in production.

---

## **20\. Appendix — Recommended Defaults (Config v0)**

freq: 5m  
input\_len\_steps: 288          \# 24h @ 5m  
horizon\_steps: 12             \# 1h @ 5m  
quantiles: \[0.1, 0.5, 0.9\]  
transform:  
  space: logit  
  eps: 1e-6  
missing:  
  max\_gap\_minutes: 60  
timeouts:  
  tollama\_timeout\_s: 2.0  
  retry\_count: 1  
fallback:  
  baseline\_only\_liquidity\_threshold: low  
conformal:  
  enabled: true  
  rolling\_window\_days: 14  
  target\_coverage: 0.9

---

.

