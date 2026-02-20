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
- `tests/unit/test_api_tsfm_forecast.py`
  - API contract test
- `tests/unit/test_tsfm_model_license_guard.py`
  - 라이선스 가드레일 test

---

## Defaults (v0) 및 선택 이유
- `freq=5m`: alert cadence 정렬
- `input_len_steps=288`: 24h 컨텍스트
- `horizon_steps=12`: 1h 예측
- `quantiles=[0.1,0.5,0.9]`: Gate/coverage 실무 표준
- `transform=logit, eps=1e-6`: bounded target 안정화
- `tollama timeout=2s, retry=1`: SLO와 안정성 균형
- `baseline_method=EWMA`: 계산비용 낮고 fallback latency 유리
- `min_points_for_tsfm=32`: 극단적 짧은 시계열 보호
- `min_interval_width=0.02, max_interval_width=0.9`: 과도한 협/광 밴드 방지
- `baseline_only_liquidity=low`: 극저유동 시장에서는 보수적 운영

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
