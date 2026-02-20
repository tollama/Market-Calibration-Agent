# PRD1 구현 상태 (I-01~I-20)

기준 시점: 2026-02-20 (현재 워크트리 코드 기준)  
판정 기준:
- `Implemented`: PRD AC 핵심 요건 충족
- `Partial`: 구현은 있으나 AC 일부 미충족 또는 운영 연결 미완료
- `Planned`: 실질 구현 없음/스켈레톤

## 상태 매핑

| 이슈 | 상태 | 현재 코드 기준 요약 |
| --- | --- | --- |
| I-01 | Partial | `connectors/polymarket_gamma.py`에 페이지네이션/재시도/RPS 제한은 구현. 다만 `pipelines/ingest_gamma_raw.py` 경로/원문 보존 규칙이 PRD의 `raw/gamma/dt=...` 원문 보존 규약과 완전 일치하지 않음 |
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
| I-15 | Partial | `agents/alert_agent.py`, `pipelines/build_alert_feed.py`, `pipelines/alert_policy_loader.py`, `pipelines/daily_job.py`에 config-driven 임계치/`min_trust_score` 주입은 구현. 다만 PRD의 “Gate1~3 미충족 시 HIGH/MED 금지” 엄격 게이트 조건은 아직 불일치 |
| I-16 | Implemented | `connectors/polymarket_ws.py`, `pipelines/realtime_ws_job.py`, `pipelines/aggregate_intraday_bars.py`에 재연결/하트비트/백오프, 동적 구독, 1m·5m OHLC/`trade_count`/`realized_vol` 집계 구현 |
| I-17 | Implemented | `agents/explain_agent.py` + `agents/explain_validator.py`에 evidence guardrail, 5줄/140자 제한, 면책문구 옵션, evidence-bound 위반 라인 후처리(marking) 구현 |
| I-18 | Implemented | `reports/postmortem.py`, `pipelines/build_postmortem_batch.py`에 고정 섹션/결정론 생성 + 파일명 `{market_id}_{resolved_date}.md` 규칙 구현 |
| I-19 | Implemented | `pipelines/daily_job.py`에 `discover→...→publish` 결선, checkpoint/resume, `stage_retry_limit`, `continue_on_stage_failure`, backfill 인자 구현 |
| I-20 | Partial | `api/app.py`에 `/scoreboard`, `/alerts`, `/postmortem/{market_id}`는 구현됐으나, `api/dependencies.py`의 postmortem 로더가 `{market_id}.md`만 조회해 I-18 파일명 규칙(`{market_id}_{resolved_date}.md`)과 불일치 |

## 이번 배치에서 해결된 항목

- `I-05`: `label_status` 기반 binary 변환/기본 제외 규칙이 scoreboard 빌더에 연결됨
- `I-12`: `top_p` 정책 및 캐시 키 반영이 추가되어 샘플링 파라미터 고정 범위 확장
- `I-13`: global slope/intercept + `category×liquidity×TTE` 세그먼트 집계 추가
- `I-14`: trust 가중치 YAML 로더와 `daily_job` 주입 경로 연결
- `I-17`: explain evidence-bound validator 추가 및 agent 후처리 연동
- `I-18`: postmortem 파일명 규칙 `{market_id}_{resolved_date}.md` 반영

## 남은 항목 (AC 기준)

- `I-01`: Gamma raw 저장 규약(원문 보존 + PRD 경로 규칙) 정합성 보완 필요
- `I-15`: 3단계 게이트 엄격 조건(PRD AC 20번) 기준으로 severity 규칙 재정의 필요
- `I-20`: postmortem 조회 로직을 새 파일명 규칙과 호환되도록 보완 필요

## 남은 테스트/검증 공백

- 실데이터 통합 회귀 부재: Gamma/Subgraph/WS 포함 ingest→publish E2E(네트워크 포함) 검증 없음
- `I-01` 원문 보존 검증 부족: raw가 “원문 그대로 + PRD 경로”로 남는지 통합 테스트 없음
- `I-15` AC 정합 테스트 부족: Gate1~3 엄격 충족 시나리오에 대한 acceptance 테스트 없음
- `I-20` 연계 테스트 부족: `{market_id}_{resolved_date}.md` 생성물과 `/postmortem/{market_id}` 조회 호환 테스트 없음

## 남은 Actionable Backlog (<=5)

1. `pipelines/ingest_gamma_raw.py` 저장 규칙을 PRD 경로(`raw/gamma/dt=...`)와 원문 보존 정책에 맞게 정렬
2. `agents/alert_agent.py` severity 산식을 Gate1~3 엄격 조건(미충족 시 HIGH/MED 금지)으로 수정
3. `api/dependencies.py` `load_postmortem()`를 `{market_id}_{resolved_date}.md` 패턴 조회(최신 resolved_date 우선)로 개선
4. `configs/default.yaml`와 `pipelines/trust_policy_loader.py`의 trust weight 스키마 경로(`calibration.trust_score`) 정합화
5. `tests/unit`에 I-01/I-15/I-20 AC 중심 통합 시나리오(경로/게이트/조회 연계) 추가
