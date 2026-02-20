# PRD1 구현 상태 (I-01~I-20)

기준 시점: 2026-02-20  
판정 기준:
- `Implemented`: 핵심 AC를 현재 코드에서 충족
- `Partial`: 구현은 있으나 AC 일부가 비어 있음
- `Planned`: 실질 구현이 없거나 스켈레톤 수준

## 상태 매핑

| 이슈 | 상태 | 현재 코드 기준 요약 |
| --- | --- | --- |
| I-01 | Partial | `connectors/polymarket_gamma.py`에 페이지네이션/재시도/rate limit은 있으나 raw JSONL 저장 연계는 미구현 |
| I-02 | Implemented | `connectors/polymarket_subgraph.py`에 쿼리 템플릿, 재시도, 부분 실패 리포트, 정규화 반환 구현 |
| I-03 | Partial | `registry/build_registry.py`에서 upsert/slug 이력/충돌 처리 구현, 레지스트리 기반 snapshot 생성 연계는 미완료 |
| I-04 | Implemented | `storage/writers.py`, `storage/layout.md`로 raw/derived 분리, dt 파티션, idempotent 쓰기 구현 |
| I-05 | Partial | `agents/label_resolver.py`에서 4상태 분류는 구현, multi-outcome 별도 타입/scoreboard 제외 규칙 연결은 미완료 |
| I-06 | Partial | `pipelines/build_cutoff_snapshots.py`에 nearest-before 선택 로직은 있으나 기본 stage는 placeholder 동작 중심 |
| I-07 | Implemented | `features/build_features.py`에서 필수 피처 계산 및 결정론 동작 구현(테스트 포함) |
| I-08 | Implemented | `runners/baselines.py`에 EWMA/Kalman/Rolling Quantile + q10/q50/q90 + logit 옵션 구현 |
| I-09 | Implemented | `runners/tsfm_base.py`에 공통 인터페이스/결과 타입/디바이스 설정 필드 구현 |
| I-10 | Partial | `calibration/conformal.py`에 보정 학습/적용/coverage 리포트 구현, drift 재학습 트리거 규칙은 미정의 |
| I-11 | Partial | `agents/question_quality_agent.py`, `llm/schemas.py`로 JSON 강제는 있으나 PRD 필드 스키마(ambiguity 등)와 재시도 정책이 불일치 |
| I-12 | Partial | `llm/cache.py`의 sha256 캐시는 구현, SQLite 기반 영속 캐시/seed 정책 고정은 미완료 |
| I-13 | Partial | `calibration/metrics.py`에서 Brier/LogLoss/ECE/세그먼트 계산 구현, slope/intercept/agent 출력(parquet+md)은 미구현 |
| I-14 | Partial | `calibration/trust_score.py`에 가중합/컴포넌트 로그 row 생성 구현, config 기반 파이프라인 연계는 미완료 |
| I-15 | Planned | Alert rule engine(`agents/alert_agent.py`) 실구현 없음 (조회 API/스키마만 존재) |
| I-16 | Planned | WebSocket ingestor/1m~5m 집계 모듈 실구현 없음 |
| I-17 | Partial | `agents/explain_agent.py`의 5줄 생성은 있으나 evidence-bound 강제/면책 문구 옵션은 미완료 |
| I-18 | Planned | post-mortem 생성기(`reports/postmortem.py`) 실구현 없음 |
| I-19 | Partial | `pipelines/daily_job.py` 오케스트레이션 뼈대는 있으나 체크포인트 영속/실패 복구/백필 제어는 미완료 |
| I-20 | Implemented | `api/app.py`에 `/scoreboard`, `/alerts`, `/postmortem/{market_id}` 읽기 전용 엔드포인트 구현 |

## 즉시 실행 계획 (기본 가정 고정)

기본 가정:
- 데이터 루트는 `data/`를 사용하고 저장 시각은 UTC로 통일
- MVP-1 우선순위는 PRD 권고대로 P0(I-01~I-14, I-19) 완료
- 기존 read-only API 스키마는 하위 호환 유지

실행 순서:
1. I-01 마감: Gamma 수집 결과를 `RawWriter` 주입 방식으로 `raw/gamma/dt=...`에 직접 저장하도록 연결
2. I-06 마감: 이벤트 종료시각 기준 `T-24h/T-1h/Daily` 선택 로직과 fallback(nearest earlier) 완성
3. I-11/I-12 정합화: PRD 스키마로 Question Quality 출력 변경, 누락 필드 시 최대 2회 재시도, SQLite 캐시 도입
4. I-13/I-14 엔진화: metric 계산 + trust score를 배치 stage로 연결하고 `parquet + markdown` 산출물 저장
5. I-19 강화: stage 체크포인트 파일, 재실행 idempotency, `last N days` 백필 옵션, 실패 단계 재시작 정책 추가
6. P1 착수 준비: I-15/I-17을 기존 API 입력 스키마에 맞춰 최소 기능부터 연결
