# Agent C 구현 로드맵 (PRD1 기반)

## 1. 추진 원칙 및 일정 가정
- 범위: MVP-1(배치/읽기전용) 선출시 후 MVP-2(준실시간 알림) 확장
- 스프린트 단위: 2주, 단 `Sprint 0`은 1주 부트스트랩
- 기준 일정: 총 12주(부트스트랩 1주 + 2주 스프린트 5개 + 릴리즈 안정화 1주)
- 우선순위: P0 완결 > P1 운영 품질 > P2 조회 UX

## 2. Sprint Breakdown (Phased)
| Sprint | 기간 | 목표 | 포함 이슈(PRD) | 핵심 산출물 | 종료 DoD(요약) |
|---|---|---|---|---|---|
| Sprint 0 | Week 1 | 개발/데이터 표준 부트스트랩 | I-04(기반), I-19(골격) | 저장소 레이아웃, writer 인터페이스, 배치 파이프라인 스켈레톤 | 샘플 데이터 1회 E2E dry-run 성공 |
| Sprint 1 | Week 2-3 | 수집/식별자 기반 확립 | I-01, I-02, I-03, I-19(ingest/normalize) | Gamma/Subgraph 커넥터, registry upsert, raw/derived 저장 자동화 | 활성 시장 일괄 수집 + 중복 없는 적재 |
| Sprint 2 | Week 4-5 | 라벨 정제 및 분석용 스냅샷 생성 | I-05, I-06, I-07, I-19(snapshots/features) | label resolver, cutoff snapshot(T-24h/T-1h/Daily), feature frame | RESOLVED/VOID/UNRESOLVED 분리 정확도 목표 충족 |
| Sprint 3 | Week 6-7 | 예측밴드/보정 기반 구축 | I-08, I-09, I-10 | baseline band, TSFM 공통 인터페이스, conformal 보정 | 목표 커버리지 리포트 산출 및 재현 가능 |
| Sprint 4 | Week 8-9 | 캘리브레이션/신뢰도 MVP-1 출시 | I-11, I-12, I-13, I-14, I-19(publish) | question quality JSON, LLM cache, calibration metrics, trust score scoreboard | MVP-1 산출물(Scoreboard + markdown 요약) 배치 99%+ |
| Sprint 5 | Week 10-11 | 준실시간 알림 체계 | I-16, I-15, I-17 | WS ingest/1~5분 집계, alert engine, explain 5줄 생성 | 알림 지연 1~5분, severity/근거 저장 검증 |
| Sprint 6 | Week 12 | 사후 리포트/조회 인터페이스 및 안정화 | I-18, I-20 | post-mortem 자동 생성, 조회 API/CLI | 리포트 결정론 보장 + 조회 엔드포인트 운영 가능 |

## 3. WBS (Work Breakdown Structure)
| WBS ID | 작업 | 대응 이슈 | 선행 조건 | 책임 역할 | 산출물 |
|---|---|---|---|---|---|
| 1.1 | 저장 레이아웃 규격 확정(raw/derived/dt 파티션) | I-04 | 없음 | Data Engineer | `storage/layout.md`, 파티션 규약 |
| 1.2 | RawWriter/ParquetWriter 구현 및 테스트 | I-04 | 1.1 | Data Engineer | writer 모듈, 단위테스트 |
| 1.3 | 파이프라인 스켈레톤(discover->publish) 생성 | I-19 | 1.1 | Platform Engineer | `daily_job` 골격, 체크포인트 구조 |
| 2.1 | Gamma markets/events 커넥터 구현 | I-01 | 1.2 | Data Engineer | rate-limit/backoff 지원 수집기 |
| 2.2 | Subgraph GraphQL 커넥터/쿼리 템플릿 구현 | I-02 | 1.2 | Data Engineer | OI/activity/volume 조회기 |
| 2.3 | Market registry upsert + 변경이력 테이블 | I-03 | 2.1 | Data Engineer | registry 테이블 및 충돌 규칙 |
| 2.4 | ingest/normalize 단계 idempotent 처리 | I-19 | 2.1, 2.2, 2.3 | Platform Engineer | 재실행 안전 파이프라인 |
| 3.1 | 결과 라벨 상태 분류기 구현 | I-05 | 2.3 | Quant Engineer | RESOLVED_TRUE/FALSE/VOID/UNRESOLVED |
| 3.2 | cutoff snapshot 생성 규칙(T-24h/T-1h/Daily) 구현 | I-06 | 3.1 | Quant Engineer | cutoff 테이블 |
| 3.3 | feature builder(returns/vol/velocity/oi/tte) 구현 | I-07 | 3.2, 2.2 | Quant Engineer | feature frame parquet |
| 3.4 | snapshots/features 단계 파이프라인 통합 | I-19 | 3.2, 3.3 | Platform Engineer | 운영 배치 작업 |
| 4.1 | EWMA/Kalman/Rolling Quantile 밴드 구현 | I-08 | 3.3 | ML Engineer | baseline forecast band |
| 4.2 | TSFM 추상 인터페이스/타입 정의 | I-09 | 3.3 | ML Engineer | runner base, config schema |
| 4.3 | Conformal 보정 모듈/coverage 리포트 | I-10 | 4.1 또는 4.2, 3.1 | ML Engineer | 보정 밴드 및 커버리지 결과 |
| 5.1 | Question quality JSON 스키마 강제 에이전트 | I-11 | 2.3 | LLM Engineer | 구조화 점수 산출기 |
| 5.2 | LLM cache/client(해시키, seed/temperature 고정) | I-12 | 5.1 | LLM Engineer | SQLite 캐시 및 무결성 테스트 |
| 5.3 | Calibration engine(Brier/LogLoss/ECE/segment) | I-13 | 3.1, 3.2, 3.3, 5.1 | Quant Engineer | metrics table + reliability data |
| 5.4 | Trust score 산식 v1 + components 로그 | I-14 | 3.3, 5.1, 5.3 | Quant Engineer | trust score table |
| 5.5 | publish 단계(scoreboard/markdown) 완성 | I-19 | 5.3, 5.4 | Platform Engineer | MVP-1 배치 산출물 |
| 6.1 | WebSocket market ingest/reconnect/heartbeat | I-16 | 2.3 | Backend Engineer | WS ingestor |
| 6.2 | 1m/5m 집계(OHLC/거래수/실현변동성) | I-16 | 6.1 | Backend Engineer | stream aggregate 테이블 |
| 6.3 | Alert engine(3-gate + severity) 구현 | I-15 | 4.3, 5.4, 6.2, 5.1 | Backend Engineer | alert_event 생성기 |
| 6.4 | 설명 5줄 생성기(evidence-grounded) | I-17 | 6.3, 5.2 | LLM Engineer | 5줄 근거 요약 |
| 7.1 | Post-mortem markdown 자동 생성 | I-18 | 6.3, 6.4, 5.3 | Backend Engineer | 사건별 리포트 파일 |
| 7.2 | Scoreboard/Alerts/Reports 조회 API 또는 CLI | I-20 | 5.5, 7.1 | Backend Engineer | 읽기전용 조회 인터페이스 |
| 7.3 | 통합 운영 검증/런북/릴리즈 | (횡단) | 전 단계 | QA/SRE | 운영 체크리스트, 장애 대응 문서 |

## 4. 의존성(Dependencies) 및 임계경로
### 4.1 핵심 의존성 체인
1. 데이터 체인: I-01 -> I-03 -> I-06 -> I-07 -> I-13 -> I-14
2. 모델 체인: I-07 -> I-08/I-09 -> I-10 -> I-15
3. LLM 체인: I-11 -> I-12 -> I-14/I-17
4. 실시간 체인: I-16 -> I-15 -> I-17 -> I-18
5. 운영 체인: I-19가 Sprint 1~4 모든 단계를 관통

### 4.2 블로커 우선순위
| 블로커 | 영향 | 완화 계획 |
|---|---|---|
| I-03 지연(registry 불안정) | snapshot/feature/WS 구독 전부 지연 | Sprint 1 내 schema freeze, 충돌 규칙 조기 확정 |
| I-05 라벨 오염 | calibration/score 신뢰도 하락 | VOID/UNRESOLVED 분리 테스트를 배치 게이트로 승격 |
| I-10 coverage 미달 | alert 품질 저하(오탐 증가) | baseline fallback 유지, 재학습 트리거 명시 |
| I-12 캐시 불일치 | LLM 점수 재현성 붕괴 | 해시키/파라미터 고정 테스트를 배포 차단 조건화 |
| I-16 스트림 품질 불안정 | MVP-2 지연 | 배치 fallback 알림 모드를 병행 운용 |

## 5. DoD (Definition of Done)
### 5.1 공통 DoD
- 모든 모듈은 입력/출력 스키마가 문서 또는 코드(pydantic/dataclass)로 고정되어 있다.
- 단위테스트와 최소 1개 통합테스트가 CI에서 통과한다.
- 재실행 시 결과가 동일해야 하는 단계는 결정론 설정(seed/version/config)이 명시되어 있다.
- 파이프라인 단계는 idempotent하며 실패 지점 재시작이 가능하다.
- 주요 테이블(raw/registry/snapshot/features/metrics/alerts)에 대한 데이터 품질 체크가 존재한다.
- 운영 로그에 run_id, 데이터 기간, 모델/프롬프트 버전이 남는다.

### 5.2 스프린트별 Exit DoD
| Sprint | Exit DoD |
|---|---|
| Sprint 0 | 샘플 1일치 데이터로 discover->publish dry-run, 실패 시 체크포인트 재개 확인 |
| Sprint 1 | 활성 시장 기준 Gamma/Subgraph 수집 성공, raw/derived 파티션 자동 생성 |
| Sprint 2 | 상태 라벨 분리 정확도 기준 충족, cutoff/feature 테이블 일관성 검증 통과 |
| Sprint 3 | 밴드 q10/q50/q90 산출 + 커버리지 리포트 생성, baseline 교체 가능 인터페이스 확인 |
| Sprint 4 | Brier/LogLoss/ECE + 세그먼트 리포트 생성, trust score 구성요소 로그 저장, MVP-1 배치 성공률 목표 충족 |
| Sprint 5 | 1~5분 집계와 알림 생성 연결, HIGH/MED/FYI 분류와 근거 필드 저장, 설명 5줄 정책 준수 |
| Sprint 6 | post-mortem 자동 생성 결정론 확인, Scoreboard/Alerts/Reports 조회 기능 운영 가능 |

## 6. 첫 주(Week 1) 실행 체크리스트
- [ ] 킥오프: PRD 범위 고정(MVP-1 P0 우선), 역할/책임 매트릭스 확정
- [ ] 데이터 계약: `market_registry`, `market_snapshot`, `question_quality`, `forecast_band`, `alert_event` 스키마 잠금
- [ ] 저장 규칙: raw JSONL, derived parquet, `dt=YYYY-MM-DD` 파티션 규칙 문서화
- [ ] 개발 표준: 코드 스타일, 예외 계층, 로깅 필드(run_id/market_id/stage) 정의
- [ ] CI 기본선: lint/test/type-check 파이프라인 구축
- [ ] I-01/I-02 POC: 샘플 기간 수집 및 재시도/백오프 동작 검증
- [ ] I-03 POC: registry upsert + slug 변경 이력 반영 확인
- [ ] I-19 골격: discover->ingest->normalize 단계 연결, 실패 복구 포인트 확인
- [ ] 리스크 리뷰: 라벨 오염, 식별자 충돌, API rate-limit 대응안 승인
- [ ] 주간 데모: "샘플 시장 1건의 raw->registry->snapshot 흐름" 시연 완료

## 7. 역할별 병렬화 레인(Parallelizable Lanes)
| 역할 | 병렬 레인(주요 작업) | 선행 입력 | 산출물/핸드오프 |
|---|---|---|---|
| Data Engineer | I-01, I-02, I-03, I-04 | PRD 스키마 정의 | raw 적재기, registry, normalized snapshot 초안 |
| Platform Engineer | I-19(전 단계 오케스트레이션), 배포 파이프라인 | Data/ML/LLM 모듈 인터페이스 | idempotent 배치 잡, 체크포인트/재시도 운영 |
| Quant/ML Engineer | I-05, I-06, I-07, I-08, I-09, I-10, I-13, I-14 | registry + snapshot + features | calibration metrics, trust score, band 보정 |
| LLM Engineer | I-11, I-12, I-17 | market text, alert evidence | question quality JSON, 캐시 계층, 설명 5줄 |
| Backend Engineer | I-16, I-15, I-18, I-20 | trust score, band, quality score, stream agg | alert feed, post-mortem, 조회 API/CLI |
| QA/SRE | 통합 테스트, 데이터 품질 게이트, 운영 관측성 | 각 레인 산출물 | 품질 리포트, 릴리즈 승인/차단 기준 |
| PM/Domain Analyst | 임계치/세그먼트 정책, 라벨 샘플 검증, AC 승인 | 리포트/메트릭 초안 | 정책 확정본, 우선순위 조정안 |

## 8. 병렬 실행 규칙 (실무 적용)
1. `Lane A (Data Foundation)`와 `Lane C (LLM Quality)`는 Sprint 1부터 동시 진행한다.
2. `Lane B (Modeling/Calibration)`은 Sprint 2에서 `snapshot/features` 안정화 직후 시작한다.
3. `Lane D (Realtime/Alert)`는 Sprint 5에 시작하되, I-16과 I-15는 분리 팀이 병렬 개발 후 contract test로 결합한다.
4. 각 Sprint 말에는 contract test(스키마/필수 필드/버전)를 통과해야 다음 레인으로 핸드오프한다.
