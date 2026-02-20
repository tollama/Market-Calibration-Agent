# PRD2 구현 상태 — TSFM Runner (via tollama)

## Stage 1 — 목적/인터페이스 고정
- `POST /tsfm/forecast` 계약을 `api/schemas.py`에 추가:
  - `TSFMForecastRequest`
  - `TSFMForecastResponse`
- API 엔드포인트를 `api/app.py`에 추가.

## Stage 2 — Tollama Adapter 구현
- `runners/tollama_adapter.py`
  - `TollamaConfig`
  - `TollamaAdapter.forecast(...)`
  - timeout/retry(지터 포함), 응답 파싱, 표준 메타 반환.

## Stage 3 — TSFM Runner Service 구현
- `runners/tsfm_service.py`
  - 입력 시계열 슬라이싱(`input_len_steps`)
  - logit/inv-logit 변환
  - tollama 호출
  - baseline fallback(EWMA)
  - 출력 표준화(`yhat_q`, `meta`)

## Stage 4 — Post-processing/Safety
- [0,1] clipping
- quantile crossing 고정(시점별 정렬)
- interval min/max width sanity enforcement
- warning 메타 축적

## Stage 5 — Conformal 연동
- 기존 `calibration.conformal` 모듈 재사용
- 서비스에서 옵션으로 `conformal_last_step` 반환 지원

## Stage 6 — Baseline/Fallback 정책
- fallback 트리거:
  - tollama 호출 실패
  - 입력 길이 부족
  - 저유동성 bucket(기본: `low`)
- fallback 사용 시 `meta.fallback_used=true` 및 reason warning 기록

## Stage 7 — 라이선스 가드레일
- `configs/tsfm_models.yaml` 신설
  - 모델별 `license_tag`
  - `prod.allowed_models`
- 단위테스트로 prod에 `research_only` 모델 미포함 강제

## Stage 8 — 테스트/검증
- `tests/unit/test_tsfm_runner_service.py`
  - 정상 경로
  - adapter 오류 fallback
  - crossing/clipping 안정성
  - cache hit 메타 플래그
  - circuit breaker open fallback
- `tests/unit/test_api_tsfm_forecast.py`
  - API contract test
- `tests/unit/test_tsfm_model_license_guard.py`
  - 라이선스 가드레일 test

## Stage 9 — 성능/처리량 강화
- `TSFMRunnerService`에 성능 안정화 기본기 추가:
  - 요청 해시 기반 TTL cache (`cache_ttl_s=60`)
  - rolling-window 기반 circuit breaker (`failure_rate_to_open=1.0`, `cooldown=120s`)
  - stale-if-error cache (`stale_if_error_s=120`)
- `TollamaAdapter` 커넥션 풀 기본값 추가:
  - `max_connections=200`
  - `max_keepalive_connections=50`
- 성능 스모크 벤치마크 추가:
  - `pipelines/bench_tsfm_runner_perf.py`
  - p95/사이클 시간 SLO budget check 내장

---

## Defaults (v0) 및 선택 이유
- `freq=5m`: alert cadence 정렬
- `input_len_steps=288`: 24h 컨텍스트
- `horizon_steps=12`: 1h 예측
- `quantiles=[0.1,0.5,0.9]`: Gate/coverage 실무 표준
- `transform=logit, eps=1e-6`: bounded target 안정화
- `tollama timeout=1.2s, retry=1(+exp backoff/jitter)`: p95/p99 tail-latency 방어
- `baseline_method=EWMA`: 계산비용 낮고 fallback latency 유리
- `min_points_for_tsfm=32`: 극단적 짧은 시계열 보호
- `min_interval_width=0.02, max_interval_width=0.6`: 과도한 협/광 밴드 방지
- `baseline_only_liquidity=low`: 극저유동 시장에서는 보수적 운영
- `cache_ttl_s=60`: 5분 cadence에서 동일 요청 burst 흡수
- `circuit_breaker_failures=5, cooldown=120s`: flapping 줄이고 안정적 복구 유도
- `http pool: max_connections=200, keepalive=50`: top-N 배치 처리량 headroom 확보

## 실행 방법
1. 의존성 설치
```bash
pip install -e .[dev]
```
2. API 실행
```bash
uvicorn api.app:app --reload
```
3. 요청 예시
```bash
curl -X POST http://127.0.0.1:8000/tsfm/forecast \
  -H 'content-type: application/json' \
  -d '{
    "market_id":"m-1",
    "as_of_ts":"2026-02-20T12:00:00Z",
    "freq":"5m",
    "horizon_steps":12,
    "quantiles":[0.1,0.5,0.9],
    "y":[0.41,0.42,0.40,0.43,0.44,0.45,0.46,0.45,0.44,0.43,0.42,0.41,0.40,0.41,0.42,0.43,0.44,0.45,0.46,0.47,0.48,0.47,0.46,0.45,0.44,0.43,0.42,0.41,0.40,0.41,0.42,0.43],
    "transform":{"space":"logit","eps":1e-6},
    "model":{"provider":"tollama","model_name":"chronos","params":{"temperature":0.0}}
  }'
```

## 입력/출력 요약
- 입력: market_id, as_of, freq, horizon, quantiles, y(+선택 covariates)
- 출력: `yhat_q`(quantile path), `meta`(runtime/latency/fallback/warnings)

## 검증 절차
```bash
pytest tests/unit/test_tsfm_runner_service.py tests/unit/test_api_tsfm_forecast.py tests/unit/test_tsfm_model_license_guard.py
```
- 기대: 전부 PASS
- 실패 시 우선순위:
  1) API schema 불일치
  2) fallback 동작/quantile monotonicity
  3) config license guard

## 성능 스모크 벤치마크 (재현 가능)
```bash
PYTHONPATH=. python3 pipelines/bench_tsfm_runner_perf.py --requests 200 --unique 20 --adapter-latency-ms 15 --budget-p95-ms 300 --budget-cycle-s 60
PYTHONPATH=. python3 pipelines/bench_tsfm_runner_perf.py --requests 200 --unique 200 --adapter-latency-ms 15 --budget-p95-ms 300 --budget-cycle-s 60
```
- 체크 항목:
  - `latency_p95_ms <= 300`
  - `elapsed_s <= 60`
- 기대 출력: 마지막 줄 `SLO_PASS`

## PRD1+PRD2 CI-release gap closure
- CI(`.github/workflows/ci.yml`)에 `prd2-release-gate` 잡을 추가해 PRD2 원커맨드 게이트(`scripts/prd2_verify_all.sh`)를 필수 통과 조건으로 승격.
- CI unit 잡에 PRD1 핵심 AC 회귀(`I-01/I-15/I-20`)를 명시 게이트로 추가해 요구사항 기반 실패 지점을 빠르게 식별 가능하게 정렬.
- PRD2 게이트 결과물(`prd2_verify_summary.json`, `prd2_release_audit_report.json`, 단계 로그)을 CI 아티팩트로 업로드하도록 보강.
- `scripts/prd2_verify_all.sh`/`scripts/prd2_release_audit.py` 기본 인터프리터를 `python3.11`로 고정하고, JSON 직렬화 경로까지 동일 인터프리터를 사용하도록 통일.
- release audit 스크립트에 `--output-json` 옵션을 추가해 릴리스 증적(report artifact) 자동 수집을 지원.

## PRD1+PRD2 regression sweep
- 실행 시각: 2026-02-21 05:22 (KST)
- Python: `python3.11`
- PRD1 critical constraints quick check:
  - I-13: Brier/LogLoss/ECE/slope/intercept + `category×liquidity×TTE` 세그먼트, parquet+markdown 출력
  - I-15: Gate1(band breach) + Gate2(OI/volume) + Gate3(ambiguity low) 기반 alert_event 생성
- PRD2 AC quick check:
  - 기능: q10/q50/q90 반환, tollama 실패 시 fallback(`fallback_used=true`)
  - 정확성: `[0,1]` clipping, quantile non-crossing, conformal coverage 목표 충족
  - 운영: SLO/관측성 지표, Gate1 연계 안정성
- 실행 커맨드:
  - `PYTHON_BIN=python3.11 python3 scripts/prd2_release_audit.py`
  - `PRD2_VERIFY_PYTHON_BIN=python3.11 scripts/prd2_verify_all.sh`
- 결과:
  - `scripts/prd2_release_audit.py`: **PASS** (blocker 11/11, p1 6/6)
  - `scripts/prd2_verify_all.sh`: **PASS** (unit/integration/perf/audit 전 단계 통과)
  - 산출물: `artifacts/prd2_verify_summary.json`
- 회귀 수정 필요 사항: 없음 (green 상태 유지)
