# SINGLE APP 아키텍처 설계 (Polymarket Calibration Agent)

## 1) 목표

현재 레포의 구성(배치 파이프라인 + FastAPI + Streamlit + TSFM runtime 연동)을 기준으로,
**운영/개발 관점에서 하나의 배포 단위(single app)로 시작**하고,
트래픽/팀 규모 증가 시 **점진적으로 분리 가능한 구조**를 설계한다.

핵심 목표:
- 단일 프로세스/단일 배포로 빠른 개발-검증-운영 사이클 확보
- PRD1(캘리브레이션/알림) + PRD2(TSFM forecast)를 동일 앱 경계에서 일관 운영
- 인증/레이트리밋/캐시/fallback/circuit-breaker 등 안전장치를 기본 내장
- 데이터 계약(raw/derived, artifacts)을 유지하며 향후 서비스 분리 비용 최소화

---

## 2) 현재 레포 구조 기반 요구사항 정리

아래는 실제 디렉터리/모듈을 기준으로 정리한 single app 요구사항이다.

### 2.1 기능 요구사항
- 데이터 수집
  - `connectors/polymarket_gamma.py`, `connectors/polymarket_ws.py`, `connectors/polymarket_subgraph.py`
- 배치/실시간 처리
  - `pipelines/daily_job.py`, `pipelines/realtime_ws_job.py`, `pipelines/*`
- 피처/캘리브레이션/신뢰도
  - `features/build_features.py`, `calibration/*`, `agents/alert_agent.py`
- API 제공
  - `api/app.py` (scoreboard, alerts, markets, postmortem, `/tsfm/forecast`, metrics)
- TSFM 서빙
  - `runners/tsfm_service.py`, `runners/tollama_adapter.py`, `runners/baselines.py`
- UI
  - `demo/live_demo_app.py` (Streamlit)

### 2.2 비기능 요구사항
- 설정 일관성
  - `configs/default.yaml`, `configs/alerts.yaml`, `configs/tsfm_runtime.yaml`, `configs/models.yaml`
- 저장소 계약 유지
  - `storage/layout.md`의 raw/derived 파티셔닝 규칙 준수
- 운영 검증 자동화
  - `scripts/rollout_hardening_gate.sh`, `scripts/prd2_verify_all.sh`, `scripts/openapi_smoke.py`
- 보안/안정성
  - `/tsfm/forecast` 토큰 인증 + placeholder token 차단 + 분당 요청 제한(`api/app.py`)

---

## 3) 컴포넌트 다이어그램 (텍스트)

```text
[External Sources]
  - Polymarket Gamma API
  - Polymarket WebSocket
  - Polymarket Subgraph
  - Tollama Runtime (외부/별도 프로세스)

          | (ingest/stream)
          v
+------------------------------------------------------+
|                 Single App (Python)                 |
|------------------------------------------------------|
|  A. Ingestion Layer                                 |
|   - connectors/*                                     |
|                                                      |
|  B. Processing Layer                                 |
|   - pipelines/daily_job.py                           |
|   - pipelines/realtime_ws_job.py                     |
|   - features/build_features.py                       |
|   - calibration/*, agents/*                          |
|                                                      |
|  C. Serving Layer                                    |
|   - FastAPI: api/app.py                              |
|   - Streamlit: demo/live_demo_app.py                 |
|                                                      |
|  D. Forecast Runtime Layer                           |
|   - runners/tsfm_service.py                          |
|   - cache / circuit breaker / fallback / conformal   |
+------------------------------------------------------+
          |
          v
[Local Storage Root]
  - raw/<dataset>/dt=YYYY-MM-DD/*.jsonl
  - derived/<dataset>/dt=YYYY-MM-DD/*
  - derived/metrics/scoreboard.json, derived/alerts/alerts.json

(운영 관점)
- 하나의 배포 단위에서 API + 파이프라인 + UI를 실행
- 내부적으로 역할 분리(모듈화)하고 프로세스 분리는 점진 적용
```

---

## 4) 데이터모델 초안

현재 스키마/산출물(`api/schemas.py`, `storage/layout.md`, pipeline outputs) 기준의 최소 공통 모델.

### 4.1 핵심 엔티티

1) `Market`
- market_id (PK)
- category
- liquidity_bucket
- as_of

2) `ScoreboardRecord`
- market_id (FK)
- window (예: 90d)
- trust_score
- brier
- logloss
- ece
- as_of

3) `AlertRecord`
- alert_id (PK, optional)
- market_id (FK)
- ts
- severity (HIGH/MED/FYI)
- reason_codes[]
- evidence (json)
- llm_explain_5lines[]

4) `Postmortem`
- market_id
- content (markdown)
- source_path
- generated_at / resolved_at

5) `TSFMForecastRequest/Response` (API contract)
- Request: market_id, as_of_ts, freq, horizon_steps, quantiles, y, x_past, x_future, transform, model
- Response: yhat_q{quantile->series}, meta, conformal_last_step

### 4.2 저장소/파티셔닝
- Raw: `raw/<dataset>/dt=YYYY-MM-DD/*.jsonl`
- Derived: `derived/<dataset>/dt=YYYY-MM-DD/*.parquet|*.json`
- API 로더는 최신 partition fallback + 루트 fallback(`api/dependencies.py`) 유지

### 4.3 인덱싱/조회 관점 (향후 DB 도입 대비)
- `market_id + as_of` 복합 인덱스
- alerts: `ts desc`, `severity + ts`
- scoreboard: `window + trust_score`

---

## 5) API 초안 (Single App 기준)

현행 `api/app.py`를 유지하되, 버저닝과 내부/외부 경계를 명확히 한다.

### 5.1 Public Read API
- `GET /scoreboard?window=90d&tag=&liquidity_bucket=&min_trust_score=`
- `GET /alerts?since=&limit=&offset=&severity=`
- `GET /markets`
- `GET /markets/{market_id}`
- `GET /markets/{market_id}/metrics`
- `GET /postmortem/{market_id}`

### 5.2 Forecast API
- `POST /tsfm/forecast`
  - 인증 필수(Bearer 또는 X-API-Key)
  - 레이트리밋 적용
  - 실패 시 runtime fallback/baseline 반환 가능
- `POST /markets/{market_id}/comparison`
  - tollama vs baseline 비교 결과 반환

### 5.3 Observability API
- `GET /metrics`, `GET /tsfm/metrics`

### 5.4 권장 개선
- `/v1/*` 프리픽스 도입 (하위 호환 기간 운영)
- OpenAPI 문서에 에러 코드 표준화 (`401/429/400/5xx`)
- forecast 메타에 degradation/fallback reason 표준 필드 고정

---

## 6) 보안 / 리스크 가드레일

`api/app.py`, `docs/ops/*`의 운영 방식을 기준으로 single app 필수 가드레일을 정의한다.

### 6.1 인증/인가
- `/tsfm/forecast` 토큰 인증 강제
- placeholder token 금지(`demo-token`, `changeme` 등)
- 내부 운영 API(향후 추가)는 별도 admin token 또는 네트워크 ACL 분리

### 6.2 트래픽 보호
- per-token/IP rate limit (현재 분당 제한)
- burst 제어 + `Retry-After` 준수
- 과도한 horizon/quantiles/series 길이 요청 방어(스키마/서비스 레벨)

### 6.3 모델/출력 안전성
- quantile monotonicity 보정
- [0,1] clip
- interval width min/max clamp
- fallback 시 meta에 `fallback=true`, `reason_code` 강제

### 6.4 데이터 품질/정합성
- pipeline checkpoint/retry 유지
- dt partition deterministic write (idempotent)
- ingest dual-write(legacy/canonical) 종료 시점 명시 필요

### 6.5 운영 리스크
- 단일 앱 장애 시 API+배치+UI 동시 영향
  - 대응: 프로세스 supervisor, healthcheck, graceful restart, stale artifact serve
- 외부 runtime(Tollama) 장애
  - 대응: circuit breaker + baseline-only degradation 모드

---

## 7) 배포 전략: 단일 배포 → 분리 확장

### Stage A: Single Deployment (초기 권장)
- 단일 리포/단일 이미지(또는 단일 VM 서비스)
- 실행 구성 예시:
  - 프로세스1: FastAPI (`api/app.py`)
  - 프로세스2: Streamlit (`demo/live_demo_app.py`)
  - 프로세스3: Scheduler(일배치/실시간잡 launcher)
- 공통 설정/스토리지 루트 공유
- 운영 게이트:
  - `scripts/rollout_hardening_gate.sh`
  - `scripts/prd2_verify_all.sh`

### Stage B: 논리 분리 (같은 배포 내)
- 코드/런타임 책임 분리
  - `app-api`, `app-worker`, `app-ui` 엔트리포인트 분리
- 리소스 제한(CPU/memory)과 장애 격리 우선 적용
- metrics/log 라벨에 role 추가

### Stage C: 물리 분리 (확장 단계)
- API 서비스와 Worker 서비스 분리 배포
- TSFM runtime 연동 계층 별도 서비스화 옵션
- Artifact store/S3 + 메타DB 도입
- Queue 기반 job orchestration (예: Redis/Celery or cloud queue)

---

## 8) 운영 체크리스트

### 8.1 배포 전
- [ ] `requirements.lock` 동기화 설치 확인
- [ ] `configs/*.yaml` 환경별 값 주입 확인
- [ ] `TSFM_FORECAST_API_TOKEN` 실토큰 적용(placeholder 금지)
- [ ] OpenAPI smoke (`scripts/openapi_smoke.py`)
- [ ] Hardening gate (`scripts/rollout_hardening_gate.sh`)

### 8.2 배포 직후
- [ ] `/metrics` scrape 정상
- [ ] `/scoreboard`, `/alerts`, `/markets` 응답 정상
- [ ] `/tsfm/forecast` 인증/레이트리밋 동작 점검
- [ ] fallback/circuit breaker 메트릭 점검

### 8.3 일상 운영
- [ ] daily_job 성공률/소요시간 모니터링
- [ ] realtime_ws_job 지연/누락 모니터링
- [ ] alert severity 분포 이상치 점검
- [ ] postmortem 산출물 누락률 점검
- [ ] 주간 단위로 정책 임계치(신뢰도/알림) 재점검

### 8.4 장애 대응
- [ ] Tollama 장애 시 baseline-only 전환 절차 문서화
- [ ] derived artifact stale serve 정책 확인
- [ ] 재처리(runbook): ingest → cutoff → feature → scoreboard 재생성

---

## 9) 단계별 실행계획 (Week 1~)

### Week 1 — 단일 앱 런타임 정리
- 단일 실행 엔트리포인트 설계(`server`, `worker`, `ui` 명령 세트)
- 설정 로더 통합(환경변수 우선순위 표준화)
- `/v1` API 프리픽스 초안 + 호환 라우팅

### Week 2 — 데이터 계약/아티팩트 안정화
- raw/derived 산출물 스키마 버전 필드 도입
- API 로더의 fallback 규칙 문서화/테스트 강화
- ingest dual-write 종료 조건/마이그레이션 계획 확정

### Week 3 — 보안/신뢰성 강화
- forecast 요청 상한(horizon, series length) 강제
- 레이트리밋 identity 전략 개선(token + forwarded IP)
- circuit breaker/degradation 상태 운영 대시보드 고정

### Week 4 — 배포 표준화
- 단일 이미지 빌드 + 역할별 실행 템플릿(systemd or container)
- smoke/e2e 파이프라인 정리
- 운영 runbook(복구 절차, 장애 시나리오) 확정

### Week 5+ — 분리 확장 준비
- worker 분리 PoC (API와 독립 배치)
- artifact store 외부화(S3/Blob) 검토
- 메타데이터 DB 도입 설계(시장/알림/실행이력)

---

## 10) 미결정사항 (Open Questions)

1. 단일 앱의 프로세스 관리 표준
- systemd 기반 멀티서비스 vs 단일 컨테이너 내 supervisor vs k8s 멀티배포

2. 영속 스토리지 전략
- 현재 파일기반(raw/derived) 유지 기간과 외부 object storage 전환 시점

3. 메타데이터 DB 도입 범위
- alerts/scoreboard/postmortem 인덱싱만 우선할지, 전체 이벤트 소싱까지 확장할지

4. TSFM runtime 배치
- 동일 호스트 인접 배치 vs 별도 전용 inference 서비스

5. 보안 경계
- 내부 운영 엔드포인트 분리 필요성(현재 public read API와 동일 앱)

6. UI 전략
- Streamlit 유지 vs 향후 독립 프론트엔드로 전환 시점/조건

7. SLA/SLO
- forecast p95 latency, daily pipeline 완료시각, 데이터 최신성 목표치 정의 필요

---

## 부록) 현재 구조 매핑 요약
- API: `api/app.py`, `api/schemas.py`, `api/dependencies.py`
- Runner: `runners/tsfm_service.py`, `runners/tollama_adapter.py`, `runners/baselines.py`
- Pipeline: `pipelines/daily_job.py`, `pipelines/realtime_ws_job.py`, `pipelines/*`
- Calibration/Features: `calibration/*`, `features/build_features.py`
- Connectors: `connectors/*`
- UI: `demo/live_demo_app.py`
- Storage contract: `storage/layout.md`
- Ops scripts: `scripts/rollout_hardening_gate.sh`, `scripts/prd2_verify_all.sh`, `scripts/openapi_smoke.py`
