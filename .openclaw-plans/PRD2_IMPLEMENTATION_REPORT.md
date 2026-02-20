# PRD2 IMPLEMENTATION REPORT — TSFM Runner (via tollama)

## Scope completed
Implemented PRD2 end-to-end in sequential stages with production-oriented defaults and fallback-first safety.

## Stage-by-stage implementation
1. **Stage 1: API Contract**
   - Added TSFM request/response schemas and `/tsfm/forecast` endpoint.
2. **Stage 2: Tollama Adapter**
   - Added `TollamaAdapter` with timeout, retry(+jitter), normalized parsing, and runtime metadata.
3. **Stage 3: Runner Service**
   - Added `TSFMRunnerService` orchestration for preprocessing, inference, and standardized output.
4. **Stage 4: Safety/Post-processing**
   - Added clipping to [0,1], quantile crossing fix, interval sanity width enforcement.
5. **Stage 5: Conformal hook**
   - Integrated optional conformal adjustment output (`conformal_last_step`) via existing calibration module.
6. **Stage 6: Baseline fallback**
   - Added fallback triggers and baseline generation (EWMA) with explicit metadata/warnings.
7. **Stage 7: Licensing guardrails**
   - Added model registry config with `license_tag` and test to prevent research-only models in prod allowlist.
8. **Stage 8: Tests/verification**
   - Added unit/API tests covering main path, fallback, post-processing safety, and license policy.

## Files changed
- `runners/tollama_adapter.py` (new)
- `runners/tsfm_service.py` (new)
- `api/schemas.py` (updated)
- `api/app.py` (updated)
- `configs/tsfm_models.yaml` (new)
- `tests/unit/test_tsfm_runner_service.py` (new)
- `tests/unit/test_api_tsfm_forecast.py` (new)
- `tests/unit/test_tsfm_model_license_guard.py` (new)
- `docs/prd2-implementation-status.md` (new)
- `README.md` (updated link)
- `.openclaw-plans/PRD2_IMPLEMENTATION_REPORT.md` (new)

## Defaults chosen and rationale
- `freq=5m`, `horizon_steps=12`, `input_len_steps=288`: aligns with PRD alert cadence and 24h context.
- `quantiles=[0.1,0.5,0.9]`: baseline interval for gate/breach workflow.
- `transform=logit`, `eps=1e-6`: bounded probability stability.
- `tollama timeout=2.0s`, `retry=1`: PRD SLO-aligned resilient inference.
- `min_points_for_tsfm=32`: avoid unstable low-context model calls.
- `baseline_method=EWMA`: robust low-latency fallback.
- `baseline_only_liquidity=low`: conservative handling for illiquid markets.
- `min_interval_width=0.02`, `max_interval_width=0.9`: protect against pathological narrow/wide intervals.

## Verification executed
Command:
```bash
python3 -m pytest tests/unit/test_tsfm_runner_service.py tests/unit/test_api_tsfm_forecast.py tests/unit/test_tsfm_model_license_guard.py tests/unit/test_baseline_bands.py tests/unit/test_tsfm_base_contract.py
```
Result: **15 passed**.

## Run instructions
- Docs: `docs/prd2-implementation-status.md`
- Endpoint: `POST /tsfm/forecast`
- Start API: `uvicorn api.app:app --reload`

## Remaining risks / follow-up
1. **tollama endpoint schema drift risk**: adapter isolates this, but upstream API changes still require adapter update.
2. **No real tollama integration test in CI**: current coverage is unit-level with adapter stubs.
3. **Conformal currently attached as optional last-step output**: full rolling online calibrator persistence/job wiring can be expanded in next iteration.
4. **Observability export hooks are metadata-ready but no metrics backend wiring yet**.
