# PRD1 구현 상태 (I-01~I-20)

기준 시점: 2026-02-20 (현재 브랜치 코드 기준)  
판정 기준:
- `Implemented`: PRD AC 핵심 요건 충족
- `Partial`: 구현은 있으나 AC 일부 미충족 또는 운영 연결 미완료
- `Planned`: 실질 구현 없음/스켈레톤

## 상태 매핑

| 이슈 | 상태 | 현재 코드 기준 요약 |
| --- | --- | --- |
| I-01 | Partial | `connectors/polymarket_gamma.py`에 페이지네이션/재시도/rate-limit 구현, `pipelines/ingest_gamma_raw.py`로 raw 저장 연계 완료. 다만 PRD의 raw 원문 보존 경로/형식(`raw/gamma/...`)과 1:1로 맞춘 저장 규약은 미완료 |
| I-02 | Implemented | `connectors/polymarket_subgraph.py`에 QueryTemplates, 재시도 백오프, 부분 실패 누적(`failures`), `market_id/event_id` 정규화 반환 구현 |
| I-03 | Implemented | `registry/build_registry.py` + `registry/conflict_rules.py`에 upsert/충돌 규칙/slug 이력 반영, `pipelines/registry_linker.py`로 snapshot enrich 연계 구현 |
| I-04 | Implemented | `storage/writers.py`, `storage/layout.md`로 raw(JSONL)/derived(parquet) 분리, `dt=YYYY-MM-DD` 파티션, idempotent overwrite 구현 |
| I-05 | Partial | `agents/label_resolver.py`와 `calibration/labeling.py`로 4상태 분리 및 binary 라벨 변환 구현. multi-outcome 별도 타입 운영 규칙/scoreboard 기본 제외의 파이프라인 강제는 미완료 |
| I-06 | Partial | `pipelines/build_cutoff_snapshots.py`에 nearest-before 및 fallback 룰 구현. 그러나 기본 stage가 실데이터 대신 placeholder 경로를 주로 사용 |
| I-07 | Implemented | `features/build_features.py`에 returns/vol/volume_velocity/oi_change/tte/liquidity_bucket 계산 및 결정론 정렬 처리 구현 |
| I-08 | Implemented | `runners/baselines.py`에 EWMA/Kalman/Rolling Quantile 모두 q10/q50/q90 산출, logit 옵션, 단일 dispatch(`forecast_baseline_band`) 구현 |
| I-09 | Implemented | `runners/tsfm_base.py`에 `TSFMRunnerBase.forecast_quantiles(...)`, `RunnerConfig`, `ForecastResult`(메타/디바이스 필드 포함) 정의 |
| I-10 | Implemented | `calibration/conformal.py`에 보정량 학습/적용/coverage 리포트, `calibration/drift.py`에 재학습 트리거 평가 로직 구현 |
| I-11 | Implemented | `agents/question_quality_agent.py` + `llm/schemas.py`에 strict JSON, `market_id/llm_model/prompt_version` 필수, rationale 1~5개, 최대 2회 재시도(총 3회 시도) 구현 |
| I-12 | Partial | `llm/cache.py`/`llm/sqlite_cache.py`/`llm/client.py`로 SHA-256 기반 캐시와 영속 캐시 구현. 다만 seed/top_p 등 샘플링 재현성 정책 고정은 미완료 |
| I-13 | Partial | `calibration/metrics.py`에 Brier/LogLoss/ECE/slope/intercept 구현, `pipelines/build_scoreboard_artifacts.py`에 parquet+markdown 출력 구현. category×liquidity×TTE 교차 세그먼트 미구현 |
| I-14 | Partial | `calibration/trust_score.py`에 가중합/구성요소 로그 row 생성 구현. config 파일 기반 가중치 로딩 및 파이프라인 주입 미완료 |
| I-15 | Partial | `agents/alert_agent.py` + `pipelines/build_alert_feed.py`로 밴드 이탈/확증 게이트/Severity 생성 구현. YAML 기반 임계치 주입과 trust 연계 운영 규칙은 미완료 |
| I-16 | Partial | `connectors/polymarket_ws.py`, `pipelines/realtime_ws_job.py`, `pipelines/aggregate_intraday_bars.py`로 재연결/1m·5m 집계 기본 구현. 동적 구독, 거래량/실현변동성 표준 컬럼은 미완료 |
| I-17 | Partial | `agents/explain_agent.py`에 5줄 생성, 140자 제한, 면책문구 옵션 구현. evidence 밖 주장 차단을 코드 레벨로 검증하는 강제 장치는 미완료 |
| I-18 | Partial | `reports/postmortem.py`, `pipelines/build_postmortem_batch.py`에 고정 섹션/결정론 생성 구현. 파일명 규칙이 `market_id + resolved_date`를 아직 반영하지 않음 |
| I-19 | Partial | `pipelines/daily_job.py`에 단계 순서/체크포인트/재개/백필 메타/stage hook 구현. 실 stage end-to-end 결선과 실패 재시도 정책 하드닝은 미완료 |
| I-20 | Implemented | `api/app.py`에 `/scoreboard`, `/alerts`, `/postmortem/{market_id}` 읽기전용 API 및 기본 필터/페이지네이션 구현 |

## 남은 기능 갭 (AC 기준)

- `I-01`: Gamma 응답 원문(JSONL) 보존 규약을 PRD 경로(`raw/gamma/dt=...`)로 통일하고, 정규화본과 분리 저장 필요
- `I-05`: multi-outcome 전용 라벨 타입 및 scoreboard 기본 제외 규칙을 파이프라인 레벨에서 강제 필요
- `I-06`: cutoff stage에서 placeholder 제거, 실제 snapshot source_rows 연동 필요
- `I-12`: seed/top_p 등 샘플링 파라미터 고정 정책 및 캐시 키 반영 필요
- `I-13`: category×liquidity×TTE 교차 세그먼트 및 slope/intercept 아티팩트 노출 필요
- `I-14`: config(yaml) 기반 trust 가중치 주입 경로 필요
- `I-15`: alert 임계치의 config-driven 로딩/주입 및 trust gate 결합 규칙 필요
- `I-16`: market_id(asset_id) 동적 구독, 표준 거래량/실현변동성 집계 컬럼 필요
- `I-17`: evidence-bound 위반 탐지(후처리 validator) 필요
- `I-18`: postmortem 파일명 `market_id + resolved_date` 규칙 반영 필요
- `I-19`: `discover -> ingest -> normalize -> snapshots -> cutoff -> features -> metrics -> publish` 실 데이터 E2E 결선 및 retry/skip 정책 고정 필요

## 남은 테스트/검증 공백

- `calibration/conformal.py`: fit/apply/coverage 핵심 경로 단위테스트 부재
- `runners/tsfm_base.py`: 인터페이스 계약(메타/quantile shape) 검증 테스트 부재
- `agents/question_quality_agent.py`: strict JSON 실패 후 재시도 경로 테스트 부재
- `agents/explain_agent.py`: 140자 truncate/면책문구 on-off 정책 테스트 부재
- `pipelines/daily_job.py`: 실제 stage 조합(ingest~publish) E2E 회귀 테스트 부재
- `pipelines/realtime_ws_job.py` + `pipelines/aggregate_intraday_bars.py`: 거래량/실현변동성 집계 표준 검증 테스트 부재 (현재 기능도 미완료)

## 즉시 추가 구현 항목

1. `I-06` 실데이터 cutoff 연결: `pipelines/build_cutoff_snapshots.py`, `pipelines/daily_job.py`에서 `source_rows` 실제 주입 경로 추가 및 placeholder 모드 기본 비활성화
2. `I-13` 세그먼트 확장: `calibration/metrics.py`, `pipelines/build_scoreboard_artifacts.py`에 `category x liquidity_bucket x tte_bucket` 교차 리포트와 slope/intercept 출력 추가
3. `I-16` 스트림 집계 보강: `connectors/polymarket_ws.py`, `pipelines/aggregate_intraday_bars.py`, `pipelines/realtime_ws_job.py`에 동적 구독 + `volume/trade_count/realized_vol` 컬럼 추가
4. `I-18` 파일명 규칙 정합화: `reports/postmortem.py`, `pipelines/build_postmortem_batch.py`에 `{market_id}_{resolved_date}.md` 저장 규칙 도입
5. `I-12` 재현성 정책 고정: `llm/client.py` 캐시 키/요청 파라미터에 `seed/top_p` 포함, `agents/question_quality_agent.py`/`agents/explain_agent.py` 호출부 고정값 주입
6. `I-19` 오케스트레이션 결선: `pipelines/daily_job.py`에서 ingest→registry→cutoff→feature→scoreboard/alerts/postmortem 기본 실행 경로를 hook 없이도 동작하도록 연결
