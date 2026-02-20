# 02-architecture.md

## 1) 아키텍처 목표와 원칙
- 목표: Polymarket 시장 확률의 캘리브레이션 품질을 배치(MVP-1)와 준실시간(MVP-2)으로 측정하고, 신뢰도 점수/알림/사후 리포트를 읽기전용으로 제공한다.
- 원칙:
  - 원본보존 우선: `raw` 불변 저장, `derived`는 재생성 가능해야 함.
  - 결정론 우선: 동일 입력 + 동일 버전 => 동일 출력.
  - 모듈 교체 가능성: TSFM, LLM, 저장소, API 클라이언트는 인터페이스 분리.
  - 운영 안정성: 재시도/백오프/체크포인트/idempotency 내장.
  - 스키마 계약 기반: pydantic + parquet 스키마 고정으로 파이프라인 결합도 축소.

## 2) 시스템 컴포넌트 설계

### 2.1 상위 컴포넌트
1. `Discovery & Ingestion`
- 역할: Gamma/Subgraph/(MVP-2에서 WS) 데이터 수집
- 출력: `raw/gamma`, `raw/subgraph`, `raw/ws`

2. `Normalization & Registry`
- 역할: market/event 식별자 정규화, 상태/라벨 정제, 레지스트리 이력 관리
- 출력: `market_registry`, `market_registry_history`, `label_status`

3. `Snapshot & Cutoff Builder`
- 역할: 공통 스냅샷 생성, T-24h/T-1h/Daily 컷오프 선택
- 출력: `market_snapshot`, `cutoff_snapshot`

4. `Feature & Forecast Layer`
- 역할: 시계열/유동성 피처 생성, 베이스라인 밴드(EWMA/Kalman/RQ), TSFM 밴드, Conformal 보정
- 출력: `feature_frame`, `forecast_band`

5. `Scoring & Calibration`
- 역할: Brier/LogLoss/ECE/reliability 계산, Trust Score 산식 계산
- 출력: `calibration_metrics`, `reliability_curve`, `trust_score`

6. `LLM Reasoning`
- 역할: 문항 품질 점수(JSON 강제), 설명 5줄 생성(증거 제한)
- 출력: `question_quality`, `llm_explain_5lines`

7. `Alert & Reporting`
- 역할: 밴드 이탈 + 3단계 게이트 + Severity 판정, Post-mortem markdown 생성
- 출력: `alert_event`, `reports/postmortem/*.md`

8. `Serving Layer`
- 역할: 조회 API/CLI 제공(`/scoreboard`, `/alerts`, `/postmortem/{market_id}`)
- 출력: JSON 응답 또는 CLI 출력

9. `Orchestration`
- 역할: 백필/증분 실행, 단계별 체크포인트, 실패 복구
- 출력: `run_metadata`, `pipeline checkpoints`

### 2.2 데이터 플로우
```text
Gamma REST ------\
                  +--> Raw Store --> Normalizer/Registry --> Snapshot/Cutoff --> Features --> Calibration/Trust --> Scoreboard
Subgraph GraphQL -/                                           \                                    \--> Alert Engine --> Alerts
                                                               \--> Forecast(Baseline/TSFM/Conformal)-/
WebSocket (MVP-2) ---------------------------------------------> Stream Aggregator ------------------/

Market text/rules --> Question Quality Agent --> question_quality -------------------------------> Trust/Alert/Post-mortem
Alert evidence ----> Explain Agent -------------------------------------------------------------> alert_event.llm_explain_5lines
```

### 2.3 실행 단위(잡)
- `daily_batch_job` (MVP-1 핵심)
  - discover -> ingest -> normalize -> snapshots -> cutoff -> features -> forecast -> calibration -> trust -> publish
- `stream_job` (MVP-2)
  - ws_ingest -> 1m/5m aggregate -> latest features -> alert evaluate -> publish
- `postmortem_job`
  - resolved market detect -> metrics join -> markdown render

## 3) 폴더/파일 레이아웃 제안

```text
.
├── api/
│   ├── app.py
│   ├── schemas.py
│   └── dependencies.py
├── agents/
│   ├── label_resolver.py
│   ├── calibration_agent.py
│   ├── alert_agent.py
│   ├── question_quality_agent.py
│   └── explain_agent.py
├── calibration/
│   └── conformal.py
├── connectors/
│   ├── polymarket_gamma.py
│   ├── polymarket_subgraph.py
│   └── polymarket_ws_market.py
├── features/
│   └── build_features.py
├── llm/
│   ├── client.py
│   ├── cache.py
│   ├── schemas.py
│   └── prompts/
│       ├── question_quality_v1.md
│       └── explain_5lines_v1.md
├── pipelines/
│   ├── daily_job.py
│   ├── build_cutoff_snapshots.py
│   └── common.py
├── registry/
│   ├── build_registry.py
│   └── conflict_rules.py
├── reports/
│   ├── postmortem.py
│   └── templates/
│       └── postmortem_v1.md.j2
├── runners/
│   ├── tsfm_base.py
│   ├── tsfm_chronos.py
│   ├── tsfm_timesfm.py
│   └── baselines.py
├── scoring/
│   └── trust_score.py
├── schemas/
│   ├── market_registry.py
│   ├── market_snapshot.py
│   ├── contracts.py
│   └── enums.py
├── storage/
│   ├── writers.py
│   ├── readers.py
│   └── layout.md
├── streaming/
│   └── aggregator.py
├── configs/
│   ├── default.yaml
│   ├── alerts.yaml
│   ├── models.yaml
│   └── logging.yaml
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
└── data/
    ├── raw/
    │   ├── gamma/dt=YYYY-MM-DD/
    │   ├── subgraph/dt=YYYY-MM-DD/
    │   └── ws/dt=YYYY-MM-DD/
    └── derived/
        ├── registry/
        ├── snapshot/
        ├── features/
        ├── forecast_band/
        ├── metrics/
        ├── alerts/
        └── reports/
```

### 3.1 모듈 의존 규칙
- `connectors` -> `storage`만 의존 가능 (`agents`, `api` 의존 금지)
- `agents`는 `schemas`, `features`, `scoring`, `calibration`에 의존 가능
- `api`는 계산 로직 직접 수행 금지, `derived` 조회 + 응답 직렬화만 수행
- `pipelines`는 오케스트레이션만 담당, 비즈니스 계산은 각 모듈 위임

## 4) 데이터 계약(Data Contracts)

### 4.1 공통 규칙
- 시간: 저장은 UTC ISO8601 (`ts`, `start_ts`, `end_ts`)
- 키: `market_id`/`event_id`는 문자열 canonical key
- 확률값: `[0,1]` 범위 보장, 부동소수 오차 허용치 `1e-9`
- 파티션: 일 단위 `dt=YYYY-MM-DD` + 주요 테이블은 `market_id` 보조 인덱스
- 스키마 버전: `schema_version` 필드 권장 (`v1` 시작)

### 4.2 핵심 엔터티 계약

#### A. `market_registry`
- PK: `market_id`
- 필수: `market_id`, `event_id`, `slug`, `outcomes`, `enableOrderBook`, `status`
- 제약:
  - `outcomes`와 `outcomePrices` 길이 일치
  - `status` enum: `ACTIVE|RESOLVED|VOID|UNRESOLVED`
  - slug 변경 시 `market_registry_history`에 append-only 기록

#### B. `market_snapshot`
- PK: `(ts, market_id)`
- 필수: `p_yes`, `p_no`, `volume_24h`, `open_interest`, `tte_seconds`, `liquidity_bucket`
- 제약:
  - binary 시장에서 `p_yes + p_no ~= 1`
  - `liquidity_bucket`: `LOW|MID|HIGH`

#### C. `cutoff_snapshot`
- PK: `(market_id, cutoff_type)`
- 필수: `cutoff_type(T-24h|T-1h|DAILY)`, `selected_ts`, `selection_rule`
- 제약:
  - 기본은 nearest-before, 없으면 nearest-any fallback

#### D. `question_quality`
- PK: `(market_id, prompt_version, llm_model)`
- 필수: `ambiguity_score`, `resolution_risk_score`, `trigger_events`, `rationale_bullets`
- 제약:
  - JSON schema strict validation
  - `rationale_bullets` 최대 5개

#### E. `feature_frame`
- PK: `(ts, market_id)`
- 필수: `returns`, `vol`, `volume_velocity`, `oi_change`, `tte_seconds`, `liquidity_bucket`
- 제약:
  - NaN 처리 정책 컬럼(`impute_flag`) 명시

#### F. `forecast_band`
- PK: `(ts, market_id, method, horizon_steps, step_seconds)`
- 필수: `q10`, `q50`, `q90`, `model_id`, `band_calibration`
- 제약:
  - `q10 <= q50 <= q90`
  - `band_calibration`: `raw|conformal`

#### G. `calibration_metrics`
- PK: `(window, segment_key, run_id)`
- 필수: `brier`, `logloss`, `ece`, `slope`, `intercept`, `sample_size`
- 제약:
  - 세그먼트 축: `category x liquidity_bucket x tte_bucket`

#### H. `trust_score`
- PK: `(ts, market_id)`
- 필수: `trust_score(0-100)`, `components`
- 제약:
  - `components`에 최소 `liquidity`, `stability`, `question_quality`, `manipulation_suspect`

#### I. `alert_event`
- PK: `alert_id` (UUIDv7 권장)
- 필수: `ts`, `market_id`, `severity`, `reason_codes`, `evidence`
- 제약:
  - `severity`: `HIGH|MED|FYI`
  - evidence 기반 설명만 허용 (`llm_explain_5lines`)

### 4.3 파이프라인 런 메타 계약
- `run_metadata` 필수 필드:
  - `run_id`, `pipeline_name`, `code_version`, `config_hash`, `data_interval_start`, `data_interval_end`, `status`, `error_stage`
- 목적:
  - 재현성 보장, 실패 지점 복구, 모델/프롬프트 버전 추적

## 5) API 통합 지점(API Integration Points)

### 5.1 외부 데이터 소스
1. Gamma REST
- 용도: 시장/이벤트 메타 + 스냅샷성 가격
- 통합 모듈: `connectors/polymarket_gamma.py`
- 핵심 정책:
  - 페이지네이션 순회
  - rate-limit + exponential backoff + timeout
  - raw JSONL 원본 저장

2. Subgraph GraphQL
- 용도: OI/활동/거래량 집계
- 통합 모듈: `connectors/polymarket_subgraph.py`
- 핵심 정책:
  - 쿼리 템플릿 파일화
  - 부분 실패 허용 + 실패 세그먼트 로깅
  - `market_id/event_id` 기준 정규화

3. CLOB WebSocket (MVP-2)
- 용도: 준실시간 market channel 수신
- 통합 모듈: `connectors/polymarket_ws_market.py`, `streaming/aggregator.py`
- 핵심 정책:
  - heartbeat + reconnect + backoff
  - 동적 구독(시장 활성 집합 기준)
  - 1m/5m 집계 OHLC + trade_count + realized_vol

4. LLM Provider
- 용도: 문항 품질 구조화, 설명 문장화
- 통합 모듈: `llm/client.py`, `llm/cache.py`
- 핵심 정책:
  - 캐시 키: `sha256(normalized_text + model + prompt_version + params)`
  - JSON schema 위반 시 최대 2회 재시도
  - 모델/프롬프트/샘플링 파라미터 버전 고정

### 5.2 내부 조회 API (읽기전용)
1. `GET /scoreboard?window=90d&tag=&liquidity_bucket=`
- 소스: `derived/metrics`, `derived/trust_score`
- 반환: 시장별 지표 + 신뢰도 + 필터링/페이징

2. `GET /alerts?since=...&severity=`
- 소스: `derived/alerts`
- 반환: 최신 알림 + reason codes + evidence 요약

3. `GET /postmortem/{market_id}`
- 소스: `derived/reports/postmortem`
- 반환: markdown 또는 렌더링된 JSON 구조

### 5.3 통합 실패 처리 표준
- 재시도 불가 오류(4xx 스키마 오류 등): 즉시 실패 + dead-letter 저장
- 재시도 가능 오류(네트워크/5xx): 지수 백오프 재시도
- 부분 실패: 세그먼트 단위 실패 허용, 전체 잡 상태는 `PARTIAL_SUCCESS` 기록

## 6) 기술 리스크 및 완화

1. 식별자 불일치(Gamma/Subgraph/WS)
- 리스크: 잘못된 join으로 잘못된 지표 산출
- 완화: `market_registry` 단일 진실원 + 충돌 규칙(`market_id` 우선) + 이력 테이블

2. 라벨 오염(VOID/UNRESOLVED 혼입)
- 리스크: Brier/LogLoss/ECE 왜곡
- 완화: `label_resolver`에서 상태 4분리 강제, 기본 집계 제외 규칙 내장

3. 시간 정렬 오류(T-24h/T-1h 선택)
- 리스크: 평가 시점 편향, 재현성 저하
- 완화: UTC 고정 + cutoff 선택 규칙 코드화 + fallback rule 저장

4. 저유동성 시장의 오탐 폭증
- 리스크: Alert 신뢰도 하락
- 완화: 3단계 게이트(band breach -> 구조 동반 -> ambiguity 낮음) + Trust Score 하한선

5. TSFM 성능 불확실/드리프트
- 리스크: 밴드 커버리지 저하
- 완화: 베이스라인 3종 상시 산출 + conformal 보정 + 커버리지 모니터링 기반 재학습 트리거

6. LLM 출력 불안정/환각
- 리스크: 문항 품질 점수 변동, 설명 신뢰도 하락
- 완화: JSON strict schema, 캐시/seed/temperature 고정, evidence-only 템플릿 정책

7. 데이터 품질 결측/지연
- 리스크: feature/score 누락
- 완화: 결측 플래그(`impute_flag`)와 품질 지표(`data_freshness_sec`) 동시 저장

8. 백필/증분 중복 적재
- 리스크: 중복 레코드로 지표 왜곡
- 완화: idempotent upsert key, 단계별 체크포인트, `run_id` 기반 재실행 정책

9. 운영 복잡도 증가(MVP-2 스트림)
- 리스크: 장애면 확대
- 완화: MVP-1 배치 안정화 후 점진 확장, 스트림은 독립 프로세스/큐로 격리

10. 비용 리스크(LLM/스토리지)
- 리스크: 운영비 증가
- 완화: LLM 캐시 우선, 시장 우선순위 샘플링, raw 보존 주기/압축 정책 적용

## 7) 단계별 구현 우선순위

### MVP-1 (배치/읽기전용)
- 필수: I-01~I-14 + I-19
- 완료 조건:
  - 일 배치 성공률 99%+
  - 스코어보드/캘리브레이션 리포트 생성
  - 재실행 재현성 검증(run metadata 기준)

### MVP-2 (준실시간 알림)
- 필수: I-15~I-18 + I-16
- 완료 조건:
  - 1~5분 지연 내 알림 갱신
  - 오탐률 감소 추세(운영 기준)
  - post-mortem 자동 생성

## 8) 아키텍처 의사결정 기록(ADR) 권장 항목
- ADR-001: 저장 포맷(JSONL + Parquet)과 파티션 전략
- ADR-002: TSFM vs Baseline 우선순위 및 fallback 정책
- ADR-003: LLM 벤더/모델 버전 고정 정책
- ADR-004: Alert Gate 임계치의 config-driven 운영 방식
- ADR-005: API 우선(FastAPI) vs CLI 우선 제공 전략
