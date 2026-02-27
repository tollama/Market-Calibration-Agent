# 원본 MCA → single-app 피처 이관 템플릿 (v1.1)

> 목적: 기존 MCA(파이썬 중심 모듈) 기능을 `apps/single-app`으로 안전하게 이관할 때, 누락 없이 동일한 운영 품질로 전환하기 위한 표준 템플릿.
>
> 관련 문서: [Feature Specs v1.1 (컬럼 스키마/백테스트/Go·No-Go, `liquidity_bucket` 포함)](./feature-specs-v1.md)
>
> 표준 고정 규칙(유동성): `liquidity_bucket = bucket(max(volume_24h, open_interest), low=10_000, high=100_000)` / `liquidity_bucket_id={LOW:0,MID:1,HIGH:2}`

## 1) 목적 / 적용 범위

### 목적
- 원본 기능(수집/가공/의사결정/API)을 single-app 경계에서 재현
- 기능 이관 시 데이터 계약, 리스크 가드, 알림, 롤백 가능성까지 함께 보장
- “구현 완료”가 아니라 “운영 가능(관측/중단/복구 가능)” 상태를 목표로 함

### 적용 범위
- 대상 레포: `Market-Calibration-Agent`
- 원본 코드(legacy): `api/`, `pipelines/`, `connectors/`, `features/`, `calibration/`, `agents/`, `runners/`
- 이관 대상(single-app): `apps/single-app/app/api/`, `apps/single-app/src/lib/`, `apps/single-app/src/queue/`, `apps/single-app/src/worker/`, `apps/single-app/prisma/`
- 운영 문서: `docs/ops/single-app-ops-runbook.md`

---

## 2) 단계별 이관 체크리스트 (연구 → 검증 → 이관 → 카나리 → 운영)

## A. 연구(Research)
- [ ] 원본 기능의 **진입점/의존성/출력물** 식별
  - 예: `pipelines/daily_job.py`, `api/app.py`, `features/build_features.py`
- [ ] 기능의 입력 계약(요청 파라미터, config, env) 목록화
- [ ] 기능의 출력 계약(JSON/파일/DB/로그/이벤트) 목록화
- [ ] 실패 모드(타임아웃, 외부 API 실패, 데이터 누락, 재시도 고갈) 정리
- [ ] 운영 제약(인증, rate-limit, kill-switch, 알림) 존재 여부 확인

산출물(권장):
- `입력/출력 계약 표`
- `실패 모드 표`
- `이관 우선순위(필수/후순위)`

## B. 검증(Validation)
- [ ] 원본 동작의 기준 샘플 확보(동일 입력에 대한 기준 응답/상태)
- [ ] single-app에서 목표 동작의 **수용 기준(acceptance criteria)** 정의
- [ ] 스키마 차이(필드명, 타입, nullable, enum) diff 작성
- [ ] 로컬 재현 절차(명령어, seed 데이터, env) 문서화
- [ ] 최소 smoke 시나리오 작성 (`npm run smoke:ci` 포함)

## C. 이관(Migration)
- [ ] API 계층 이관 (`apps/single-app/app/api/**/route.ts`)
- [ ] 도메인 로직 이관 (`apps/single-app/src/lib/*.ts`)
- [ ] 비동기 실행 경로 이관 (`apps/single-app/src/queue/*`, `src/worker/index.ts`)
- [ ] DB 모델 반영 (`apps/single-app/prisma/schema.prisma` + migration)
- [ ] 에러 코드/응답 계약 정합성 확인(HTTP status + code)
- [ ] feature flag 또는 안전 기본값 적용(`dryRun=true`, 보수적 limit)

## D. 카나리(Canary)
- [ ] 사전 조건 확인: `/api/health` OK, DB 연결 OK, worker 기동
- [ ] `ADMIN_API_TOKEN` 반영 상태 확인(app/worker 동일)
- [ ] kill-switch OFF 확인 후 카나리 1회 실행
- [ ] 권장 고정 파라미터 사용(예: `mode=mock`, `dryRun=false`, `maxPosition=1000`)
- [ ] 이상 징후 발생 시 즉시 kill-switch ON
- [ ] 카나리 기록(시각/담당자/runId/결과/후속조치) 남김

## E. 운영(Operation)
- [ ] 알림 채널(`ALERT_WEBHOOK_URL`) 연결 확인
- [ ] 재시도 고갈/실패 이벤트 모니터링 설정
- [ ] 토큰 로테이션 절차 적용 (`scripts/admin_token_rotate.sh`)
- [ ] 정기 smoke 실행(배포 후/토큰 로테이션 후)
- [ ] 롤백 플레이북 최신화 및 담당자 공유

---

## 3) 코드 삽입 포인트 매핑 (원본 repo vs single-app)

| 기능 영역 | 원본 MCA 위치(legacy) | single-app 삽입 위치 | 구현 메모 |
|---|---|---|---|
| 헬스/기본 API | `api/app.py` | `apps/single-app/app/api/health/route.ts` | 서비스/DB 상태 계약 정렬 |
| 마켓 조회 API | `api/app.py` + `connectors/polymarket_gamma.py` | `apps/single-app/app/api/markets/route.ts`, `apps/single-app/src/lib/markets-source.ts` | 업스트림 실패 시 fallback 정책 유지 |
| 실행 시작 API | `api/app.py`(운영 API 성격) | `apps/single-app/app/api/execution/start/route.ts` | 인증 + 리스크 가드 + enqueue |
| 실행 중단/차단 | (legacy 산발 로직/운영 스크립트) | `apps/single-app/app/api/execution/stop/route.ts`, `apps/single-app/src/lib/kill-switch.ts` | kill-switch 상태 저장/조회 표준화 |
| 리스크 가드 | `configs/*`, `pipelines/*` 내부 검증 | `apps/single-app/src/lib/risk-guard.ts` | API/worker 이중 가드 적용 |
| 알림 이벤트 | `agents/alert_agent.py`, 운영 스크립트 | `apps/single-app/src/lib/ops-events.ts` | critical 이벤트 웹훅 전송 |
| 배치/실행 파이프라인 | `pipelines/daily_job.py`, `pipelines/realtime_ws_job.py` | `apps/single-app/src/worker/index.ts` (+ Python entrypoint 호출) | `CALIBRATION_ENTRYPOINT_MODULE`로 점진 이관 |
| 큐잉 | (legacy 스케줄/직접 실행) | `apps/single-app/src/queue/producer.ts`, `executionQueue.ts`, `config.ts` | 재시도/백오프 정책 고정 |
| 데이터 모델 | 파일 기반 산출물 + 스키마(`schemas/`, `storage/`) | `apps/single-app/prisma/schema.prisma`, `apps/single-app/prisma/migrations/*` | 최소 운영 엔티티부터 단계적 확장 |
| 운영 스모크 | `scripts/openapi_smoke.py`, `scripts/prd2_verify_all.sh` | `apps/single-app/scripts/ci_smoke.sh`, `npm run smoke:ci` | single-app 관점 one-shot 검증 |

> 사용법: 기능 이관 시 위 표의 “행 단위”로 PR을 쪼개면 리뷰/롤백이 쉬워짐.

---

## 4) 데이터 계약 / 스키마 변경 템플릿

아래 블록을 복사해 PR 본문 또는 설계 노트에 채운다.

```md
## 데이터 계약 변경 템플릿

### 1. 변경 개요
- 기능명:
- 변경 유형: [신규 필드 추가 | 필드 타입 변경 | 필드 제거 | enum 변경 | 인덱스 변경]
- 영향 범위: [API 응답 | Worker payload | DB schema | 외부 연동]

### 2. Before / After
- Before 스키마:
- After 스키마:
- 호환성: [Backward Compatible | Breaking]

### 3. 마이그레이션 계획
- Prisma 변경 파일: `apps/single-app/prisma/schema.prisma`
- 마이그레이션 생성/적용:
  - `npm run db:migrate -- --name <migration_name>`
  - (배포) `prisma migrate deploy`
- 롤백 가능 여부:

### 4. 검증 포인트
- API 계약 테스트:
- DB 읽기/쓰기 테스트:
- Worker 처리 테스트:
- 대시보드/알림 필드 영향:

### 5. 위험요소 및 대응
- 예상 리스크:
- 완화책:
- 모니터링 지표/로그:
```

---

## 5) 리스크 / 알림 / kill-switch 연동 체크리스트

- [ ] `POST /api/execution/start` 호출 경로에 인증 강제(`ADMIN_API_TOKEN`)
- [ ] producer 단계에서 kill-switch ON 차단
- [ ] worker 단계에서 kill-switch ON 재검증(우회 방지)
- [ ] 손실/주문속도/포지션 제한 가드 적용 (`src/lib/risk-guard.ts`)
- [ ] 차단 시 표준 에러 코드 반환 (`KILL_SWITCH_ON`, `RISK_LIMIT_EXCEEDED`, `ORDER_RATE_LIMIT_EXCEEDED`)
- [ ] critical 이벤트 로깅 + 웹훅 전송 (`src/lib/ops-events.ts`, `ALERT_WEBHOOK_URL`)
- [ ] 재시도 고갈 이벤트(`retry_exhausted`) 알림 연결
- [ ] kill-switch ON/OFF 이력(reason, updatedAt) 추적 가능

---

## 6) 검증 명령어 템플릿 (smoke:ci, API curl, worker 로그)

### 6-1. one-shot smoke
```bash
cd apps/single-app
npm run smoke:ci
```

### 6-2. API 수동 검증(curl)
```bash
export ADMIN_API_TOKEN='<admin-token>'

# health
curl -i http://127.0.0.1:3000/api/health

# markets
curl -i http://127.0.0.1:3000/api/markets

# start (토큰 필수)
curl -i -X POST http://127.0.0.1:3000/api/execution/start \
  -H "authorization: Bearer ${ADMIN_API_TOKEN}" \
  -H 'content-type: application/json' \
  -d '{"mode":"mock","dryRun":true,"maxPosition":1000000}'

# kill-switch ON
curl -i -X POST http://127.0.0.1:3000/api/execution/stop \
  -H "authorization: Bearer ${ADMIN_API_TOKEN}" \
  -H 'content-type: application/json' \
  -d '{"enabled":true,"reason":"migration canary abort"}'

# kill-switch 상태
curl -i http://127.0.0.1:3000/api/execution/stop
```

### 6-3. worker 로그 확인 템플릿
```bash
cd apps/single-app
npm run worker
# 확인 포인트:
# - job accepted / completed
# - execution_start_blocked
# - worker_failed
# - retry_exhausted
```

---

## 7) 롤백 절차

### 롤백 트리거
- 카나리/운영 중 `5xx` 급증
- `worker_failed` 또는 `retry_exhausted` 급증
- 의도치 않은 실행(예: no-op 미적용, 리스크 가드 우회)
- 데이터 계약 불일치로 소비자 장애 발생

### 즉시 조치 (T+0)
1. 실행 차단
```bash
curl -X POST http://127.0.0.1:3000/api/execution/stop \
  -H "authorization: Bearer ${ADMIN_API_TOKEN}" \
  -H 'content-type: application/json' \
  -d '{"enabled":true,"reason":"rollback initiated"}'
```
2. 신규 배포/재시도 중지
3. 장애 시점 runId/jobId, 관련 로그 스냅샷 확보

### 기능 롤백 (T+5~)
1. 직전 안정 커밋/태그로 코드 롤백
2. 필요 시 DB 변경 롤백 또는 호환 패치 적용
3. app + worker 재기동 후 smoke 최소 세트 실행
4. kill-switch OFF는 정상 확인 후 수행

### 사후 조치
- 원인 분류: 코드/스키마/설정/외부 의존성
- 재발 방지 항목을 체크리스트에 반영
- 카나리 재진입 조건(명확한 pass 기준) 정의

---

## 8) 이관 작업 기록 템플릿 (복사용)

```md
## 피처 이관 기록
- 피처명:
- 담당자:
- 기간:
- 관련 PR:

### 1) 연구 결과 요약
- 

### 2) 구현 범위
- 

### 3) 검증 결과
- smoke:ci:
- API curl:
- worker 로그:

### 4) 리스크/알림/kill-switch 점검
- 

### 5) 롤백 계획/결과
- 
```
