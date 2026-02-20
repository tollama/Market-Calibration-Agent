# PRD1 기반 구현 계획서 (요구사항)

## 목표/범위/비범위

### 목표
1. Polymarket 시장별 신뢰도와 캘리브레이션 상태를 정량화한 Scoreboard를 제공한다.
2. 정상범위(예측구간) 이탈을 준실시간으로 감지하고, 근거 기반 알림과 5줄 설명을 제공한다.
3. 이벤트 종료 후 맞/틀림 원인을 구조화한 Post-mortem 리포트를 자동 생성한다.

### 범위
1. MVP-1(배치/읽기전용): Gamma/Subgraph 수집, 식별자 정합, 스냅샷/피처 생성, 캘리브레이션 지표, Trust Score, 일배치 오케스트레이션.
2. MVP-2(준실시간/알림): WebSocket 수집, 1~5분 집계, Alert Engine, 설명 생성기, Post-mortem 자동화.
3. 조회 기능: API 또는 CLI를 통해 Scoreboard/Alerts/Reports를 읽기전용으로 제공한다(P2).

### 비범위
1. 주문/체결/포지션 오픈 등 트레이딩 기능.
2. 개인 투자자 대상 투자 자문 또는 수익 최적화 기능.
3. 틱 단위 초저지연(HFT급) 알파 탐색.

## 기능요구사항(P0/P1/P2)

### P0 (필수)
1. [I-01] Gamma API 커넥터는 markets/events를 페이지네이션으로 수집하고 재시도, 타임아웃, rate limit를 지원해야 한다.
2. [I-02] Subgraph GraphQL 커넥터는 쿼리 템플릿 기반으로 OI/활동/거래량을 수집하고 부분 실패를 보고해야 한다.
3. [I-03] Market Registry는 market_id/event_id/slug/outcomes/status를 단일 진실원으로 관리하고 변경 이력을 보존해야 한다.
4. [I-04] 저장소 계층은 raw(JSONL)와 derived(parquet)를 분리하고 dt 파티션 규칙을 적용해야 한다.
5. [I-05] 라벨 정제 로직은 RESOLVED_TRUE/RESOLVED_FALSE/VOID/UNRESOLVED를 구분하고 기본 지표 계산에서 VOID/UNRESOLVED를 제외해야 한다.
6. [I-06] 컷오프 스냅샷 파이프라인은 T-24h, T-1h, Daily 기준 레코드를 이벤트당 1~3개 생성해야 한다.
7. [I-07] Feature Builder는 returns/vol/volume_velocity/oi_change/tte/liquidity_bucket를 결정론적으로 계산해야 한다.
8. [I-08] Baseline 밴드 모듈은 EWMA/Kalman/Rolling Quantile 방식으로 q10/q50/q90를 생성해야 한다.
9. [I-09] TSFM Runner 인터페이스는 모델 교체 가능한 공통 추상 인터페이스와 표준 ForecastResult 스키마를 제공해야 한다.
10. [I-10] Conformal Calibration 모듈은 목표 커버리지 기반으로 밴드를 보정하고 커버리지 리포트를 생성해야 한다.
11. [I-11] Question Quality Agent는 JSON 스키마 강제 출력과 재시도 정책을 제공해야 한다.
12. [I-12] LLM 캐시는 normalized_text/model/prompt_version/params 기반 해시 키로 동일 입력 재사용과 재현성을 보장해야 한다.
13. [I-13] Calibration Engine은 Brier/LogLoss/ECE/slope/intercept 및 category×liquidity×TTE 세그먼트 리포트를 생성해야 한다.
14. [I-14] Trust Score 모듈은 Liquidity/Stability/Question Quality/Manipulation Suspect 구성요소를 로그와 함께 0~100 점수로 산출해야 한다.
15. [I-19] 배치 오케스트레이션은 discover→ingest→normalize→snapshots→features→metrics→publish 단계의 idempotent 실행과 실패 복구를 지원해야 한다.

### P1 (중요)
1. [I-15] Alert Engine은 band breach + 구조 동반(OI/volume) + 해석 리스크(ambiguity) 3단계 게이트와 HIGH/MED/FYI 분류를 지원해야 한다.
2. [I-16] WebSocket Ingestor와 Aggregator는 재연결/하트비트/백오프 및 1m/5m 집계(OHLC, 거래량, realized vol)를 생성해야 한다.
3. [I-17] Explain Agent는 alert evidence 기반 5줄 요약을 생성하고 evidence 밖 사실 주장을 금지해야 한다.
4. [I-18] Post-mortem 생성기는 요약/궤적/동반지표/문항리스크/재발방지 섹션 고정 템플릿으로 Markdown 리포트를 생성해야 한다.

### P2 (개선)
1. [I-20] 읽기전용 API/CLI는 scoreboard, alerts, postmortem 조회와 페이징/필터링(tag, liquidity_bucket)을 제공해야 한다.

## 비기능요구사항

1. 신뢰성: 일일 배치 기준 Scoreboard 생성 성공률 99% 이상을 유지해야 한다.
2. 정확성: RESOLVED/VOID/UNRESOLVED 라벨 정제 정확도는 수작업 샘플 기준 95% 이상이어야 한다.
3. 재현성: 동일 입력 데이터와 동일 버전/설정에서 지표와 리포트 결과가 동일해야 한다.
4. 성능: MVP-2 알림 파이프라인은 스트림 집계 단위 기준 1~5분 내 최신 상태를 반영해야 한다.
5. 내결함성: 외부 API/WS 오류 시 재시도 및 백오프 후 자동 복구하며, 복구 불가 시 부분 실패를 기록해야 한다.
6. 일관성: 모든 시계열 저장은 UTC를 기준으로 하고, 리포트 표시만 Asia/Seoul 옵션을 허용해야 한다.
7. 운영성: 모든 파이프라인 단계는 체크포인트, 구조화 로그, 실행 메타데이터(버전/모델/파라미터)를 남겨야 한다.
8. 확장성: TSFM/베이스라인/저장소 구현체는 인터페이스 기반으로 교체 가능해야 한다.
9. 데이터 거버넌스: raw 원문은 변경 없이 보존하고 derived는 스키마 버전과 생성 이력을 추적해야 한다.
10. 안전성: 시스템은 읽기전용 분석/모니터링 용도로 동작하며 트레이딩 실행 기능을 포함하지 않아야 한다.

## 수용기준(테스트 가능한 문장)

1. 네트워크 오류를 3회 유도해도 Gamma 수집 작업은 중복 없는 JSONL raw 파일을 `raw/gamma/dt=YYYY-MM-DD/` 경로에 생성해야 한다.
2. 요청 제한값(RPS)을 1로 설정했을 때, Gamma 커넥터의 평균 호출 간격은 설정값을 위반하지 않아야 한다.
3. Subgraph 쿼리 1개를 실패시키면 작업 전체는 계속 진행되고, 실패 쿼리와 사유가 실행 리포트에 남아야 한다.
4. 동일 market_id에 slug 변경 이벤트를 입력하면 Registry 본테이블은 최신 slug 1건만 유지하고 이력 테이블에 변경 전/후 값이 기록되어야 한다.
5. raw 저장 파일은 원문 필드 손실 없이 JSONL로 기록되고, derived 저장 파일은 parquet + dt 파티션으로 생성되어야 한다.
6. VOID/UNRESOLVED 상태 시장이 포함된 입력으로 Scoreboard를 생성하면 해당 시장은 기본 계산 결과에서 제외되어야 한다.
7. 종료시각 기준 T-24h, T-1h 스냅샷이 비어 있으면 nearest earlier 규칙으로 대체 레코드가 생성되어야 한다.
8. 동일 입력 스냅샷으로 Feature Builder를 2회 실행하면 행 수, 컬럼 값, 정렬 순서가 완전히 동일해야 한다.
9. Baseline 3개 방식(EWMA/Kalman/Rolling Quantile)은 동일 인터페이스 호출로 q10/q50/q90를 모두 반환해야 한다.
10. 밴드 출력의 모든 분위수 값은 0 이상 1 이하여야 하며 q10 ≤ q50 ≤ q90 조건을 만족해야 한다.
11. TSFM Runner 구현체는 `forecast_quantiles(series, horizon, step, quantiles, covariates)` 시그니처를 준수해야 한다.
12. Conformal 보정 적용 후 검증 구간의 실측 커버리지는 설정 목표(예: 0.8 또는 0.9)에 수렴해야 한다.
13. Question Quality Agent 응답에서 필수 JSON 필드가 누락되면 최대 2회 재시도 후 실패 상태를 명시적으로 반환해야 한다.
14. 동일 입력 텍스트/모델/프롬프트 버전/파라미터로 LLM 호출 시 두 번째 실행은 캐시 히트로 외부 호출 없이 동일 결과를 반환해야 한다.
15. Calibration Engine 결과에는 Brier, LogLoss, ECE, slope, intercept 컬럼이 모두 포함되어야 한다.
16. 세그먼트 리포트는 category × liquidity_bucket × TTE 축으로 집계 테이블을 생성해야 한다.
17. Trust Score 출력에는 최종 점수(0~100)와 구성요소별 원점수 및 가중치가 함께 저장되어야 한다.
18. 일배치 파이프라인을 동일 날짜 범위로 재실행해도 중복 레코드가 증가하지 않아야 한다.
19. 파이프라인 중간 단계 실패 후 재실행하면 마지막 성공 체크포인트 이후 단계부터 복구 실행되어야 한다.
20. Alert Engine은 Gate1~Gate3 중 하나라도 미충족이면 HIGH/MED 알림을 생성하지 않아야 한다.
21. Alert 생성 시 `alert_event` 스키마의 필수 필드(ts, market_id, severity, reason_codes, evidence)가 누락되면 저장이 거부되어야 한다.
22. WebSocket 연결이 끊기면 백오프 후 자동 재연결되고, 재연결 시 구독 대상 market_id 목록이 복원되어야 한다.
23. 1m/5m 집계 결과에는 OHLC, trade_count, realized_vol 컬럼이 모두 존재해야 한다.
24. Explain Agent 출력은 정확히 5줄이어야 하며 각 줄 길이는 140자를 초과하지 않아야 한다.
25. Explain Agent 결과 텍스트는 입력 evidence에 없는 수치/사실을 포함하지 않아야 한다.
26. Post-mortem 파일명은 `market_id + resolved_date` 규칙을 따르고 Markdown 섹션 순서를 고정해야 한다.
27. 동일 입력 데이터와 동일 템플릿 버전으로 Post-mortem을 2회 생성하면 파일 내용 해시가 동일해야 한다.
28. API/CLI 조회 기능(P2)은 `/scoreboard`, `/alerts`, `/postmortem/{market_id}` 또는 동등 명령을 제공해야 한다.
29. `/scoreboard` 조회는 `window=90d` 필터가 적용된 결과만 반환해야 한다.
30. `/alerts` 조회는 `since` 파라미터 기준 이후 데이터만 반환하고 페이지네이션이 동작해야 한다.
31. 시스템 코드베이스에는 트레이딩 주문 전송 함수 또는 인증키 기반 주문 API 호출이 포함되지 않아야 한다.
