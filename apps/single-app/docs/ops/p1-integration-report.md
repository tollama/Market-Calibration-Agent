# P1(T1~T4) 통합 스모크 + 최종 Go/No-Go 리포트

- 작성 일시: 2026-02-27 23:xx (KST)
- 작업 디렉토리: `/Users/ychoi/Documents/GitHub/Market-Calibration-Agent/apps/single-app`
- 범위: health/auth/kill-switch, idempotency replay, auto kill-switch 트리거, KPI 계약 리포트

---

## 1) 실행 명령 및 결과 (한국어)

### A. 의존 서비스 준비 + 최신 마이그레이션 적용

```bash
# Docker Desktop 기동 (초기 daemon 미기동 상태)
open -a Docker

# 의존 서비스 준비
cd /Users/ychoi/Documents/GitHub/Market-Calibration-Agent/apps/single-app
docker compose up -d postgres redis
docker exec single-app-postgres pg_isready -U postgres
docker exec single-app-redis redis-cli ping

# 최신 마이그레이션 적용
npx prisma migrate deploy
```

결과 요약:
- Postgres: accepting connections
- Redis: PONG
- Prisma migrate deploy: **신규 1건 적용** (`20260227233000_add_execution_idempotency_key`)

### B. 통합 스모크 (health/auth/kill-switch + idempotency replay)

```bash
cd /Users/ychoi/Documents/GitHub/Market-Calibration-Agent/apps/single-app
npm run smoke:ci
```

핵심 결과:
- `[RESULT] Smoke test PASSED (13 checks)`
- 포함 검증:
  - health 200 + db.ok=true ✅
  - start 무토큰 401/403 ✅
  - idempotency 1차 202 / 2차 200 replayed=true ✅
  - replay 시 동일 runId ✅
  - DB idempotencyKey row count=1 ✅
  - stop enabled=true 후 start 409 차단 ✅
  - stop enabled=false 복구 ✅

### C. auto kill-switch 트리거 발화 시나리오 (테스트 기반)

```bash
cd /Users/ychoi/Documents/GitHub/Market-Calibration-Agent/apps/single-app
npm run test:auto-killswitch
```

결과:
- 총 4개 테스트 통과 (pass 4 / fail 0)
- 트리거 검증 항목:
  - 연속 실패 임계 초과 트리거 ✅
  - 손실 임계 초과 트리거 ✅
  - 지연 절대 임계 초과 트리거 ✅
  - 지연 급증(스파이크) 트리거 ✅

### D. KPI 계약 리포트 실행 (`kpi_contract_report`)

```bash
cd /Users/ychoi/Documents/GitHub/Market-Calibration-Agent
python3 scripts/kpi_contract_report.py \
  --input scripts/examples/kpi_runs_sample.jsonl \
  --stage canary \
  --n 5 \
  --thresholds configs/kpi_contract_thresholds.json \
  --output-json artifacts/ops/kpi_contract_report_canary.json
```

결과:
- 출력: `overall=NO_GO warn_runs=1/5`
- 종료코드: `2`
- WARN 런 1건(14:00Z):
  - `brier>0.2000`
  - `ece>0.0800`
  - `realized_slippage_bps>15.00`

---

## 2) PASS/FAIL 체크리스트

- [x] 최신 마이그레이션 적용 및 의존 서비스 준비
- [x] health/auth/kill-switch 기본 시나리오
- [x] idempotency key 재요청 replay (200, replayed=true, 동일 runId)
- [x] auto kill-switch 트리거 최소 1개 발화 시나리오(테스트/시뮬레이션 기반)
- [x] KPI 계약 리포트 스크립트 실행 (`kpi_contract_report`)
- [ ] KPI 계약 게이트 통과 (`overall=GO`)  
  ↳ 현재 `overall=NO_GO`

---

## 3) 최종 Go/No-Go 판정

## 판정: **NO-GO**

근거:
1. P1 통합 스모크(서비스/DB/API/idempotency/kill-switch)는 모두 통과했으나,
2. KPI 계약 리포트 결과가 `overall=NO_GO`(warn 1/5)로 게이트 불합격.
3. 운영 게이트 기준상 KPI 계약 미충족 상태에서는 배포/승격 진행 불가.

---

## 4) 블로커 / 리스크 / 즉시 조치

### 블로커
- KPI 계약 미충족 (`overall=NO_GO`, 1개 런 WARN)

### 리스크
- canary 품질 편차(특정 런에서 brier/ece/slippage 동시 임계 초과)
- 동일 패턴 재발 시 실거래 손익/체결 품질 변동 가능성

### 즉시 조치
1. WARN 런(14:00Z) 원인 분석: 입력 데이터 드리프트/체결 지연/슬리피지 급등 구간 분해
2. 파라미터/전략 재튜닝 후 동일 리포트 재실행
3. 최근 N-run 윈도우 재검증 시 `overall=GO` 확보 전까지 승격 보류
4. 필요 시 kill-switch ON 기본 운영으로 유지하며 원인 해결 후 재검증

---

## 5) 결론 요약

- **기능 통합 검증 자체는 성공(PASS)**
- **운영 KPI 게이트는 실패(NO_GO)**
- 따라서 현재 시점 최종 판정은 **NO-GO**
