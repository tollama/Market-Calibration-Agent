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
  - 연속 실패 기반 circuit breaker (`3회 실패`, `30s` cooldown)
- `TollamaAdapter` 커넥션 풀 기본값 추가:
  - `max_connections=200`
  - `max_keepalive_connections=20`
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
- `min_interval_width=0.02, max_interval_width=0.9`: 과도한 협/광 밴드 방지
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
