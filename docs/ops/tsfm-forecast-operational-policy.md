# TSFM Forecast Operational Policy

## Environment token expectations

### Inbound API protection
- `TSFM_FORECAST_API_TOKEN` (required in secure environments) controls `/tsfm/forecast` auth.
- Request auth header must be:
  - `Authorization: Bearer <token>` (preferred) or
  - `X-API-Key: <token>`
- Placeholder-like values are rejected:
  - `changeme`, `changemeplease`, `tsfm-dev-token`, `dev-token`, `demo-token`, `example`, `your-token`, `placeholder`
- Optional config override from `configs/default.yaml` under `api.tsfm_forecast.token_env_var`.

### Downstream Tollama runtime
- `TOLLAMA_TOKEN` is passed as `Authorization: Bearer` when set.
- Other optional settings:
  - `TOLLAMA_BASE_URL` (default `http://localhost:11435`)
  - `TOLLAMA_ENDPOINT` (default `/v1/timeseries/forecast`)
  - `TOLLAMA_MODEL_NAME`, `TOLLAMA_MODEL_VERSION`
  - `TOLLAMA_TIMEOUT_S`, `TOLLAMA_RETRY_COUNT`

## Forecast input constraints

- `freq`: string `m`/`h` periods only (e.g. `5m`, `1h`), validated in service.
- `horizon_steps`: integer `>= 1`.
- `quantiles`: request quantiles are validated; unsupported values are coerced to default `[0.1, 0.5, 0.9]` and emit warning `unsupported_quantiles_requested;using_default`.
- `y` constraints:
  - list with 2 to 20,000 points,
  - finite numeric values only,
  - no NaN/inf,
  - if provided, `y_ts` length must match `y`.
- `max_gap_minutes` may be used to tighten gap acceptance (service default is 60).

## Fallback behavior

Fallback is intentional and visible in response `meta`:
- `fallback_used: true` indicates fallback path was taken.
- Typical fallback reasons:
  - `too_few_points`
  - `baseline_only_liquidity_bucket`
  - `max_gap_exceeded`
  - `degradation_baseline_only`
  - `circuit_breaker_open`
  - `stale_if_error`
  - `tollama_error:*`
  - `baseline_error:*`
- If cache exists and tollama fails, stale cache can be used with `cache_stale=true` and `fallback_reason=stale_if_error`.

Operational defaults in hardening:
- baseline fallback method: `EWMA`
- min points before tollama: `32`
- circuit breaker and degradation paths are enabled with conservative thresholds in `configs/tsfm_runtime.yaml`.

## Rollback / traffic-stop conditions

For TSFM rollout decisions, immediate rollback is triggered when any of:
- p95 latency crosses rollout gate thresholds for two consecutive 5m windows,
- error rate window breach,
- invalid-output occurs,
- sustained high fallback rate or breaker-open rate in escalation windows.

See: `docs/ops/tsfm-canary-rollout-runbook.md` (clean-window gates and full rollback matrix).

## 운영자가 따라할 수 있는 점검(4블록)

- 사전조건
  - `TSFM_FORECAST_API_TOKEN`가 실제 토큰인지 확인(placeholder 아님).
  - 토큰이 설정된 서비스/프록시가 `/tsfm/forecast` 라우트를 노출 중인지 확인.
- 실행
  - 운영 중 `/tsfm/forecast`에 대한 샘플 요청(유효 토큰)으로 반환 구조와 `meta.fallback_used`/`meta.warnings` 확인.
- 검증
  - `yhat_q` 단조성(`q10<=q50<=q90`) 및 값 범위(0~1) 확인.
  - 과도한 fallback, invalid-output 로그, breaker/degradation 상태를 메트릭으로 모니터.
- 실패시 대응
  - `fallback_used=true`가 잦으면 입력 길이/`y_ts` 품질, 라이브러리 지연, Tollama 연동 상태를 우선 점검.
  - 치명 상태 시 가드레일(롤백/트래픽 억제) 경로를 canary runbook에 따라 즉시 적용.
