# PRD1 구현 상태 (I-01~I-20)

기준 시점: 2026-02-20 (현재 워크트리 코드 기준)  
판정 기준:
- `Implemented`: PRD AC 핵심 요건 충족
- `Partial`: 구현은 있으나 AC 일부 미충족 또는 운영 연결 미완료
- `Planned`: 실질 구현 없음/스켈레톤

## 상태 매핑

| 이슈 | 상태 | 현재 코드 기준 요약 |
| --- | --- | --- |
| I-01 | Implemented | `connectors/polymarket_gamma.py`에 페이지네이션/재시도/RPS 제한 + `fetch_markets_raw`/`fetch_events_raw`가 구현되어 있고, `pipelines/ingest_gamma_raw.py`가 PRD canonical 경로(`raw/gamma/dt=.../*.jsonl`)와 기존 dataset-scoped 경로(`raw/gamma/{dataset}/dt=.../data.jsonl`)를 dual-write로 함께 지원해 마이그레이션 안전성을 확보 |
| I-02 | Implemented | `connectors/polymarket_subgraph.py`에 쿼리 템플릿, retry/backoff, 부분 실패 누적(`failures`), `market_id/event_id` 정규화 반환 구현 |
| I-03 | Implemented | `registry/build_registry.py`, `registry/conflict_rules.py`, `pipelines/registry_linker.py`로 필수 식별자/충돌 규칙/slug 이력/스냅샷 enrich 연결 구현 |
| I-04 | Implemented | `storage/writers.py`, `storage/layout.md`에 raw(JSONL)/derived(parquet) 분리, `dt=YYYY-MM-DD` 파티션, idempotent overwrite 구현 |
| I-05 | Implemented | `agents/label_resolver.py`의 4상태 분리 + `calibration/labeling.py`의 binary 변환(기본 multi-outcome 제외), `pipelines/build_scoreboard_artifacts.py`의 `label_status` 기반 기본 제외 규칙 연동 구현 |
| I-06 | Implemented | `pipelines/build_cutoff_snapshots.py`에 T-24h/T-1h/Daily nearest-before 선택 및 fallback 구현, `pipelines/daily_job.py` cutoff stage 연동 완료 |
| I-07 | Implemented | `features/build_features.py`에 returns/vol/volume_velocity/oi_change/tte/liquidity_bucket 계산 및 결정론 정렬 구현 |
| I-08 | Implemented | `runners/baselines.py`에 EWMA/Kalman/Rolling Quantile q10/q50/q90, logit 옵션, 단일 dispatch 구현 |
| I-09 | Implemented | `runners/tsfm_base.py`에 `TSFMRunnerBase.forecast_quantiles`, `RunnerConfig`, `ForecastResult` 계약 구현 |
| I-10 | Implemented | `calibration/conformal.py` + `calibration/drift.py`에 conformal 보정/coverage 리포트/재학습 트리거 구현 |
| I-11 | Implemented | `agents/question_quality_agent.py` + `llm/schemas.py`에 strict JSON, 필수 키 강제, rationale(1~5), 재시도(최대 3회 시도) 구현 |
| I-12 | Implemented | `llm/client.py`, `llm/policy.py`, `llm/cache.py`, `llm/sqlite_cache.py`에 seed/temperature/top_p 정책 고정, 캐시 키 반영, SHA-256 무결성 경로 구현 |
| I-13 | Implemented | `calibration/metrics.py`와 `pipelines/build_scoreboard_artifacts.py`에 Brier/LogLoss/ECE/slope/intercept 및 `category×liquidity×TTE` 세그먼트 집계, parquet+markdown 산출 구현 |
| I-14 | Implemented | `calibration/trust_score.py`에 구성요소 로그+가중합(0~100) 구현, `pipelines/trust_policy_loader.py` + `pipelines/daily_job.py`에 YAML 가중치 주입 경로 구현 |
| I-15 | Partial | `agents/alert_agent.py`, `pipelines/build_alert_feed.py`, `pipelines/alert_policy_loader.py`, `pipelines/daily_job.py`에 config-driven 임계치/`min_trust_score` 주입이 구현되어 있고, strict gate 산식도 코드/테스트 기준으로 정렬됨: Gate1(`BAND_BREACH`) + Gate2(`LOW_OI_CONFIRMATION` or `VOLUME_SPIKE`) + Gate3(`LOW_AMBIGUITY`)를 모두 충족해야 `MED/HIGH`, `HIGH`는 `LOW_OI_CONFIRMATION`과 `VOLUME_SPIKE` 동시 충족이 필요. 다만 네트워크 포함 ingest→publish 통합 회귀는 아직 없어 보수적으로 `Partial` 유지 |
| I-16 | Implemented | `connectors/polymarket_ws.py`, `pipelines/realtime_ws_job.py`, `pipelines/aggregate_intraday_bars.py`에 재연결/하트비트/백오프, 동적 구독, 1m·5m OHLC/`trade_count`/`realized_vol` 집계 구현 |
| I-17 | Implemented | `agents/explain_agent.py` + `agents/explain_validator.py`에 evidence guardrail, 5줄/140자 제한, 면책문구 옵션, evidence-bound 위반 라인 후처리(marking) 구현 |
| I-18 | Implemented | `reports/postmortem.py`, `pipelines/build_postmortem_batch.py`에 고정 섹션/결정론 생성 + 파일명 `{market_id}_{resolved_date}.md` 규칙 구현 |
| I-19 | Implemented | `pipelines/daily_job.py`에 `discover→...→publish` 결선, checkpoint/resume, `stage_retry_limit`, `continue_on_stage_failure`, backfill 인자 구현 |
| I-20 | Implemented | `api/app.py`에 `/scoreboard`, `/alerts`, `/postmortem/{market_id}`와 필터/페이징이 구현되어 있고, `api/dependencies.py`의 `load_postmortem()`가 `{market_id}_{resolved_date}.md` 패턴 최신본 우선 + `{market_id}.md` fallback 조회를 지원 |

## 이번 배치에서 해결된 항목

- `I-05`: `label_status` 기반 binary 변환/기본 제외 규칙이 scoreboard 빌더에 연결됨
- `I-12`: `top_p` 정책 및 캐시 키 반영이 추가되어 샘플링 파라미터 고정 범위 확장
- `I-13`: global slope/intercept + `category×liquidity×TTE` 세그먼트 집계 추가
- `I-14`: trust 가중치 YAML 로더와 `daily_job` 주입 경로 연결
- `I-17`: explain evidence-bound validator 추가 및 agent 후처리 연동
- `I-18`: postmortem 파일명 규칙 `{market_id}_{resolved_date}.md` 반영
- `I-20`: postmortem 조회 로직이 `{market_id}_{resolved_date}.md` 패턴(최신 resolved_date 우선)과 legacy `{market_id}.md` fallback을 모두 지원하도록 보강

## 남은 항목 (AC 기준)

- `I-15`: strict gate 산식/단위 테스트 정렬은 완료되었고, 잔여 과제는 ingest→publish 실데이터 통합 회귀에서 gate + `min_trust_score` 경계 동작 검증

## 남은 테스트/검증 공백

- 실데이터 통합 회귀 부재: Gamma/Subgraph/WS 포함 ingest→publish E2E(네트워크 포함) 검증 없음
- `I-15`/`I-20` 핵심 회귀는 반영됨: `tests/unit/test_i15_acceptance.py`, `tests/unit/test_alert_feed_gate_rules.py`, `tests/unit/test_api_postmortem_latest.py`, `tests/unit/test_postmortem_loader_pattern.py`로 strict gate 조합과 postmortem 최신본/패턴 fallback이 검증됨

## 남은 Actionable Backlog (<=5)

1. 통합 회귀 보강: 네트워크 포함 ingest→publish E2E 스모크(최소 1일 샘플)로 배치 경로를 주기 검증

## PRD1+PRD2 alert-gates gap closure

- **Top-N selective inference orchestration 추가(PRD2 §2/§13 반영):**
  - `pipelines/alert_topn_orchestration.py`
    - `rank_top_n_markets(...)`: watchlist → alert-candidate → 유동성/신뢰 복합점수 순으로 **결정론적** 정렬
    - `orchestrate_top_n_alert_decisions(...)`: top-N만 TSFM forecast 수행 후 I-15 gate를 적용해 per-market decision(`EMIT`/`SUPPRESS`) 출력
- **Decision output 표준화:**
  - 선택 제외는 `SUPPRESS/TOP_N_EXCLUDED`
  - trust 미달(또는 trust 누락) 시 `SUPPRESS/TRUST_GATE` (보수적 deterministic default)
  - gate 미충족 시 `SUPPRESS/ALERT_GATE`
  - 발행 시 `severity/reason_codes/alert payload/forecast_meta` 포함
- **운영용 스모크 스크립트 추가:**
  - `pipelines/run_topn_alert_cycle.py`
  - 입력 후보 JSON + alerts config 기준으로 1회 top-N 결정 사이클 실행/결과 JSON 출력
- **회귀 테스트 추가:**
  - `tests/unit/test_alert_topn_orchestration.py`
    - Top-N 정렬 우선순위 결정론 검증
    - emit/suppress decision 경로(Top-N 제외, trust gate, alert gate) 검증
    - trust 누락 시 보수적 suppress 기본값 검증
