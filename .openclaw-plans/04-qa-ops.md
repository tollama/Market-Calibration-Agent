# QA/운영 계획 (Agent D)

## 1) 테스트 전략

### 1.1 범위와 품질 게이트
- 대상 범위: MVP-1(I-01~I-14, I-19), MVP-2(I-15~I-18, I-16).
- PRD 성공지표를 품질 게이트로 사용:
  - 일일 Scoreboard 생성 성공률 99% 이상.
  - 라벨 정제 정확도 95% 이상(RESOLVED vs VOID/UNRESOLVED).
  - 동일 입력 재실행 시 동일 결과(재현성).
  - MVP-2 알림 지연 1~5분, 오탐률 30% 이하로 지속 개선.
- 테스트 피라미드 목표 비율: Unit 70%, Integration 20%, E2E/Backtest 10%.
- CI 차단 조건:
  - 실패 테스트 1건 이상.
  - 스키마 계약 테스트 실패.
  - 재현성 스모크 테스트 실패(고정 seed/config).

### 1.2 Unit 테스트
- 목적: 각 모듈의 결정론/예외 처리/경계값을 빠르게 검증.
- 공통 원칙:
  - 외부 I/O(API/DB/LLM)는 mock/stub으로 격리.
  - 시간/난수 의존 로직은 freeze time + seed 고정.
  - 0/1 확률 경계, 빈 데이터, NaN, 중복 입력을 기본 케이스로 포함.

| 모듈 | 핵심 테스트 항목 | 합격 기준 |
|---|---|---|
| 커넥터(Gamma/Subgraph/WS) | 페이지네이션, rate limit, timeout, backoff, 재시도 후 중복 제거 | 동일 원본 입력 대비 중복 없는 결과 |
| Registry/Label Resolver | ID 매핑 우선순위, slug 변경 이력, 상태 분류(4종) | 충돌 규칙 위반 0건 |
| Snapshot/Feature | T-24h/T-1h nearest/fallback, 파생피처 계산, NaN 처리 | 동일 입력 해시 기준 결과 동일 |
| Baseline/TSFM/Conformal | q10/q50/q90 산출, 0~1 경계 처리, coverage 계산 | 범위 이탈(0 미만/1 초과) 0건 |
| LLM Quality/Cache/Explain | JSON 스키마 강제, 재시도(최대 2회), 캐시 키 일관성 | 스키마 누락 필드 0건, 캐시 해시 충돌 0건 |
| Calibration/Trust/Alert | Brier/LogLoss/ECE, 구성요소 로그, 3단계 게이트, severity 분류 | 규칙 기반 기대값과 완전 일치 |
| Orchestration | 단계 체크포인트, idempotent 재실행, backfill 기간 처리 | 재실행 시 중복/오염 0건 |

### 1.3 Integration 테스트
- 목적: 모듈 경계(API-저장소-파이프라인-지표)의 계약 일관성 검증.
- 환경:
  - 로컬/CI에서 mock API 서버 + 임시 parquet/sqlite 사용.
  - 표준 fixture: 정상 데이터, 부분 누락 데이터, 스키마 변경 데이터.
- 필수 시나리오:
  1. `discover -> ingest -> normalize -> snapshots` 경로에서 `market_registry`, `market_snapshot` 스키마 준수 확인.
  2. `features -> calibration -> scoreboard publish` 경로에서 세그먼트 지표(category x liquidity x TTE) 생성 확인.
  3. LLM 품질 점수 경로에서 JSON 검증 실패 후 재시도/캐시 히트 동작 확인.
  4. Alert 경로에서 Gate1/2/3, severity, reason_codes, evidence 필드 일관성 확인.
  5. 부분 실패(커넥터 1개 실패) 시 체크포인트 기반 복구 및 재실행 검증.

### 1.4 E2E 테스트
- 목적: 실제 운영 플로우 단위의 품질/안정성/복구 시간 검증.
- MVP-1 E2E:
  - 일일 배치 전체 실행 후 Scoreboard와 markdown 요약 산출 확인.
  - 실패 주입(네트워크 오류, raw 파일 손상, 스키마 누락) 후 재실행 복구 확인.
  - 배치 3회 연속 성공 + 출력 재현성 비교(동일 입력 해시).
- MVP-2 E2E:
  - WS ingest -> 1m/5m 집계 -> band -> alert -> explain 5줄 저장까지 검증.
  - 알림 지연 p95가 5분 이내인지 측정.
  - 알림 폭주/침묵 시 보호 동작(게이트 강화, FYI 강등, 임시 mute) 확인.

### 1.5 Backtest 전략
- 목적: 캘리브레이션 품질과 알림 품질을 릴리즈 전 정량 검증.
- 데이터 분할:
  - Walk-forward(예: 주/월 단위)로 학습/보정/평가 구간 분리.
  - 최신 구간 홀드아웃 유지(최소 30일)로 최종 점검.
  - 라벨은 `RESOLVED_TRUE/FALSE`만 사용, VOID/UNRESOLVED는 제외.
- 평가 항목:
  - Calibration: Brier, LogLoss, ECE, slope/intercept(전체 + 세그먼트).
  - Band: 목표 coverage 대비 오차(80/90% 목표 별도 측정).
  - Alert: 정밀도, 오탐률, 탐지 지연, severity 분포.
  - Trust Score: 점수 구간별 실제 적중/캘리브레이션 단조성 확인.
- 누수 방지 규칙:
  - T-24h/T-1h 컷오프 이후 정보 사용 금지.
  - 종료 라벨 공개 시점 이전에는 정답 참조 금지.
  - 피처 생성 시 미래 시점 집계값 참조 금지.
- 릴리즈 승인 최소 조건:
  - MVP-1: 핵심 세그먼트에서 ECE 악화(직전 버전 대비) 없음.
  - MVP-2: 오탐률 30% 이하 또는 직전 대비 개선 추세 + 지연 p95 5분 이내.

## 2) 관측성(Observability) 지표 및 알림

### 2.1 관측성 원칙
- 로그: JSON 구조화 로그(필수 키: `run_id`, `stage`, `market_id`, `event_id`, `model_version`, `prompt_version`).
- 메트릭: 시계열 수집(예: Prometheus 호환 네이밍).
- 트레이싱: 파이프라인 단계별 지연/실패 위치 추적(`trace_id`, `span_id`).
- 데이터 계보: raw/derived 버전, 모델 버전, 프롬프트 버전 동시 기록.

### 2.2 핵심 운영 메트릭
| 영역 | 메트릭 | 목표/임계치 |
|---|---|---|
| 배치 신뢰성 | `job_success_rate_24h` | 목표 >= 0.99, 경고 < 0.99, 치명 < 0.97 |
| 단계 안정성 | `stage_failure_count{stage}`, `stage_retry_count{stage}` | 급증(7일 중앙값 대비 2배) 시 경고 |
| 처리 지연 | `pipeline_lag_minutes`, `alert_latency_seconds_p95` | MVP-2 p95 <= 300초 |
| 데이터 품질 | `snapshot_missing_rate`, `schema_drift_count`, `registry_conflict_count` | drift/conflict 1건 이상 즉시 알림 |
| 라벨 품질 | `label_void_ratio`, `label_unresolved_ratio` | 급변 시 데이터 점검 알림 |
| 모델 품질 | `ece_total`, `brier_total`, `band_coverage_80/90` | coverage 이탈 지속 시 재보정 트리거 |
| 알림 품질 | `alerts_total_by_severity`, `alert_false_positive_rate_7d` | 오탐률 > 0.30 시 P2 |
| LLM 운영 | `llm_json_retry_rate`, `llm_cache_hit_rate`, `llm_latency_p95`, `llm_cost_daily` | 재시도율/비용 급증 시 경고 |

### 2.3 알림 정책(예시)
- P1 (즉시 호출):
  - 일일 배치 연속 1회 실패 또는 데이터 손상 의심.
  - 스키마 드리프트로 핵심 파이프라인 중단.
  - 알림 지연 p95 > 10분이 30분 이상 지속.
- P2 (업무시간 내 대응):
  - `job_success_rate_24h < 0.99`.
  - `alert_false_positive_rate_7d > 0.30`.
  - `band_coverage`가 목표 대비 10%p 이상 이탈(연속 2윈도우).
- P3 (백로그/튜닝):
  - 캐시 히트율 저하, 비용 증가, 비핵심 지연 증가 등.

### 2.4 대시보드 구성
- 대시보드 A: 배치 파이프라인 상태(성공률/지연/실패 단계).
- 대시보드 B: 데이터 품질(결측률/스키마/레지스트리 충돌/라벨 분포).
- 대시보드 C: 모델/캘리브레이션(ECE/Brier/coverage/세그먼트 비교).
- 대시보드 D: 알림 품질(발생량, severity 비율, 오탐률, 지연).

## 3) 인시던트 런북 초안

### 3.1 역할
- Incident Commander(IC): 우선순위 결정, 커뮤니케이션 총괄.
- Ops On-call: 파이프라인/인프라 복구 실행.
- Data/Model Owner: 데이터 품질/모델 드리프트 진단.
- Recorder: 타임라인/조치 기록, 사후보고서 초안 작성.

### 3.2 심각도 정의
- Sev-1: 핵심 서비스 중단 또는 잘못된 결과 대량 배포 위험.
- Sev-2: 품질 저하가 명확하고 사용자 영향이 중간 이상.
- Sev-3: 기능은 유지되나 품질/비용/지연 튜닝 필요.

### 3.3 공통 대응 절차
1. 탐지/접수: 알림 수신 후 10분 내 Sev 분류, IC 지정.
2. 영향도 확인: 영향 범위(시장 수, 지표, 알림 채널)와 시작 시각 확정.
3. 완화: 배포 중지, publish hold, 문제 단계 격리(ingest/normalize/alert).
4. 복구: 체크포인트 기준 재실행 또는 직전 안정 버전으로 롤백.
5. 검증: 핵심 메트릭 정상화(성공률/지연/오탐률/coverage) 확인.
6. 종료: 타임라인, 원인, 재발 방지 액션을 24시간 내 기록.

### 3.4 시나리오별 플레이북

#### A. 데이터 수집 실패(Gamma/Subgraph/WS)
- 트리거: 수집 0건, 재시도 급증, API 오류율 급증.
- 즉시 조치:
  - rate limit 하향, backoff 상향.
  - 실패 소스만 격리 후 나머지 단계 진행 가능 여부 판단.
  - 필요 시 이전 정상 스냅샷으로 임시 운영(읽기전용).
- 복구 기준: 최근 파티션 정상 적재 + 중복/누락 검사 통과.

#### B. 스키마 드리프트/레지스트리 충돌
- 트리거: 필수 필드 파싱 실패, `registry_conflict_count > 0`.
- 즉시 조치:
  - 신규 raw 파티션 quarantine.
  - 파서 hotfix 또는 매핑 규칙 업데이트.
  - 영향 기간 재처리(backfill) 범위 확정.
- 복구 기준: 스키마 계약 테스트 통과, 충돌 0건.

#### C. 라벨 오염(VOID/UNRESOLVED 혼입)
- 트리거: 라벨 분포 급변, 수작업 샘플 불일치 증가.
- 즉시 조치:
  - Scoreboard publish 일시 중지.
  - label resolver 재실행 + 샘플 검수.
  - 오염 구간 재산출 후 대체 게시.
- 복구 기준: 샘플 정확도 95% 이상 회복.

#### D. 알림 폭주/침묵
- 트리거: 알림량이 기준 대비 3배 이상 급증 또는 장시간 0건.
- 즉시 조치:
  - Gate 임계치 임시 상향/하향으로 안전 모드 진입.
  - HIGH 알림만 유지하거나 FYI 강등 정책 활성화.
  - band/coverage 드리프트와 데이터 지연 동시 점검.
- 복구 기준: 알림량/지연/오탐률 정상 범위 복귀.

#### E. LLM 품질/비용 이상
- 트리거: JSON 재시도율 급등, 응답 지연/비용 급증.
- 즉시 조치:
  - 캐시 우선 모드 활성화, 비핵심 LLM 호출 차단.
  - 고정 모델/프롬프트 버전으로 롤백.
  - explain 생성 실패 시 템플릿 fallback 사용.
- 복구 기준: 재시도율, 지연, 비용 정상화.

### 3.5 커뮤니케이션 템플릿
- 제목: `[Sev-X][상태] 요약`
- 본문:
  - 발생 시각(UTC/KST), 영향 범위, 현재 상태(조사중/완화/복구완료)
  - 임시 조치, 사용자 영향, 다음 업데이트 시각
  - 담당자(IC, 실행 담당)

## 4) 릴리즈 체크리스트

### 4.1 사전 체크(공통)
- 코드/설정 동결 버전 태깅(`data_version`, `model_version`, `prompt_version`).
- 스키마 변경 검토(하위 호환성, 마이그레이션/롤백 경로).
- 단위/통합/E2E 테스트 전부 통과.
- Backtest 리포트 첨부(핵심 지표 + 세그먼트 결과).
- 대시보드/알림 룰 배포 및 테스트 알림 수신 확인.
- 런북 링크/담당 온콜 일정 확인.

### 4.2 MVP-1 배포 게이트
- I-01~I-14, I-19 AC 증빙 완료.
- 일일 배치 3회 연속 성공(스테이징 또는 리허설).
- Scoreboard 재현성 검증 통과(동일 입력/동일 출력).
- 라벨 샘플 검수 정확도 95% 이상.

### 4.3 MVP-2 추가 게이트
- WS ingest/집계 soak test(최소 24시간) 통과.
- Alert E2E(게이트/심각도/5줄 설명) 시나리오 통과.
- 알림 지연 p95 5분 이내 확인.
- 오탐률 기준(30% 이하 또는 개선 추세) 확인.

### 4.4 배포 실행
1. Canary: 일부 시장/카테고리 대상으로 우선 배포.
2. 30~60분 집중 모니터링(성공률/지연/오탐/coverage).
3. 이상 없으면 전체 확장 배포.
4. 배포 후 첫 배치/첫 스트림 윈도우 결과를 QA 승인.

### 4.5 롤백 조건
- 배치 실패율 급증 또는 데이터 무결성 실패.
- 지표/알림 결과가 신뢰 불가 수준으로 왜곡.
- 복구 예상 시간이 SLA를 초과.
- 롤백 시 직전 안정 태그로 복귀 후 영향 구간 재처리 계획 즉시 공지.

