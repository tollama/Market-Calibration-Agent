# single-app (최소 스캐폴드)

Market-Calibration-Agent 레포 내부에서 **기존 코드 변경 없이** 추가된 Next.js + API + Worker + Prisma 최소 동작본입니다.

## Advisory-only 정책 (고정)

본 앱은 **정보 제공 전용(advisory-only)** 서비스입니다.

- 투자 권유/중개/집행 서비스가 아닙니다.
- 법률·세무·회계 자문이 아닙니다.
- 규제 준수(관할 인허가/보고 의무 포함) 및 실제 투자/거래 의사결정은 사용자 및 운영 주체 책임입니다.
- 기본값으로 execution API는 비활성(`EXECUTION_API_ENABLED=false`)이며, 운영에서 명시적으로 `true` 설정 전까지 실행 경로를 차단합니다.

## 포함 구성

- Next.js(TypeScript, App Router) 기본 UI
- API Routes
  - `GET /api/health`
  - `GET /api/markets` (실데이터 프록시 + fallback + advisory disclaimer)
  - `POST /api/execution/start` (관리자 인증 + BullMQ enqueue, 단 기본 비활성)
  - `POST /api/execution/stop` (관리자 인증 + kill-switch ON/OFF, 단 기본 비활성)
  - `GET /api/execution/stop` (kill-switch 상태 + execution 활성화 여부 조회)
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
- `EXECUTION_API_ENABLED` (default: `false`, advisory-only 기본 정책. `true`일 때만 execution 관련 POST 허용)
- `MARKETS_SOURCE_BASE_URL` (default: `http://127.0.0.1:8100`)
- `MARKETS_SOURCE_PATH` (default: `/markets`)
- `MARKETS_SOURCE_TIMEOUT_MS` (default: `5000`)

실패 정책:

- 업스트림 타임아웃/연결실패/비정상 HTTP 응답 시에도 API 자체는 JSON 응답을 유지
- 응답 본문에 `error.code`, `error.message` 포함
- `items`는 빈 배열(`[]`)로 반환
- 성공/실패 모두 `disclaimer` 필드(advisory-only/비자문 고지) 포함
- 인증 실패(401/403), 서버 인증 설정 오류(503), 공통 에러 경로(예: `/api/health` DB 오류)에도 동일하게 disclaimer를 주입
- advisory 메타는 `advisory.scope`, `advisory.executionEnabled` 포맷으로 통일

## API 테스트

```bash
export ADMIN_API_TOKEN='change-me-admin-token'
# advisory-only 기본 정책: 실행 API 차단됨(403)
# 실행 경로 테스트가 꼭 필요할 때만 임시 override
export EXECUTION_API_ENABLED='true'

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
- `idempotency_key` 또는 `idempotencyKey`: `string` (선택, 최대 128자)
- `Idempotency-Key` 헤더: `string` (선택, body보다 우선)

기본 호출은 큐 등록 후 즉시 반환하며, `state`는 `queued`입니다.
동일 idempotency key로 재요청하면 중복 enqueue 없이 기존 `runId`를 재사용해 `200`(`replayed=true`)을 반환합니다.

`POST /api/execution/start` 신규 실행 응답 예시:

```json
{
  "ok": true,
  "runId": "uuid",
  "jobId": "1",
  "state": "queued",
  "queue": "execution_start",
  "idempotencyKey": "exec-20260227-001",
  "params": {
    "mode": "paper",
    "dryRun": true,
    "maxPosition": 1000000
  }
}
```

`POST /api/execution/start` 동일 key 재요청 응답 예시:

```json
{
  "ok": true,
  "runId": "동일한 기존 runId",
  "state": "queued",
  "replayed": true,
  "idempotencyKey": "exec-20260227-001"
}
```

검증 규칙:

- `mode`/`dryRun`/`maxPosition`/`notes`는 `zod` 스키마를 통해 검증
- 잘못된 요청은 `400` + `fieldErrors`를 반환

인증/상태 코드 계약:

- 아래 실패 응답(401/403/409/503 포함)은 모두 공통적으로 `disclaimer` + `advisory { scope, executionEnabled }`를 포함

- `200`: idempotency replay 응답 (`replayed=true`, 기존 runId 반환)
- `202`: 신규 실행 요청 accepted (큐 등록 완료)
- `400`: 요청 바디 검증 실패 (`idempotencyKey` 길이 초과/빈 문자열 포함)
- `401`: Authorization 헤더 누락 또는 Bearer 형식 오류
- `403`: Bearer 토큰 불일치
- `403`: 실행 정책 차단
  - `EXECUTION_DISABLED`: advisory-only 기본 정책(`EXECUTION_API_ENABLED=false`)으로 차단
- `409`: 실행 차단
  - `KILL_SWITCH_ON`: kill-switch ON으로 차단
  - `RISK_LIMIT_EXCEEDED`: 일일 손실 한도(`RISK_MAX_DAILY_LOSS`) 초과
  - `ORDER_RATE_LIMIT_EXCEEDED`: 최근 1분 주문수 한도(`ORDER_RATE_LIMIT_PER_MIN`) 초과
- `503`: 서버 설정 문제(`ADMIN_API_TOKEN` 미설정) 또는 enqueue/인프라 실패 (`ENQUEUE_FAILED`)

`POST /api/execution/stop` 요청 스펙:

- `enabled`: `boolean` (기본값 `true`, 즉 stop 호출 기본 동작은 kill-switch ON)
- `reason`: `string` (선택, 최대 500자)

`GET /api/execution/stop`은 현재 kill-switch 상태(`enabled`, `reason`, `updatedAt`)를 반환합니다.

### 표현 가드(콘텐츠 안전)

서버 측 유틸 `src/lib/advisory-policy.ts`를 통해 직접 거래 권유 문구를 치환합니다.

- 예: `지금 매수`, `지금 매도`, `buy now`, `sell now` 등
- 치환 문구: `직접 거래 지시 문구는 제공하지 않습니다. 판단은 사용자 책임입니다.`
- 현재 적용 지점:
  - `GET /api/markets` 오류 메시지
  - `POST /api/execution/start` 오류 메시지

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
- `npm run test:auto-killswitch` - auto kill-switch 규칙 단위 테스트(연속 실패/손실/지연)
- `npm run test:e2e:order-sm` - 상태머신+queue/worker 통합 E2E (start API → PENDING → FILLED + 불법 전이 ops-event)
- `npm run test:e2e:order-sm:local` - 로컬 one-shot 실행(도커 postgres/redis 기동 + prisma db push + E2E)
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
   - c) idempotency 검증
     - c-1) `POST /api/execution/start` (토큰 + idempotency key) → `202`
     - c-2) 동일 요청 재호출 → `200` + `replayed=true`
     - c-3) 두 응답의 `runId` 동일
     - c-4) DB `calibration_runs.idempotencyKey` 기준 row count = `1`
   - d) `POST /api/execution/stop` `enabled=true` → `200`
   - e) `POST /api/execution/start` (재시도) → `409`
   - f) `POST /api/execution/stop` `enabled=false` → `200`

예상 출력 예시:

## Order 상태머신 통합 E2E

`src/lib/order-state-machine.e2e.test.ts`

검증 범위:
1. `POST /api/execution/start` 요청 시 `orders.status=PENDING` 생성
2. queue job을 worker가 처리한 뒤 상태가 terminal(`FILLED`)로 전이
3. terminal 상태에서 불법 전이(`FILLED -> FAILED`) 시 `order_status_transition_blocked` ops-event가 warning으로 기록

flake 방지 포인트:
- 고정 polling interval(150ms) + 명시적 timeout(15s)
- 테스트 전 queue `obliterate(force)` 및 `EXECUTION:*` fixture 정리
- `idempotency-key`를 테스트마다 고유하게 생성

실행:

```bash
# 이미 postgres/redis가 떠있는 경우
npm run test:e2e:order-sm

# 로컬 one-shot (의존 서비스 자동 기동 + schema 반영 포함)
npm run test:e2e:order-sm:local
```

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

## PR/배포 전 CI 게이트 정책 (고정)

GitHub Actions 워크플로우: `.github/workflows/single-app-ci-gates.yml`

PR/`main` push 전에 아래 3개 게이트를 **순서대로 고정 실행**합니다.

1. `smoke:ci`
   - 명령: `npm run smoke:ci`
   - 목적: docker postgres/redis + migrate + 핵심 API 시나리오 one-shot 검증
2. `test:e2e:order-sm`
   - 명령: `npm run test:e2e:order-sm`
   - 목적: queue/worker 포함 주문 상태머신 통합 E2E 검증
3. `p1_revalidate --auto`
   - 명령:
     ```bash
     bash scripts/p1_revalidate.sh --auto \
       --execution-source scripts/examples/execution_runs_remediated_sample.jsonl \
       --metrics-source scripts/examples/metrics_runs_remediated_sample.jsonl \
       --auto-kpi-output ../../artifacts/ops/kpi_runs_auto_ci.jsonl \
       ../../artifacts/ops/kpi_contract_report_ci.json
     ```
   - 목적: run-level KPI 자동 생성 + KPI contract overall=GO 확인

실패 정책:
- 세 게이트 중 하나라도 실패하면 워크플로우는 즉시 실패(`non-zero`) 처리됩니다.
- 산출물(`kpi_runs_auto_ci.jsonl`, `kpi_contract_report_ci.json`, `.ci_smoke.dev.log`)은 artifact로 업로드됩니다.

Fixture/한계:
- CI의 `p1_revalidate --auto`는 실거래 데이터 대신 `scripts/examples/*_remediated_sample.jsonl` fixture를 사용합니다.
- 따라서 **파이프라인/계약 검증**에는 유효하지만, 실데이터 품질/드리프트/실시장 이슈는 별도 운영 모니터링으로 보완해야 합니다.

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

### 2-1) Auto Kill-switch (P1-T4)

다음 자동 트리거 중 하나라도 충족하면 kill-switch를 자동으로 ON 처리하고, `kill_switch_on` critical ops event를 발행합니다.

- 연속 실패 임계 초과: `AUTO_KILL_SWITCH_CONSECUTIVE_FAILURES` (기본 `3`)
- 손실 임계 초과: `AUTO_KILL_SWITCH_MAX_DAILY_LOSS` (기본 `500000`, 미설정 시 `RISK_MAX_DAILY_LOSS`)
- 지연 임계/급증:
  - 절대 임계: `AUTO_KILL_SWITCH_LATENCY_THRESHOLD_MS` (기본 `30000`ms)
  - 급증 임계: EWMA 대비 `AUTO_KILL_SWITCH_LATENCY_SPIKE_MULTIPLIER` 배(기본 `3`), 샘플 `AUTO_KILL_SWITCH_LATENCY_SPIKE_MIN_SAMPLES` 이상(기본 `5`)

세부 동작:
- Worker 성공 시 연속 실패 카운터는 0으로 리셋
- 이미 kill-switch가 ON이면 자동 트리거가 중복 ON 하지 않음(수동 stop API와 충돌 방지)
- 수동 OFF(`POST /api/execution/stop` `enabled=false`)는 기존과 동일하게 동작

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

P1 재검증/관찰 실행용 체크리스트는 [`docs/ops/p1-revalidation-24h-checklist.md`](docs/ops/p1-revalidation-24h-checklist.md)를 사용합니다.

P1 최종 인수인계 원페이저: [`docs/ops/p1-final-handover-onepager.md`](docs/ops/p1-final-handover-onepager.md)

현재 24h 관찰 로그(2026-02-28): [`docs/ops/p1-24h-monitoring-log-20260228.md`](docs/ops/p1-24h-monitoring-log-20260228.md)

피처 이관 표준 템플릿은 [`docs/ops/feature-migration-template.md`](../../docs/ops/feature-migration-template.md)를 사용합니다.

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

## 주문 상태머신 (Order State Machine)

주문 상태는 `src/lib/order-status.ts`의 단일 유틸 경로로 관리합니다.

### 상태 정의

- `PENDING`: 접수됨, 아직 최종 체결/종료 아님
- `FILLED`: 체결 완료 (terminal)
- `CANCELED`: 취소 완료 (terminal)
- `FAILED`: 실행 실패 확정 (terminal)

### 전이표

| From \ To | PENDING | FILLED | CANCELED | FAILED |
| --- | --- | --- | --- | --- |
| PENDING | ✅ (idempotent) | ✅ | ✅ | ✅ |
| FILLED | ❌ | ✅ (idempotent) | ❌ | ❌ |
| CANCELED | ❌ | ❌ | ✅ (idempotent) | ❌ |
| FAILED | ❌ | ❌ | ❌ | ✅ (idempotent) |

핵심 규칙:
- terminal(`FILLED/CANCELED/FAILED`) 상태에서 다른 상태로의 역전이는 금지
- 동일 상태 재요청은 허용(idempotent)

### 에러 계약

`OrderStatusTransitionError` (`src/lib/order-status.ts`)

- `UNKNOWN_ORDER_STATUS`: 미정의 상태 문자열
- `INVALID_ORDER_STATUS_TRANSITION`: 전이표에 없는 불법 전이 요청
- `ORDER_NOT_FOUND`: 대상 주문 없음
- `ORDER_STATE_CONFLICT`: 동시성 충돌(예상 from 상태와 DB 현재 상태 불일치)

전이 적용 함수:
- `transitionOrderStatus({ orderId, to })`
- 내부에서 `parse -> validate -> updateMany(where: {id, status: current})` 순으로 단일 경로 처리

### Runtime 연결 상태 (T3 후속 반영)

- API `POST /api/execution/start`
  - 실행 run 생성 직후 `executionOrderLifecycle.createPendingOrder(...)`로 `PENDING` 주문 생성
  - 생성된 `orderId`를 worker payload로 전달
- Worker 성공 경로
  - 실행 완료 후 `executionOrderLifecycle.markFilled(...)` 호출
  - 내부적으로 `transitionOrderStatus(..., to='FILLED')` 단일 경로 사용
- Worker 실패 경로
  - 실패 처리(`markRunFailed`)에서 `executionOrderLifecycle.markFailed(...)` 호출
  - 내부적으로 `transitionOrderStatus(..., to='FAILED')` 단일 경로 사용
- 불법 전이/충돌/미존재 주문 등 전이 실패 시
  - `order_status_transition_blocked`(warning/critical) 또는 `order_status_transition_error`(critical) ops-event 로그 기록
  - 에러는 재던져 기존 계약(`OrderStatusTransitionError`) 유지

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
