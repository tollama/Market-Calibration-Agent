# PRD1 구현 상태 (I-01~I-20)

기준 시점: 2026-02-20 (현재 워크트리 코드 기준)  
판정 기준:
- `Implemented`: PRD AC 핵심 요건 충족
- `Partial`: 구현은 있으나 AC 일부 미충족 또는 운영 연결 미완료
- `Planned`: 실질 구현 없음/스켈레톤

## 상태 매핑

| 이슈 | 상태 | 현재 코드 기준 요약 |
| --- | --- | --- |
| I-01 | Partial | `connectors/polymarket_gamma.py`에 페이지네이션/재시도/RPS 제한 + `fetch_markets_raw`/`fetch_events_raw`가 구현됐고, `pipelines/ingest_gamma_raw.py`에서 `gamma/markets_original`, `gamma/events_original` 원문 저장까지 연결됨. 다만 저장 경로가 `raw/gamma/dt=...` 단일 규약이 아니라 `raw/gamma/{markets,events,...}/dt=...` 구조라 PRD 문구와 불일치 |
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

- `I-01`: Gamma raw 저장 경로를 PRD 표기(`raw/gamma/dt=...`)와 정합화할지, 현재 세분 경로(`raw/gamma/{dataset}/dt=...`)를 PRD에 반영할지 기준 확정 필요
- `I-15`: strict gate 산식/단위 테스트 정렬은 완료되었고, 잔여 과제는 ingest→publish 실데이터 통합 회귀에서 gate + `min_trust_score` 경계 동작 검증

## 남은 테스트/검증 공백

- 실데이터 통합 회귀 부재: Gamma/Subgraph/WS 포함 ingest→publish E2E(네트워크 포함) 검증 없음
- `I-01` AC 경계 테스트 부족: retry/rate-limit 동작과 저장 경로 규약(`raw/gamma/dt=...` vs `raw/gamma/{dataset}/dt=...`) 판정 테스트가 없음
- `I-15`/`I-20` 핵심 회귀는 반영됨: `tests/unit/test_i15_acceptance.py`, `tests/unit/test_alert_feed_gate_rules.py`, `tests/unit/test_api_postmortem_latest.py`, `tests/unit/test_postmortem_loader_pattern.py`로 strict gate 조합과 postmortem 최신본/패턴 fallback이 검증됨

## 남은 Actionable Backlog (<=5)

1. `I-01` 규약 결정: raw 저장 경로를 PRD(`raw/gamma/dt=...`)로 맞출지, 현행 경로(`raw/gamma/{dataset}/dt=...`)를 PRD에 반영할지 확정
2. `I-01` 구현 정렬: 확정된 경로 규약에 맞춰 `pipelines/ingest_gamma_raw.py`/관련 테스트를 일치시킴
3. 통합 회귀 보강: 네트워크 포함 ingest→publish E2E 스모크(최소 1일 샘플)로 배치 경로를 주기 검증
4. `I-15` 운영 경계 검증: 실데이터 fixture에서 strict gate + `min_trust_score` 조합 경계값 회귀를 추가
