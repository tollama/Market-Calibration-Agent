# PRD1 구현 상태 (I-01~I-20)

기준 시점: 2026-02-20  
판정 기준:
- `Implemented`: 핵심 AC를 현재 코드에서 충족
- `Partial`: 구현은 있으나 AC 일부가 비어 있음
- `Planned`: 실질 구현이 없거나 스켈레톤 수준

## 상태 매핑

| 이슈 | 상태 | 현재 코드 기준 요약 |
| --- | --- | --- |
| I-01 | Partial | `connectors/polymarket_gamma.py`에 페이지네이션/재시도/rate limit, `pipelines/ingest_gamma_raw.py`에 `RawWriter` 연계 저장은 구현됐지만 기본 오케스트레이션 연결은 아직 빈약 |
| I-02 | Implemented | `connectors/polymarket_subgraph.py`에 쿼리 템플릿, 재시도, 부분 실패 리포트, 정규화 반환 구현 |
| I-03 | Implemented | `registry/build_registry.py`의 upsert/slug 이력/충돌 처리 + `pipelines/registry_linker.py`의 snapshot enrich 연계까지 구현 |
| I-04 | Implemented | `storage/writers.py`, `storage/layout.md`로 raw/derived 분리, dt 파티션, idempotent 쓰기 구현 |
| I-05 | Partial | `agents/label_resolver.py`, `calibration/labeling.py`로 RESOLVED/VOID/UNRESOLVED 분리와 이진 라벨 변환은 구현됐지만 다중결과 운영 연계는 미완료 |
| I-06 | Partial | `pipelines/build_cutoff_snapshots.py`에 nearest-before 선택 로직은 구현됐지만 기본 stage는 여전히 placeholder 모드 비중이 큼 |
| I-07 | Implemented | `features/build_features.py`에서 필수 피처 계산 및 결정론 동작 구현(테스트 포함) |
| I-08 | Implemented | `runners/baselines.py`에 EWMA/Kalman/Rolling Quantile + q10/q50/q90 + logit 옵션 구현 |
| I-09 | Implemented | `runners/tsfm_base.py`에 공통 인터페이스/결과 타입/디바이스 설정 필드 구현 |
| I-10 | Implemented | `calibration/conformal.py`의 보정 학습/적용/coverage + `calibration/drift.py`의 재학습 트리거 판단 로직까지 구현 |
| I-11 | Partial | `agents/question_quality_agent.py`, `llm/schemas.py`로 strict JSON/불릿 제한은 있으나 PRD 계약 필드(`market_id`, `llm_model`, `prompt_version`)와 최대 2회 재시도 정책은 미완료 |
| I-12 | Partial | `llm/cache.py`(sha256), `llm/sqlite_cache.py`(영속 캐시), `llm/client.py`(cache backend)까지 구현됐지만 seed/샘플링 고정 정책은 미완료 |
| I-13 | Partial | `calibration/metrics.py`에 Brier/LogLoss/ECE/slope/intercept, `pipelines/build_scoreboard_artifacts.py`에 parquet+markdown 출력이 있으나 category×liquidity×TTE 완전 세그먼트는 미완료 |
| I-14 | Partial | `calibration/trust_score.py`에 가중합/컴포넌트 로그 row 생성 구현, config 기반 파이프라인 연계는 미완료 |
| I-15 | Partial | `agents/alert_agent.py`의 게이트/Severity 판정 + `pipelines/build_alert_feed.py`의 이벤트 row 생성은 구현됐지만 config-driven 임계치/완전한 3게이트 연계는 미완료 |
| I-16 | Partial | `connectors/polymarket_ws.py`, `pipelines/aggregate_intraday_bars.py`로 WS 수집/1m·5m OHLC 집계는 구현됐지만 동적 구독/거래량·실현변동성/운영 hardening은 미완료 |
| I-17 | Partial | `agents/explain_agent.py`의 5줄 생성은 있으나 evidence-bound 강제/면책 문구 옵션은 미완료 |
| I-18 | Partial | `reports/postmortem.py`와 `pipelines/build_postmortem_batch.py`로 고정 섹션/자동 생성은 구현됐지만 파일명 규칙(`market_id + resolved_date`)은 미완료 |
| I-19 | Partial | `pipelines/daily_job.py`에 단계 순서/체크포인트/재개/백필 메타/stage hook이 구현됐지만 기본 stage 실동작 연결과 재시도 정책 하드닝은 미완료 |
| I-20 | Implemented | `api/app.py`에 `/scoreboard`, `/alerts`, `/postmortem/{market_id}` 읽기 전용 엔드포인트 구현 |

## 다음 우선순위

1. **I-16 운영 하드닝**: WS 동적 구독/재연결 관측성(heartbeat, retry metric), 1m·5m 집계에 거래량·거래건수·실현변동성 추가, 산출물 저장 파이프라인 연결
2. **I-17 evidence 정책 하드닝**: evidence 외 주장 차단 검증, 줄당 140자 제한 강제, `"투자 조언 아님"` 옵션 토글 추가
3. **I-11/I-12 정합화 마감**: Question Quality 출력을 PRD 계약 필드로 고정(`market_id`, `llm_model`, `prompt_version`)하고 누락 시 최대 2회 재시도 + seed/샘플링 고정 정책 도입
4. **통합 글루(I-19 중심)**: `ingest_gamma_raw -> registry_linker -> cutoff(source_rows) -> feature -> scoreboard/alerts/postmortem` 기본 stage를 end-to-end로 연결하고 실패 재시작 규칙 고정
