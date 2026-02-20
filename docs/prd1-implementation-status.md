# PRD1 구현 상태 (I-01~I-20)

기준 시점: 2026-02-20 (현재 브랜치, `a6fb7e6` 이후 코드 기준)  
판정 기준:
- `Implemented`: PRD AC 핵심 요건 충족
- `Partial`: 구현은 있으나 AC 일부 미충족 또는 운영 연결 미완료
- `Planned`: 실질 구현 없음/스켈레톤

## 상태 매핑

| 이슈 | 상태 | 현재 코드 기준 요약 |
| --- | --- | --- |
| I-01 | Partial | `connectors/polymarket_gamma.py` + `pipelines/ingest_gamma_raw.py`로 수집/저장 연계는 완료. 다만 PRD 원문 보존 규약(원문/정규화 분리와 경로 표준화)은 여전히 미완료 |
| I-02 | Implemented | `connectors/polymarket_subgraph.py`에 템플릿 쿼리, 재시도 백오프, 부분 실패 누적, `market_id/event_id` 정규화 반환 구현 |
| I-03 | Implemented | `registry/build_registry.py`, `registry/conflict_rules.py`, `pipelines/registry_linker.py`로 upsert/충돌 규칙/스냅샷 enrich 연결 구현 |
| I-04 | Implemented | `storage/writers.py`, `storage/layout.md` 기준으로 raw(JSONL)/derived(parquet) 분리, `dt=YYYY-MM-DD` 파티션, idempotent overwrite 구현 |
| I-05 | Partial | `agents/label_resolver.py` + `calibration/labeling.py`에 4상태 분리와 binary 변환(기본 multi-outcome 제외) 구현. 다만 이 규칙의 파이프라인 강제는 미완료 |
| I-06 | Implemented | `pipelines/build_cutoff_snapshots.py`가 `snapshot_rows/normalized_records` 기반 cutoff 후보를 생성하고 nearest-before 선택, `pipelines/daily_job.py` 기본 경로에서 source snapshot 연동 완료 (무데이터 시 placeholder fallback 유지) |
| I-07 | Implemented | `features/build_features.py`에 returns/vol/volume_velocity/oi_change/tte/liquidity_bucket 계산 및 결정론 정렬 구현 |
| I-08 | Implemented | `runners/baselines.py`에 EWMA/Kalman/Rolling Quantile q10/q50/q90, logit 옵션, 단일 dispatch 구현 |
| I-09 | Implemented | `runners/tsfm_base.py`에 `TSFMRunnerBase.forecast_quantiles`, `RunnerConfig`, `ForecastResult` 계약 구현 |
| I-10 | Implemented | `calibration/conformal.py` + `calibration/drift.py`에 conformal 보정/coverage/재학습 트리거 구현 |
| I-11 | Implemented | `agents/question_quality_agent.py` + `llm/schemas.py`에 strict JSON, 필수 키 강제, rationale(1~5), 최대 3회 시도(2회 재시도) 구현 |
| I-12 | Partial | `llm/client.py`, `llm/policy.py`, `llm/sqlite_cache.py`로 seed/temperature 기반 결정론 정책과 캐시 키 반영은 완료. `top_p` 등 샘플링 정책 확장은 미완료 |
| I-13 | Partial | `calibration/metrics.py`와 `pipelines/build_scoreboard_artifacts.py`에 global/category/liquidity 지표 및 아티팩트 출력 구현. `category×liquidity×TTE` 교차 세그먼트와 slope/intercept 노출은 미완료 |
| I-14 | Partial | `calibration/trust_score.py`에 구성요소/가중합 계산 구현. YAML 기반 가중치 로딩 및 파이프라인 주입 경로는 미완료 |
| I-15 | Partial | `agents/alert_agent.py`, `pipelines/build_alert_feed.py`에 임계치 override와 `min_trust_score` 게이트 구현. YAML config 로딩/주입은 미완료 |
| I-16 | Implemented | `connectors/polymarket_ws.py`, `pipelines/realtime_ws_job.py`, `pipelines/aggregate_intraday_bars.py`에 재연결 백오프, 동적 subscribe(message/list/callable), 1m·5m `volume_sum/trade_count/realized_vol` 집계 구현 |
| I-17 | Partial | `agents/explain_agent.py`에 evidence guardrail 프롬프트, 140자 제한, 면책문구 on/off 구현. evidence-bound 위반 후처리 validator는 미완료 |
| I-18 | Partial | `reports/postmortem.py`, `pipelines/build_postmortem_batch.py`에 고정 섹션/결정론 생성 구현. 파일명은 아직 `{market_id}.md`로, `resolved_date` 결합 규칙 미반영 |
| I-19 | Implemented | `pipelines/daily_job.py`에 `discover→...→publish` 기본 결선, checkpoint/resume, `stage_retry_limit`, `continue_on_stage_failure` 구현 |
| I-20 | Implemented | `api/app.py`에 `/scoreboard`, `/alerts`, `/postmortem/{market_id}` 읽기 전용 API와 기본 필터/페이지네이션 구현 |

## 남은 기능 갭 (AC 기준)

- `I-01`: Gamma 원문 보존 규약(원문/정규화 분리 + PRD 경로 표준) 확정 및 저장 규칙 일치화 필요
- `I-05`: multi-outcome 제외 규칙을 scoreboard/metrics 경로까지 파이프라인 단에서 강제 필요
- `I-12`: `top_p` 등 추가 샘플링 파라미터의 정책 고정/캐시 키 반영 필요
- `I-13`: `category × liquidity_bucket × tte_bucket` 교차 세그먼트 및 slope/intercept 아티팩트 노출 필요
- `I-14`: trust 가중치의 YAML 로딩 및 파이프라인 주입 경로 필요
- `I-15`: alert 임계치/`min_trust_score`의 config-driven 로딩 및 daily job 주입 필요
- `I-17`: explain 결과의 evidence-bound 위반 탐지 validator 필요
- `I-18`: postmortem 파일명 `{market_id}_{resolved_date}.md` 규칙 반영 필요

## 남은 테스트/검증 공백

- 실데이터 통합 회귀 부재: 실제 Gamma/Subgraph/WS를 묶은 ingest→publish E2E(네트워크 포함) 테스트 없음
- `I-13` 확장 지표 테스트 부재: 교차 세그먼트 및 slope/intercept 아티팩트 검증 테스트 없음
- `I-14`/`I-15` config 주입 테스트 부재: YAML 기반 trust/alert 주입 경로 검증 테스트 없음
- `I-17` validator 테스트 부재: evidence-bound 위반 탐지 및 차단 규칙 테스트 없음
- `I-18` 파일명 규칙 테스트 부재: `resolved_date` 결합 파일명 검증 테스트 없음

## 다음 실행 우선순위

1. `I-13`: scoreboard 산출물에 `category×liquidity×TTE` + slope/intercept 추가
2. `I-14`/`I-15`: YAML 기반 trust/alert 정책 로더와 `daily_job` 주입 경로 연결
3. `I-17`: explain post-validator(evidence-bound) 추가 및 실패 정책 정의
4. `I-18`: postmortem 파일명 규칙을 `{market_id}_{resolved_date}.md`로 통일
5. `I-01`/`I-05`: raw 원문 저장 규약 및 multi-outcome 파이프라인 강제 마무리
