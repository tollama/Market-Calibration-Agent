# Single App 운영 Runbook (ADMIN 토큰 / Compose / Canary)

`apps/single-app` 운영 시 반복되는 3개 작업(관리자 토큰 운영화, compose 경고 제거 기준, dryRun=false 카나리)을 표준화한 문서입니다.

## 0) 대상

- 대상 앱: `apps/single-app`
- 중요 엔드포인트:
  - `POST /api/execution/start` (관리자 인증 필요)
  - `POST /api/execution/stop` (관리자 인증 필요)

---

## 1) Docker Compose 경고 제거 기준

Compose 사양 최신 기준에서는 `docker-compose.yml`의 `version:` 키가 obsolete입니다.

- 현재 기준: `apps/single-app/docker-compose.yml`에서 `version` 제거 완료
- 운영 원칙: 신규/수정 compose 파일에 `version:`를 다시 넣지 않음

실행:

```bash
cd apps/single-app
docker compose up -d postgres redis
```

---

## 2) ADMIN_API_TOKEN 운영화 (생성/로테이션/.env 반영)

### 2-1. 생성/로테이션

아래 스크립트로 새 토큰을 생성하고 `.env`에 즉시 반영합니다.

```bash
cd apps/single-app
scripts/admin_token_rotate.sh --env-file .env
```

- 기본 32바이트 난수(hex 64 chars)
- 기존 `.env`는 타임스탬프 백업(`.env.bak.YYYYMMDDHHMMSS`) 생성
- `ADMIN_API_TOKEN` 항목이 있으면 치환, 없으면 추가

토큰만 출력하고 싶다면:

```bash
scripts/admin_token_rotate.sh --print-only
```

### 2-2. 반영

```bash
cd apps/single-app
set -a; source .env; set +a
npm run dev
npm run worker
```

> 운영에서는 app/worker를 같은 토큰으로 재기동해야 합니다.

### 2-3. Smoke 재검증 (로테이션 후 필수)

```bash
cd apps/single-app
ADMIN_API_TOKEN="$ADMIN_API_TOKEN" npm run smoke:ci
```

`smoke:ci` 통과 기준:
- 무토큰 start 요청이 `401/403`
- 토큰 포함 start 요청이 `202`
- kill-switch ON 상태에서 start가 `409`

---

## 3) dryRun=false 카나리 절차 (실주문 없이 파이프라인 진입 확인)

`dryRun=false`는 일반적으로 실제 파이프라인 경로로 들어가므로, 카나리에서는 **no-op 엔트리포인트**를 강제해 안전하게 검증합니다.

### 3-1. no-op 엔트리포인트 지정

```bash
cd apps/single-app
set -a; source .env; set +a
export CALIBRATION_ENTRYPOINT_MODULE="pipelines.noop_calibration_entrypoint"
```

### 3-2. 실행 요청 (dryRun=false)

```bash
curl -X POST http://127.0.0.1:3000/api/execution/start \
  -H "authorization: Bearer ${ADMIN_API_TOKEN}" \
  -H 'content-type: application/json' \
  -d '{"mode":"mock","dryRun":false,"maxPosition":1000,"notes":"canary-noop"}'
```

### 3-3. 파이프라인 진입 확인 (DB)

```bash
cd apps/single-app
node -e '
const { PrismaClient } = require("@prisma/client");
const prisma = new PrismaClient();
(async () => {
  const row = await prisma.calibrationRun.findFirst({ orderBy: { requestedAt: "desc" } });
  console.log(row ? { id: row.id, status: row.status, notes: row.notes } : null);
  await prisma.$disconnect();
})();
'
```

판정:
- `status=COMPLETED` 이고 notes에 `calibration pipeline done` 계열 메시지가 보이면 통과
- `DRY_RUN_DONE`이면 `dryRun=false`가 반영되지 않은 것

### 3-4. 종료/복구

```bash
unset CALIBRATION_ENTRYPOINT_MODULE
```

필요 시 kill-switch를 OFF로 되돌립니다.

```bash
curl -X POST http://127.0.0.1:3000/api/execution/stop \
  -H "authorization: Bearer ${ADMIN_API_TOKEN}" \
  -H 'content-type: application/json' \
  -d '{"enabled":false,"reason":"post-canary reset"}'
```

---

## 4) 실거래 카나리 1회 체크리스트 (고정 파라미터)

> 목적: **실주문 노출을 최소화**하면서 `dryRun=false` 실제 경로(큐 → 워커 → 파이프라인 진입) 정상 동작을 1회 검증.

### 4-1. 사전조건

- app/worker가 모두 기동 중이고 `/api/health`가 `200` + `db.ok=true`
- `ADMIN_API_TOKEN`이 현재 app/worker와 동일하게 반영됨
- kill-switch 상태가 OFF (`GET /api/execution/stop`에서 `enabled=false`)
- no-op 엔트리포인트 사용 가능
  - `CALIBRATION_ENTRYPOINT_MODULE="pipelines.noop_calibration_entrypoint"`
- 운영자 확인: 카나리 1회 동안 모니터링 가능한 시간/담당자 확보

### 4-2. 권장 고정 파라미터

| 항목 | 고정값 | 이유 |
|---|---:|---|
| `mode` | `mock` | 실거래 경로 검증 목적, 전략 변동 최소화 |
| `dryRun` | `false` | dry-run 우회 없이 실제 실행 경로 진입 확인 |
| `maxPosition` | `1000` | 리스크 노출 최소화 |
| `notes` | `canary-live-once-YYYYMMDD-HHMM` | 실행 식별/추적 용이 |
| `CALIBRATION_ENTRYPOINT_MODULE` | `pipelines.noop_calibration_entrypoint` | 주문 없는 no-op 파이프라인 강제 |

### 4-3. 실행 순서

1. 환경 반영

```bash
cd apps/single-app
set -a; source .env; set +a
export CALIBRATION_ENTRYPOINT_MODULE="pipelines.noop_calibration_entrypoint"
```

2. 사전 상태 확인

```bash
curl -s http://127.0.0.1:3000/api/health
curl -s http://127.0.0.1:3000/api/execution/stop
```

3. 카나리 실행(고정 파라미터)

```bash
TS=$(date +%Y%m%d-%H%M)
curl -X POST http://127.0.0.1:3000/api/execution/start \
  -H "authorization: Bearer ${ADMIN_API_TOKEN}" \
  -H 'content-type: application/json' \
  -d "{\"mode\":\"mock\",\"dryRun\":false,\"maxPosition\":1000,\"notes\":\"canary-live-once-${TS}\"}"
```

4. DB 최신 run 확인

```bash
cd apps/single-app
node -e '
const { PrismaClient } = require("@prisma/client");
const prisma = new PrismaClient();
(async () => {
  const row = await prisma.calibrationRun.findFirst({ orderBy: { requestedAt: "desc" } });
  console.log(row ? { id: row.id, status: row.status, notes: row.notes } : null);
  await prisma.$disconnect();
})();
'
```

5. 종료 복구

```bash
unset CALIBRATION_ENTRYPOINT_MODULE
curl -X POST http://127.0.0.1:3000/api/execution/stop \
  -H "authorization: Bearer ${ADMIN_API_TOKEN}" \
  -H 'content-type: application/json' \
  -d '{"enabled":false,"reason":"post-canary reset"}'
```

### 4-4. 중단 조건 (즉시 kill-switch ON)

아래 중 하나라도 발생하면 즉시 중단:

- `POST /api/execution/start` 응답이 `5xx` 또는 비정상 payload
- DB run 상태가 `FAILED`로 종료되거나 예상치 못한 에러 로그 다수 발생
- no-op 엔트리포인트 미적용 징후(실주문/외부 주문 호출 흔적)
- 운영자 판단으로 안전성 불확실

즉시 차단 명령:

```bash
curl -X POST http://127.0.0.1:3000/api/execution/stop \
  -H "authorization: Bearer ${ADMIN_API_TOKEN}" \
  -H 'content-type: application/json' \
  -d '{"enabled":true,"reason":"canary abort"}'
```

### 4-5. 성공 기준

- 시작 요청이 `202`로 수락됨
- 최신 `calibration_runs`가 카나리 notes(`canary-live-once-*`)와 매칭됨
- 최종 상태가 `COMPLETED`
- notes/로그에 `calibration pipeline done` 계열 완료 메시지 확인
- 실행 중 kill-switch 자동/수동 오작동 없음

### 4-6. 실행 후 기록 템플릿

```md
## Canary 실행 기록 (1회)
- 실행시각(KST):
- 수행자:
- runId/jobId:
- 고정 파라미터:
  - mode=mock
  - dryRun=false
  - maxPosition=1000
  - notes=canary-live-once-...
  - CALIBRATION_ENTRYPOINT_MODULE=pipelines.noop_calibration_entrypoint
- 결과:
  - start 응답 코드:
  - 최종 status:
  - 완료 메시지(notes/log):
- 중단 여부:
  - kill-switch ON 실행 여부(Yes/No):
  - reason:
- 후속 조치:
```
