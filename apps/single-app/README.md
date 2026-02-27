# single-app (최소 스캐폴드)

Market-Calibration-Agent 레포 내부에서 **기존 코드 변경 없이** 추가된 Next.js + API + Worker + Prisma 최소 동작본입니다.

## 포함 구성

- Next.js(TypeScript, App Router) 기본 UI
- API Routes
  - `GET /api/health`
  - `GET /api/markets` (실데이터 프록시 + fallback)
  - `POST /api/execution/start` (관리자 인증 + BullMQ enqueue)
  - `POST /api/execution/stop` (관리자 인증 + kill-switch ON/OFF)
  - `GET /api/execution/stop` (kill-switch 상태 조회)
- Worker 엔트리: `src/worker/index.ts` (Redis/BullMQ consumer)
- Queue 구성: `src/queue/*` (producer, queue config, smoke script)
- Prisma schema: `orders`, `positions`, `calibration_runs`
- Dockerfile + docker-compose (app + worker + postgres + redis)

## 빠른 시작 (로컬)

```bash
cd apps/single-app
cp .env.example .env
npm install
npm run db:generate

# Postgres 준비 후 정식 migration 적용
npm run db:migrate -- --name init

# 샘플 데이터 seed
npm run db:seed

# 앱 실행
npm run dev

# 별도 터미널에서 워커 실행
npm run worker

# (옵션) 큐 스모크 적재
npm run queue:smoke -- paper
```

## /api/markets 데이터 소스 설정

`/api/markets`는 레포의 기존 FastAPI(`api/app.py`) `GET /markets`를 기본 업스트림으로 사용합니다.

환경변수:

- `ADMIN_API_TOKEN` (**필수**; `POST /api/execution/start`, `POST /api/execution/stop` Bearer 인증)
- `MARKETS_SOURCE_BASE_URL` (default: `http://127.0.0.1:8100`)
- `MARKETS_SOURCE_PATH` (default: `/markets`)
- `MARKETS_SOURCE_TIMEOUT_MS` (default: `5000`)

실패 정책:

- 업스트림 타임아웃/연결실패/비정상 HTTP 응답 시에도 API 자체는 JSON 응답을 유지
- 응답 본문에 `error.code`, `error.message` 포함
- `items`는 빈 배열(`[]`)로 반환

## API 테스트

```bash
export ADMIN_API_TOKEN='change-me-admin-token'

curl http://localhost:3000/api/health
curl http://localhost:3000/api/markets

# 실행 시작 (관리자 토큰 필요)
curl -X POST http://localhost:3000/api/execution/start \
  -H "authorization: Bearer ${ADMIN_API_TOKEN}" \
  -H 'content-type: application/json' \
  -d '{"mode":"paper","dryRun":true,"maxPosition":1000000}'

# kill-switch ON (기본 enabled=true)
curl -X POST http://localhost:3000/api/execution/stop \
  -H "authorization: Bearer ${ADMIN_API_TOKEN}" \
  -H 'content-type: application/json' \
  -d '{"reason":"incident 대응"}'

# kill-switch OFF
curl -X POST http://localhost:3000/api/execution/stop \
  -H "authorization: Bearer ${ADMIN_API_TOKEN}" \
  -H 'content-type: application/json' \
  -d '{"enabled":false,"reason":"정상화"}'

# kill-switch 상태 조회
curl http://localhost:3000/api/execution/stop
```

`/api/health` 응답 예시 (DB 연결 정상):

```json
{
  "ok": true,
  "service": "single-app",
  "now": "2026-02-27T10:00:00.000Z",
  "db": { "ok": true }
}
```

DB 연결 실패 시 HTTP 503과 함께 `db.ok=false`를 반환합니다.

`POST /api/execution/start` 요청 스펙:

- `mode`: `paper | live | mock` (기본값 `mock`)
- `dryRun`: `boolean` (기본값 `true`)
- `maxPosition`: `number` (기본값 `1000000`)
- `notes`: `string` (선택)

기본 호출은 큐 등록 후 즉시 반환하며, `state`는 `queued`입니다.

`POST /api/execution/start` 응답 예시:

```json
{
  "ok": true,
  "runId": "uuid",
  "jobId": "1",
  "state": "queued",
  "queue": "execution_start",
  "params": {
    "mode": "paper",
    "dryRun": true,
    "maxPosition": 1000000
  }
}
```

검증 규칙:

- `mode`/`dryRun`/`maxPosition`/`notes`는 `zod` 스키마를 통해 검증
- 잘못된 요청은 `400` + `fieldErrors`를 반환

인증/상태 코드 계약:

- `401`: Authorization 헤더 누락 또는 Bearer 형식 오류
- `403`: Bearer 토큰 불일치
- `409`: 실행 차단
  - `KILL_SWITCH_ON`: kill-switch ON으로 차단
  - `RISK_LIMIT_EXCEEDED`: 일일 손실 한도(`RISK_MAX_DAILY_LOSS`) 초과
  - `ORDER_RATE_LIMIT_EXCEEDED`: 최근 1분 주문수 한도(`ORDER_RATE_LIMIT_PER_MIN`) 초과
- `503`: 서버 설정 문제(`ADMIN_API_TOKEN` 미설정) 또는 enqueue/인프라 실패 (`ENQUEUE_FAILED`)

`POST /api/execution/stop` 요청 스펙:

- `enabled`: `boolean` (기본값 `true`, 즉 stop 호출 기본 동작은 kill-switch ON)
- `reason`: `string` (선택, 최대 500자)

`GET /api/execution/stop`은 현재 kill-switch 상태(`enabled`, `reason`, `updatedAt`)를 반환합니다.

기본 재시도 정책(BullMQ defaultJobOptions):

- `attempts: 3`
- `backoff: { type: "exponential", delay: 1000 }`

## 운영 준비 1단계 검증 절차

```bash
# 1) migration 적용
npm run db:migrate -- --name init

# 2) seed 적용
npm run db:seed

# 3) 앱 기동 후 health 확인
npm run dev
curl -i http://localhost:3000/api/health
```

## Docker Compose

```bash
cd apps/single-app
docker compose up --build
```

## 스크립트

- `npm run dev` - Next 개발 서버
- `npm run build` - 프로덕션 빌드
- `npm run start` - 빌드 결과 실행
- `npm run worker` - BullMQ worker 실행
- `npm run dev:worker` - worker watch 모드
- `npm run queue:smoke -- <mode>` - 큐 적재 스모크
- `npm run typecheck` - 타입체크
- `npm run db:generate` - Prisma Client 생성
- `npm run db:migrate` - Prisma migration(dev)
- `npm run db:push` - 스키마 반영(개발용)
- `npm run db:seed` - 최소 샘플 데이터 입력
- `npm run db:studio` - Prisma Studio
- `npm run smoke:ci` - 운영 one-shot smoke (docker postgres/redis + migrate + API 시나리오)
- `scripts/admin_token_rotate.sh` - ADMIN_API_TOKEN 생성/로테이션 + .env 반영

## CI/로컬 one-shot Smoke

운영 검증 시나리오를 한 번에 실행합니다.

전제조건:
- Docker + Docker Compose 사용 가능
- Node.js/npm 설치
- `apps/single-app` 의존성 설치 완료 (`npm install`)
- 3000 포트 사용 가능

실행:

```bash
cd apps/single-app
npm run smoke:ci
```

스크립트가 자동으로 수행하는 단계:
1. `docker compose up -d postgres redis` (기존 컨테이너 재사용)
2. `prisma migrate deploy` 실행
3. `ADMIN_API_TOKEN` 확인 (없으면 임시 토큰 생성, 로그는 마스킹 출력)
4. `npm run dev` 백그라운드 실행 후 `/api/health` 대기
5. API 시나리오 검증
   - a) `GET /api/health` → `200`, `db.ok=true`
   - b) `POST /api/execution/start` (무토큰) → `401/403`
   - c) `POST /api/execution/start` (토큰) → `202`
   - d) `POST /api/execution/stop` `enabled=true` → `200`
   - e) `POST /api/execution/start` (재시도) → `409`
   - f) `POST /api/execution/stop` `enabled=false` → `200`

예상 출력 예시:

```text
[PASS] Postgres ready
[PASS] Redis ready
[PASS] DB migrate
[PASS] Dev server ready
[PASS] a) health 200 + db.ok=true
[PASS] b) start without token => 401
[PASS] c) start with token => 202
[PASS] d) stop enabled=true => 200
[PASS] e) start again => 409
[PASS] f) stop enabled=false => 200
[RESULT] Smoke test PASSED (... checks)
```

## Go-Live Checklist (실거래 직전)

아래는 **운영 체크리스트 + 리스크 가드레일** 기준입니다. 각 항목은 현재 코드 기준으로
- ✅ 구현됨 (즉시 적용 가능)
- ⚠️ 부분 구현 (수동 보완 필요)
- ❌ 미구현 (실거래 전 필수 보강)
으로 구분했습니다.

### 1) Dry-run 검증

- ✅ `POST /api/execution/start` 기본값이 `dryRun=true`
- ✅ Worker에서 `dryRun=true`이면 실제 파이프라인 실행 없이 `DRY_RUN_DONE` 처리
- 운영 확인:
  - `curl -X POST /api/execution/start ...` 호출 후 DB `calibration_runs.status=DRY_RUN_DONE` 확인

### 2) Max Position / Loss / Order Rate 가드레일

- ✅ **Max Position(요청 단위)**: API 입력 `maxPosition` 검증(zod)
- ✅ **Max Position(인프라 상한)**: `MAX_POSITION_LIMIT` 초과 시 Worker 실패 처리
- ✅ **Max Loss(손실 한도)**: `orders.realizedPnl` 기준 당일 음수 손익 절대값 합계를 계산해 차단
  - 기준식: `abs(sum(realizedPnl where realizedPnl < 0 and createdAt in today)) >= RISK_MAX_DAILY_LOSS`
- ✅ **Order Rate(주문 속도 제한)**: 최근 1분 `orders.createdAt` 건수로 차단
  - 기준식: `count(orders where createdAt >= now-60s) >= ORDER_RATE_LIMIT_PER_MIN`
- ✅ **우회 방지 이중 가드**: Producer(`enqueueExecutionStart`) + Worker(잡 실행 직전) 모두 검사

권장 기본값은 `.env.example`의 `RISK_*`, `ORDER_RATE_*` 항목 참고.

### 3) Alerting

- ✅ 공통 이벤트 로거/노티파이어(`src/lib/ops-events.ts`) 추가
- ✅ `ALERT_WEBHOOK_URL` 설정 시 critical 이벤트를 웹훅으로 POST 전송
- ✅ 이벤트 공통 필드: `runId`, `jobId`, `reason` (+ `event`, `severity`, `at`, `details`)
- ⚠️ Slack/Email/Pager 직접 연동은 미구현 (웹훅 downstream에서 라우팅 권장)

현재 전송 이벤트:
- `execution_start_blocked` (API/producer/worker에서 실행 시작 차단)
- `worker_failed`
- `retry_exhausted`
- `kill_switch_on`
- `kill_switch_off`

### 4) Rollback

- ⚠️ API enqueue 실패 시 `calibration_runs` 생성 레코드 삭제(부분 롤백) 구현
- ❌ 실주문 롤백(취소/헷지/상태 복구) 플레이북 및 자동화 미구현

### 5) Secret 관리

- ⚠️ `.env` 기반 주입은 가능하나, KMS/Vault/Secret Manager 연동 없음
- ❌ 시크릿 로테이션/만료 정책/감사 추적 미구현

### 6) 권한 분리 (RBAC / 접근 통제)

- ⚠️ `ADMIN_API_TOKEN` 단일 Bearer 토큰 기반 관리자 인증은 구현됨
  - 적용 대상: `POST /api/execution/start`, `POST /api/execution/stop`
  - 실패 코드: `401`(헤더 누락/형식 오류), `403`(토큰 불일치), `503`(서버 토큰 미설정)
- ❌ 운영자/관찰자 등 역할 기반 권한 분리(RBAC) 및 세분화된 인가 정책은 미구현

### Go/No-Go 최소 기준 (권장)

실거래 전 최소한 아래 6개 조건 충족 권장:
1. Dry-run 시나리오 3회 이상 성공 + 예상 로그/상태 검증
2. Max Position/Loss/Order Rate 모두 코드 레벨 하드가드 적용
3. 실패 알림(Webhook/Slack 등) + 온콜 수신 확인
4. 롤백 런북(수동 절차) + 자동화 가능한 범위 정의
5. 시크릿 외부 저장소 연동 및 로테이션 정책 문서화
6. 단일 토큰 인증을 역할 기반 접근통제(RBAC)로 고도화(운영자/관찰자 권한 분리)

## 운영 Runbook (토큰/Compose/Canary/Alerting)

상세 절차는 루트 문서 [`docs/ops/single-app-ops-runbook.md`](../../docs/ops/single-app-ops-runbook.md)를 기준으로 운영합니다.

핵심 요약:

1. **Compose 경고 제거 기준**: `docker-compose.yml`에 `version:` 키를 두지 않습니다.
2. **ADMIN 토큰 로테이션**:
   ```bash
   cd apps/single-app
   scripts/admin_token_rotate.sh --env-file .env
   ADMIN_API_TOKEN="$ADMIN_API_TOKEN" npm run smoke:ci
   ```
3. **dryRun=false 안전 카나리**(실주문 없이 파이프라인 경로 확인):
   ```bash
   export CALIBRATION_ENTRYPOINT_MODULE="pipelines.noop_calibration_entrypoint"
   curl -X POST http://127.0.0.1:3000/api/execution/start \
     -H "authorization: Bearer ${ADMIN_API_TOKEN}" \
     -H 'content-type: application/json' \
     -d '{"mode":"mock","dryRun":false,"maxPosition":1000,"notes":"canary-noop"}'
   ```
   - 정식 체크리스트: [`single-app-ops-runbook.md`의 "4) 실거래 카나리 1회 체크리스트 (고정 파라미터)" 섹션](../../docs/ops/single-app-ops-runbook.md#4-실거래-카나리-1회-체크리스트-고정-파라미터)
   - 권장 고정값: `mode=mock`, `dryRun=false`, `maxPosition=1000`, `CALIBRATION_ENTRYPOINT_MODULE=pipelines.noop_calibration_entrypoint`
   - 중단 시 즉시 `POST /api/execution/stop` `enabled=true`로 kill-switch ON
4. **Alert 웹훅 연결**:
   ```bash
   # .env
   ALERT_WEBHOOK_URL="https://your-webhook.example/ops-alert"
   ```
   - 미설정 시: 이벤트는 `[ops-event]` 콘솔 로그로만 기록
   - 설정 시: critical 이벤트가 JSON으로 POST 전송

## TODO (다음 단계)

1. 실제 캘리브레이션 파이프라인(시장 조회/전략/주문)으로 worker 로직 치환
2. 인증/권한, 로깅/모니터링(OTel/메트릭) 강화
3. dead-letter queue 및 운영 대시보드 추가
4. 실주문 체결 데이터 연동 시 `orders.realizedPnl` 정확도/집계정합성 검증 자동화
5. Alerting 다중 채널(Slack/Pager 직접 연동) + Rollback 런북 자동화

## 작업 노트

### 변경 파일

- `apps/single-app/src/lib/admin-auth.ts`
  - `ADMIN_API_TOKEN` 기반 Bearer 인증 헬퍼 추가 (`401/403/503` 응답 분리)
- `apps/single-app/src/lib/kill-switch.ts`
  - kill-switch 상태 관리 유틸 추가 (DB upsert + 메모리 캐시)
- `apps/single-app/src/lib/ops-events.ts`
  - 공통 이벤트 로거/노티파이어 유틸 추가 (`runId`, `jobId`, `reason` 포함)
  - `ALERT_WEBHOOK_URL` 설정 시 critical 이벤트 웹훅 전송
- `apps/single-app/app/api/execution/start/route.ts`
  - 관리자 인증 강제
  - kill-switch ON 시 `409` 반환 후 enqueue 차단 + `execution_start_blocked` 이벤트 발행
- `apps/single-app/app/api/execution/stop/route.ts` (신규)
  - `POST`: kill-switch ON/OFF 제어 (`enabled` 기본 `true`)
  - `GET`: kill-switch 상태 조회
  - 동일 상태 재요청 시 `409`
  - ON/OFF 시 `kill_switch_on`, `kill_switch_off` 이벤트 발행
- `apps/single-app/src/queue/producer.ts`
  - enqueue 직전 kill-switch 상태 재검증 (우회 호출 방지)
  - 차단 시 `execution_start_blocked` 이벤트 발행
- `apps/single-app/src/worker/index.ts`
  - job 처리 시작 전 kill-switch 상태 확인 후 실행 차단
  - 실패 시 `worker_failed`, 재시도 소진 시 `retry_exhausted` 이벤트 발행
- `apps/single-app/prisma/schema.prisma`
  - `ExecutionControl` 모델 추가
- `apps/single-app/prisma/migrations/20260227195500_add_execution_control/migration.sql` (신규)
  - `execution_controls` 테이블 생성
- `apps/single-app/.env.example`
  - `ADMIN_API_TOKEN` 추가

### 실행 명령 (최소 스모크)

```bash
cd apps/single-app
npm install
npm run db:migrate -- --name init
npm run db:seed
npm run dev
```

다른 터미널:

```bash
cd apps/single-app
npm run worker
```

요청 예시:

```bash
curl -X POST http://localhost:3000/api/execution/start \
  -H 'content-type: application/json' \
  -d '{"mode":"mock","dryRun":true,"maxPosition":1000000}'
```

큐 스모크:

```bash
npm run queue:smoke -- paper
```

### 제약

- `dryRun=true` 기본 동작은 파이프라인 실제 실행을 생략하고 상태는 `DRY_RUN_DONE`으로 종료됩니다.
- 현재 실행진입점은 `pipelines.daily_job.run_daily_job`입니다. `runners/features/calibration` 모듈 경로는 현재 저장소에 없어 fallback 동작합니다.
- `MAX_POSITION_LIMIT` 미설정 시 기본값은 `1000000`입니다.
- 파이프라인 실행이 Python으로 실제 진입할 때는 `CALIBRATION_PYTHON_BIN`, `CALIBRATION_PYTHON_TIMEOUT_MS`, `CALIBRATION_ENTRYPOINT_MODULE`(선택)을 함께 활용할 수 있습니다.
