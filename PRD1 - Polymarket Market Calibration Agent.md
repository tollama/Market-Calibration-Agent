# **PRD 1 — Polymarket Market Calibration Agent (구현 이슈 20개 \+ AC \+ Codex/Claude 프롬프트)**

* 문서 버전: v0.1  
* 상태: Draft  
* 마지막 업데이트(Asia/Seoul): 2026-02-20  
* 범위: MVP-1(배치/읽기전용) \+ MVP-2(준실시간 알림, 읽기전용)

---

## **1\) 배경 / 문제 정의**

Polymarket의 시장 가격(`outcomePrices`)은 문서상 \*\*암묵적 확률(= implied probability)\*\*로 해석된다. ([Polymarket Documentation](https://docs.polymarket.com/developers/gamma-markets-api/overview?utm_source=chatgpt.com))  
하지만 이 확률이 언제/어떤 조건에서 잘 맞고(캘리브레이션), 언제 틀어지는지(편향/레짐/유동성/문항품질/조작 가능성)를 **시장 구조 \+ 텍스트 해석 \+ 시계열 정상범위** 관점에서 관찰/측정하는 제품이 부족하다.

---

## **2\) 목표(Goals) / 비목표(Non-goals)**

### **Goals**

1. **Market-level Calibration Scoreboard**  
   * 시장/카테고리/기간/유동성 구간별 신뢰도(Trust)와 캘리브레이션 지표 제공  
2. **Real-time(또는 Near real-time) Anomaly Alerts**  
   * “정상범위(예측구간) 이탈 \+ 신뢰도 게이트 통과” 시 알림 및 5줄 근거 요약  
3. **Post-mortem Reports**  
   * 사건 종료 후 왜 맞/틀렸는지 자동 리포트 \+ 재발 방지 룰 후보 생성

### **Non-goals (MVP에서 제외)**

* 거래/주문/포지션 오픈 등 **트레이딩 기능**  
* 개인 투자 조언/수익 최적화  
* 초저지연 HFT급(틱 단위) 알파 탐색

---

## **3\) 사용자 / 주요 시나리오**

### **Personas**

* **Researcher**: 시장 캘리브레이션/편향 연구, 레짐별 분석  
* **Market Intelligence 사용자**: 특정 카테고리(정치/스포츠/크립토) 신뢰도 모니터링  
* **운영/리스크 담당**: 알림 품질(오탐/미탐) 관리, 이슈 재발 방지

### **핵심 사용자 스토리**

* “지난 90일간 **유동성 낮은 시장**에서 ECE가 얼마나 악화됐는지 보고 싶다.”  
* “지금 급변하는 시장이 **정상범위 이탈**인지, **문항 자체가 애매해서** 그런 건지 알고 싶다.”  
* “종료 후 리포트에서 ‘틀린 이유’를 **유동성/문항/뉴스 반응 지연**으로 분해해 보고 싶다.”

---

## **4\) 산출물(Outputs)**

1. **Scoreboard**  
   * per market: Brier/LogLoss/ECE, Trust Score(0\~100), Question Quality, Liquidity bucket  
2. **Alert feed**  
   * 알림 이벤트(Severity, 이유 요약, 근거 피처, 링크/식별자)  
3. **Post-mortem markdown**  
   * 사건 요약 → 확률 궤적 → OI/활동 동반 여부 → 문항 리스크 → 재발방지 룰

---

## **5\) 데이터 소스 / 수집 전략**

### **5.1 Gamma API (메타/스냅샷)**

* 시장의 `outcomes`와 `outcomePrices`는 1:1 매핑되고, 가격이 implied probability로 문서화되어 있음. ([Polymarket Documentation](https://docs.polymarket.com/developers/gamma-markets-api/overview?utm_source=chatgpt.com))  
* “Events endpoint 기반 전체 활성 시장 수집” 같은 수집 전략도 문서에 존재. ([Polymarket Documentation](https://docs.polymarket.com/developers/market-makers/data-feeds?utm_source=chatgpt.com))

### **5.2 Subgraph (온체인 지표)**

* Polymarket은 GraphQL로 접근 가능한 서브그래프를 제공하며, 온체인 인덱싱/집계 정보를 조회할 수 있음. ([Polymarket Documentation](https://docs.polymarket.com/developers/subgraph/overview?utm_source=chatgpt.com))

### **5.3 WebSocket (MVP-2)**

* CLOB WebSocket은 market/user 등 채널로 실시간 데이터 스트리밍을 제공하며, 시장 데이터는 public market 채널로 구독 가능. ([Polymarket Documentation](https://docs.polymarket.com/developers/CLOB/websocket/wss-overview?utm_source=chatgpt.com))

원칙: **MVP-1은 Gamma+Subgraph로 성립**, MVP-2에서 WebSocket로 준실시간 확장.

---

## **6\) 시스템 아키텍처(요약)**

\[Gamma API\] \----\\  
                 \\--\> \[Raw Store\] \--\> \[Normalizer/Registry\] \--\> \[Snapshot Store\] \--\> \[Feature Builder\]  
\[Subgraph\] \-----/                                                           \\--\> \[Calibration Engine\] \--\> \[Scoreboard\]  
                                                                             \\--\> \[TSFM Runner\] \--\> \[Bands\]  
                                                                                  \\--\> \[Alert Engine\] \--\> \[Alerts\]  
\[WebSocket\] (MVP-2) \--\> \[Stream Aggregator\] \---------------------------------/  
                                    \\  
                                     \\--\> \[LLM Reasoner: Question Quality \+ Explain\] \--\> \[Reports\]

---

## **7\) 데이터 모델(스키마) — 최소 표준**

### **7.1 `market_registry` (ID 매핑 단일 진실원)**

{  
  "market\_id": "string",  
  "event\_id": "string",  
  "slug": "string",  
  "category\_tags": \["string"\],  
  "outcomes": \["Yes", "No"\],  
  "enableOrderBook": true,  
  "start\_ts": "2026-02-01T00:00:00Z",  
  "end\_ts": "2026-02-20T00:00:00Z",  
  "status": "ACTIVE|RESOLVED|VOID|UNRESOLVED"  
}

### **7.2 `market_snapshot` (배치/스트림 공통)**

{  
  "ts": "2026-02-20T12:00:00Z",  
  "market\_id": "string",  
  "event\_id": "string",  
  "p\_yes": 0.62,  
  "p\_no": 0.38,  
  "volume\_24h": 12345.67,  
  "open\_interest": 89012.34,  
  "num\_traders\_proxy": 123,  
  "liquidity\_bucket": "LOW|MID|HIGH",  
  "tte\_seconds": 86400,  
  "data\_source": \["gamma", "subgraph"\]  
}

### **7.3 `question_quality` (LLM 출력: 구조화)**

{  
  "market\_id": "string",  
  "llm\_model": "string",  
  "prompt\_version": "vX.Y",  
  "ambiguity\_score": 0.18,  
  "resolution\_risk\_score": 0.32,  
  "trigger\_events": \[  
    {"type": "ELECTION|CPI|COURT|EARNINGS|OTHER", "when": "2026-03-01", "keywords": \["..."\]}  
  \],  
  "rationale\_bullets": \["...", "..."\]  
}

### **7.4 `forecast_band`**

{  
  "ts": "2026-02-20T12:00:00Z",  
  "market\_id": "string",  
  "horizon\_steps": 12,  
  "step\_seconds": 300,  
  "q10": 0.55,  
  "q50": 0.61,  
  "q90": 0.68,  
  "method": "TSFM|EWMA|KALMAN|ROLLING\_QUANTILE",  
  "model\_id": "chronos-2|timesfm-2.5|...",  
  "band\_calibration": "raw|conformal"  
}

### **7.5 `alert_event`**

{  
  "ts": "2026-02-20T12:05:00Z",  
  "market\_id": "string",  
  "severity": "HIGH|MED|FYI",  
  "reason\_codes": \["BAND\_BREACH", "LOW\_OI\_CONFIRMATION", "LOW\_AMBIGUITY"\],  
  "evidence": {  
    "p\_yes": 0.72,  
    "q10": 0.55,  
    "q90": 0.68,  
    "oi\_change\_1h": \-0.01,  
    "volume\_velocity": 3.2,  
    "ambiguity\_score": 0.12  
  },  
  "llm\_explain\_5lines": \["...", "...", "...", "...", "..."\]  
}

---

## **8\) 성공 지표(Success Metrics)**

### **MVP-1**

* Scoreboard 생성 성공률(일일 배치): 99%+  
* 이벤트 라벨 정제(RESOLVED vs VOID/UNRESOLVED) 정확도: 수작업 샘플 기준 95%+  
* 캘리브레이션 리포트 재현성: 동일 데이터 재실행 시 결과 동일(버전 고정)

### **MVP-2**

* 알림 오탐률(운영 정의): “의미 없는 알림” 비중 30% 이하로 지속 감소(룰/게이트 개선)  
* 알림 지연: 집계 기준 1\~5분 내 업데이트

---

## **9\) 구현 이슈 리스트(20개) \+ AC \+ Codex/Claude 프롬프트**

표기: **P0(필수)** / P1(중요) / P2(개선)

---

### **I-01 (P0) Gamma API 커넥터 \+ 페이지네이션 \+ 재시도**

**설명**: markets/events 엔드포인트를 안정적으로 순회 수집하고 raw로 저장. ([Polymarket Documentation](https://docs.polymarket.com/api-reference/markets/list-markets?utm_source=chatgpt.com))  
**AC**

* Given 네트워크 오류가 발생해도 When 재시도 정책 수행 Then 중복 없이 수집 완료  
* 모든 응답을 `raw/gamma/dt=YYYY-MM-DD/`에 JSONL로 저장  
* 요청 속도 제한(초당 요청 수) 설정 가능

\[Codex/Claude Prompt\]  
Python으로 connectors/polymarket\_gamma.py를 작성해줘.  
\- 기능: markets, events 수집(페이지네이션 포함), rate limit, exponential backoff, 타임아웃, 로깅  
\- 출력: JSONL raw 저장(writer 인터페이스 주입)  
\- 요구: 타입힌트, 예외 계층, 단위테스트(pytest) 포함  
\- 금지: 트레이딩/인증키 필요 기능은 넣지 말 것

---

### **I-02 (P0) Subgraph GraphQL 커넥터 \+ 쿼리 템플릿**

**설명**: OI/활동/체결량 등 집계 지표를 GraphQL로 조회. ([Polymarket Documentation](https://docs.polymarket.com/developers/subgraph/overview?utm_source=chatgpt.com))  
**AC**

* GraphQL 쿼리 템플릿(문자열/파일)로 관리  
* 요청 실패 시 재시도 및 부분 실패 리포팅  
* market\_id/event\_id 기준으로 결과 정규화 반환

\[Codex/Claude Prompt\]  
connectors/polymarket\_subgraph.py를 작성해줘.  
\- GraphQLClient(엔드포인트, headers, retry) \+ QueryTemplates  
\- 함수: fetch\_open\_interest(), fetch\_activity(), fetch\_volume()  
\- 반환: pandas DataFrame 또는 dict(list) (선택), 스키마 고정  
\- 테스트: mock 서버 또는 responses로 단위테스트

---

### **I-03 (P0) Market Registry(식별자 매핑) 생성/유지**

**설명**: Gamma ↔ Subgraph ↔ (추후 CLOB) 식별자 혼선을 막기 위한 단일 매핑 테이블.  
**AC**

* market\_id/event\_id/slug/outcomes/enableOrderBook/status 필수  
* slug 변경/중복 발생 시 이력 테이블에 기록  
* 레지스트리 기반으로 snapshot 생성 가능

\[Codex/Claude Prompt\]  
schemas/market\_registry.py(pydantic)와 registry/build\_registry.py를 작성해줘.  
\- 입력: gamma markets/events raw  
\- 출력: market\_registry 테이블(upsert) \+ 변경 이력 테이블  
\- 중복/충돌 규칙을 명시(예: market\_id 우선)

---

### **I-04 (P0) Raw Store / Derived Store 분리 \+ 파티셔닝 규칙**

**설명**: 재현성/백필을 위해 raw와 derived를 분리 저장.  
**AC**

* raw는 원문 보존(JSONL)  
* derived는 정규화 스냅샷(parquet 권장)  
* dt 파티션 규칙 문서화 \+ 자동 생성

\[Codex/Claude Prompt\]  
storage/layout.md와 storage/writers.py를 만들어줘.  
\- RawWriter(JSONL), ParquetWriter(파티션 dt=)  
\- 로컬 파일 시스템 기준 구현 \+ S3 호환 추상화 인터페이스 포함

---

### **I-05 (P0) 라벨/상태 정제: RESOLVED/VOID/UNRESOLVED 분리**

**설명**: 캘리브레이션 지표 오염 방지(VOID/UNRESOLVED 제외).  
**AC**

* 최소 상태 4종: RESOLVED\_TRUE, RESOLVED\_FALSE, VOID, UNRESOLVED  
* multi-outcome은 별도 타입으로 분류  
* Scoreboard 계산 시 기본 제외 규칙 적용

\[Codex/Claude Prompt\]  
agents/label\_resolver.py를 작성해줘.  
\- 입력: gamma market/event 메타(종료/결과 관련 필드)  
\- 출력: label 상태 enum \+ outcome id  
\- 예외: void/invalid/unresolved 케이스를 안전하게 처리

---

### **I-06 (P0) 표준 컷오프 스냅샷 생성(T-24h, T-1h, Daily)**

**설명**: 이벤트별 과대표집을 줄이기 위한 표준 평가 포인트.  
**AC**

* 이벤트 종료시각 기준 T-24h/T-1h 가장 가까운 스냅샷 선택 규칙  
* missing 시 fallback(예: nearest earlier)  
* 이벤트당 1\~3개 표준 레코드 생성

\[Codex/Claude Prompt\]  
pipelines/build\_cutoff\_snapshots.py를 작성해줘.  
\- 입력: market\_snapshot 시계열  
\- 출력: cutoff\_snapshot 테이블(T-24h/T-1h/Daily)  
\- 타임존은 UTC 저장, 리포트 표시는 Asia/Seoul 옵션

---

### **I-07 (P0) Feature Builder(시계열/유동성/TTE/변동성)**

**설명**: 알림/분석에 필요한 피처 프레임 생성.  
**AC**

* 최소 피처: returns, vol, volume\_velocity, oi\_change, tte, liquidity\_bucket  
* 누락/NaN 처리 규칙 문서화  
* 동일 입력 → 동일 출력(결정론)

\[Codex/Claude Prompt\]  
features/build\_features.py를 작성해줘.  
\- 입력: cutoff\_snapshot \+ (옵션) 고빈도 집계  
\- 출력: feature\_frame parquet  
\- 피처 계산은 벡터화(pandas) \+ 테스트 케이스 포함

---

### **I-08 (P0) Baseline 밴드(EWMA/Kalman/Rolling Quantile)**

**설명**: TSFM 대비 성능 비교 및 fallback 운영.  
**AC**

* 3개 방법 모두 q10/q50/q90 산출  
* 확률 경계(0\~1) 처리(예: logit 공간) 옵션 제공  
* 단일 함수 인터페이스로 교체 가능

\[Codex/Claude Prompt\]  
runners/baselines.py를 작성해줘.  
\- EWMA band, Local-level Kalman band, Rolling quantile band 구현  
\- 입력/출력은 forecast\_band 스키마와 동일하게

---

### **I-09 (P0) TSFM Runner 공통 인터페이스 정의**

**설명**: Chronos/TimesFM 등 모델 패밀리별 runner 교체 가능하게.  
**AC**

* forecast\_quantiles(series, horizon, step, quantiles, covariates)-\>ForecastResult  
* 모델/버전/컨텍스트 길이 메타 기록  
* CPU/GPU 선택 가능

\[Codex/Claude Prompt\]  
runners/tsfm\_base.py에 추상 클래스와 공통 타입을 정의해줘.  
\- Pydantic ForecastResult \+ RunnerConfig  
\- 모델별 runner는 이 인터페이스를 구현

---

### **I-10 (P0) 예측구간 보정(Conformal Calibration) 모듈**

**설명**: “밴드의 커버리지”를 운영적으로 맞추기 위한 보정. ([arXiv](https://arxiv.org/html/2507.08858v1?utm_source=chatgpt.com))  
**AC**

* 캘리브레이션 셋에서 잔차 기반 보정량 학습  
* 목표 커버리지(예: 80/90%) 설정 가능  
* drift 발생 시 재학습 트리거 조건 정의

\[Codex/Claude Prompt\]  
calibration/conformal.py를 작성해줘.  
\- 입력: 과거 예측밴드 \+ 실측  
\- 출력: 보정된 밴드(quantile shift/scale)  
\- coverage 리포트 함수 포함

---

### **I-11 (P0) LLM Question Quality Scorer (JSON 강제)**

**설명**: 문항 다의성/리졸브 리스크를 구조화 점수화.  
**AC**

* JSON 스키마 강제(필드 누락 시 재시도)  
* prompt\_version, llm\_model 저장  
* rationale은 최대 5 bullet로 제한

\[Codex/Claude Prompt\]  
agents/question\_quality\_agent.py를 작성해줘.  
\- 입력: market 질문/룰 텍스트  
\- 출력: question\_quality JSON(ambiguity\_score, resolution\_risk\_score, trigger\_events, rationale\_bullets)  
\- 요구: JSON schema validator \+ 재시도(최대 2회) \+ 로깅

---

### **I-12 (P0) LLM 캐시 \+ 재현성(버전/온도/샘플링 고정)**

**설명**: 점수 흔들림(드리프트) 최소화 및 비용 절감.  
**AC**

* 동일 입력(정규화 텍스트, prompt\_version, model) → 캐시 히트  
* 온도/seed 정책 고정 가능  
* 캐시 무결성(해시 키) 테스트

\[Codex/Claude Prompt\]  
llm/cache.py와 llm/client.py를 작성해줘.  
\- 키 설계: sha256(normalized\_text \+ model \+ prompt\_version \+ params)  
\- 로컬 SQLite 캐시 구현 \+ 인터페이스 추상화

---

### **I-13 (P0) Calibration Engine (Brier/LogLoss/ECE \+ 세그먼트)**

**설명**: 시장/카테고리/유동성/TTE 별 캘리브레이션 지표 생성.  
**AC**

* 최소 지표: Brier, LogLoss, ECE(버킷 기반), slope/intercept  
* 세그먼트 리포트: category x liquidity x TTE  
* 결과를 parquet \+ markdown 요약으로 출력

\[Codex/Claude Prompt\]  
agents/calibration\_agent.py를 작성해줘.  
\- 입력: resolved cutoff\_snapshot \+ question\_quality \+ features  
\- 출력: metrics tables \+ reliability data(그래프용)  
\- 주의: 이벤트 가중치(1/event) 옵션 포함

---

### **I-14 (P0) Trust Score(0\~100) 산식 v1 \+ 구성요소 로그**

**설명**: “이 시장 확률을 얼마나 믿을지”를 단일 지표로 제공.  
**AC**

* Liquidity/Depth, Stability, Question Quality, Manipulation Suspect의 가중합  
* 각 구성요소 값과 최종 점수를 함께 저장(디버깅)  
* 가중치 설정 가능(config)

\[Codex/Claude Prompt\]  
scoring/trust\_score.py를 작성해줘.  
\- 입력: features \+ question\_quality \+ (옵션) stream aggregates  
\- 출력: trust\_score \+ components dict  
\- config로 가중치/클리핑/스케일링 지원

---

### **I-15 (P1) Alert Engine: 밴드 이탈 \+ 3단계 게이트 \+ Severity**

**설명**: “정상범위 이탈”을 알림으로 승격하는 규칙 엔진.  
**AC**

* Gate1: band breach, Gate2: 구조 동반(OI/volume), Gate3: 해석 리스크(ambiguity 낮음)  
* HIGH/MED/FYI 분류  
* 알림 이벤트는 `alert_event` 스키마로 저장

\[Codex/Claude Prompt\]  
agents/alert\_agent.py를 작성해줘.  
\- 입력: latest snapshot \+ forecast\_band \+ trust\_score \+ question\_quality  
\- 출력: alert\_event(Severity, reason\_codes, evidence)  
\- 룰은 config-driven(임계치 yaml)

---

### **I-16 (P1) WebSocket Market Channel Ingestor \+ 집계(1\~5분)**

**설명**: 준실시간 가격/체결 기반 알림을 위해 스트림 수집. ([Polymarket Documentation](https://docs.polymarket.com/developers/CLOB/websocket/wss-overview?utm_source=chatgpt.com))  
**AC**

* 재연결/하트비트/백오프  
* 1\~5분 OHLC/거래량/변동성 집계 테이블 생성  
* market\_id(asset\_id) 구독 관리(동적)

\[Codex/Claude Prompt\]  
connectors/polymarket\_ws\_market.py와 streaming/aggregator.py를 작성해줘.  
\- WS 구독/메시지 파싱/재연결  
\- 집계: 1m/5m 캔들 \+ trade count \+ realized vol  
\- 출력: stream\_agg parquet 또는 sqlite

---

### **I-17 (P1) “설명 5줄” LLM 생성기(알림/리포트 공용)**

**설명**: 사용자가 이해할 수 있는 근거 요약(근거 피처 기반).  
**AC**

* 입력 evidence를 근거로만 설명(환각 방지)  
* 5줄 제한, 각 줄 140자 제한  
* “투자 조언 아님” 문구 옵션

\[Codex/Claude Prompt\]  
agents/explain\_agent.py를 작성해줘.  
\- 입력: alert\_event.evidence \+ market 요약 텍스트  
\- 출력: 5줄 bullet  
\- 정책: evidence 밖의 사실 주장 금지(템플릿 기반 \+ LLM은 문장화만)

---

### **I-18 (P1) Post-mortem Markdown 리포트 자동 생성**

**설명**: 종료 후 “왜 맞/틀렸는지” 구조화 리포트.  
**AC**

* 섹션 고정(요약/궤적/동반지표/문항리스크/재발방지)  
* 동일 입력 → 동일 리포트(버전 고정)  
* 리포트 파일명 규칙: market\_id \+ resolved\_date

\[Codex/Claude Prompt\]  
reports/postmortem.py를 작성해줘.  
\- 입력: market\_registry \+ snapshots \+ calibration metrics \+ alert history \+ question\_quality  
\- 출력: markdown string \+ 파일 저장

---

### **I-19 (P0) 배치 오케스트레이션(백필/증분) \+ 실패 복구**

**설명**: “전체 활성 수집 → 스냅샷 → 피처 → 지표” 파이프라인 자동화.  
**AC**

* idempotent(재실행 시 중복/오염 없음)  
* 단계별 체크포인트(어디서 실패했는지)  
* 백필 기간 지정 가능(예: last 90d)

\[Codex/Claude Prompt\]  
pipelines/daily\_job.py를 작성해줘.  
\- 단계: discover \-\> ingest \-\> normalize \-\> snapshots \-\> features \-\> metrics \-\> publish  
\- 실패 시 재시도/스킵 정책 포함

---

### **I-20 (P2) 대시보드/API: Scoreboard/Alerts/Reports 조회**

**설명**: UI(내부용) 혹은 API로 결과 제공.  
**AC**

* 최소 3개 엔드포인트(또는 CLI):  
  * /scoreboard?window=90d  
  * /alerts?since=...  
  * /postmortem/{market\_id}  
* 페이징/필터링(tag, liquidity\_bucket)

\[Codex/Claude Prompt\]  
api/app.py(FastAPI) 또는 cli/main.py 중 하나로 구현해줘.  
\- 읽기전용 조회 기능만  
\- 응답 스키마는 pydantic으로 고정

---

## **10\) 릴리즈 플랜(권장)**

### **MVP-1 (배치/읽기전용)**

* I-01\~I-14 \+ I-19 우선 완료  
* Scoreboard \+ Question Quality \+ 기본 캘리브레이션 리포트

### **MVP-2 (준실시간/알림)**

* I-15\~I-18 \+ I-16 추가  
* 알림 피드 \+ 설명 5줄 \+ 사건 종료 리포트 자동화

---

## **11\) 리스크 / 완화**

* **라벨 오염(VOID/UNRESOLVED)** → I-05에서 분리 강제  
* **오탐 폭발** → Trust Score \+ 3단계 게이트(I-15)로 단계적 강화  
* **LLM 점수 드리프트** → 캐시/버전/구조화(I-11\~I-12)  
* **TSFM 성능 불확실** → Baseline 밴드(I-08) \+ Conformal(I-10)

---

---

