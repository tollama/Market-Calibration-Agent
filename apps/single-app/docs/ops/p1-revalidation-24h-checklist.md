# P1 재검증 + 24h 관찰 체크리스트

- 작성일: 2026-02-27 (KST)
- 대상: `apps/single-app` 운영자
- 목적: 파라미터 보정 반영 후 **재검증(smoke + KPI 5-run)** 및 **24시간 관찰**을 즉시 실행 가능한 절차로 표준화

## Advisory-only 운영 원칙 (필수)

- 본 프로젝트는 정보 제공 전용이며 투자 권유/중개/거래 집행 서비스가 아니다.
- 본 문서의 절차는 품질/리스크 관찰용 운영 절차이며, 법률·세무·회계 자문이 아니다.
- 관할 규제 준수, 실제 투자/거래 판단, 손익 책임은 사용자/운영 주체에 있다.
- `EXECUTION_API_ENABLED=false`를 기본 유지하고, 예외적 내부 검증 시에만 승인 후 일시적으로 `true`를 사용한다.

---

## CI 게이트(필수) 정책

GitHub Actions `.github/workflows/single-app-ci-gates.yml`에서 PR/`main` push 시 아래 3개를 고정 실행:

1. `smoke:ci`
2. `test:e2e:order-sm`
3. `p1_revalidate --auto`

세 게이트 중 하나라도 실패하면 워크플로우는 실패(non-zero) 처리된다.

`p1_revalidate --auto`는 CI에서 실데이터 대신 fixture(`scripts/examples/execution_runs_remediated_sample.jsonl`, `scripts/examples/metrics_runs_remediated_sample.jsonl`)를 사용해 계약 검증을 수행한다.

---

## 0) 사전 준비

- [ ] 작업 경로 확인: `cd /Users/ychoi/Documents/GitHub/Market-Calibration-Agent/apps/single-app`
- [ ] `.env` 존재 확인 (`cp .env.example .env` 필요 시 수행)
- [ ] Docker / Node / Python3 사용 가능 확인

```bash
cd /Users/ychoi/Documents/GitHub/Market-Calibration-Agent/apps/single-app
node -v
python3 --version
docker --version
docker compose version
```

---

## 1) .env 튜닝값 반영 확인 (P1 보정안)

`docs/ops/p1-gonogo-remediation.md` 권고 기준으로 아래 값을 확인/반영:

- `RISK_MAX_POSITION_PER_RUN=700000`
- `ORDER_RATE_LIMIT_PER_MIN=20`
- `AUTO_KILL_SWITCH_LATENCY_THRESHOLD_MS=20000`
- `AUTO_KILL_SWITCH_LATENCY_SPIKE_MULTIPLIER=2.5`

검증 명령:

```bash
cd /Users/ychoi/Documents/GitHub/Market-Calibration-Agent/apps/single-app
for key in \
  RISK_MAX_POSITION_PER_RUN \
  ORDER_RATE_LIMIT_PER_MIN \
  AUTO_KILL_SWITCH_LATENCY_THRESHOLD_MS \
  AUTO_KILL_SWITCH_LATENCY_SPIKE_MULTIPLIER
  do
    grep -E "^${key}=" .env || echo "[MISSING] ${key}"
  done
```

체크:
- [ ] 4개 키 모두 `.env`에 존재
- [ ] 값이 권고값과 일치

---

## 2) 재기동 순서 (환경값 반영)

권장 순서:

1. 인프라 컨테이너(POSTGRES/REDIS) 기동
2. smoke:ci로 API/DB/Queue one-shot 검증
3. app/worker 운영 방식에 따라 재기동

```bash
cd /Users/ychoi/Documents/GitHub/Market-Calibration-Agent/apps/single-app

docker compose up -d postgres redis
npm run smoke:ci
```

운영 프로세스 재기동(예시):

```bash
# 터미널 1
cd /Users/ychoi/Documents/GitHub/Market-Calibration-Agent/apps/single-app
npm run dev

# 터미널 2
cd /Users/ychoi/Documents/GitHub/Market-Calibration-Agent/apps/single-app
npm run worker
```

체크:
- [ ] `smoke:ci` 전체 PASS
- [ ] `/api/health` 200 + `db.ok=true`

---

## 3) KPI 리포트 재실행 (최근 5-run)

참고: run-level KPI 입력 자동화/정합 규칙 문서 `docs/ops/p1-kpi-input-automation.md`

### 3-1. 표준 실행 (자동 KPI 생성 + 재검증)

```bash
cd /Users/ychoi/Documents/GitHub/Market-Calibration-Agent/apps/single-app
bash scripts/p1_revalidate.sh --auto \
  --execution-source scripts/examples/execution_runs_sample.jsonl \
  --metrics-source scripts/examples/metrics_runs_sample.jsonl \
  --auto-kpi-output ../../artifacts/ops/kpi_runs_auto.jsonl
```

> 산출물(JSONL) 필수 필드: `run_id, ended_at, brier, ece, realized_slippage_bps, execution_fail_rate`

### 3-2. 기존 입력(JSONL) 직접 지정 방식

```bash
cd /Users/ychoi/Documents/GitHub/Market-Calibration-Agent/apps/single-app
bash scripts/p1_revalidate.sh ../../scripts/examples/kpi_runs_sample.jsonl
```

### 3-3. 수동 실행(대체)

```bash
cd /Users/ychoi/Documents/GitHub/Market-Calibration-Agent
python3 scripts/kpi_contract_report.py \
  --input scripts/examples/kpi_runs_sample.jsonl \
  --stage canary \
  --n 5 \
  --thresholds configs/kpi_contract_thresholds.json \
  --output-json artifacts/ops/kpi_contract_report_canary.json
```

체크:
- [ ] `n=5` 기준 리포트 생성 완료
- [ ] `overall=GO`
- [ ] WARN run 0건(권고)

---

## 4) GO 판정 기준

아래를 모두 만족하면 GO:

- [ ] smoke:ci PASS
- [ ] KPI 5-run 리포트 `overall=GO`
- [ ] 주요 지표 임계 충족
  - [ ] `brier <= 0.20`
  - [ ] `ece <= 0.08`
  - [ ] `realized_slippage_bps <= 15.0`
  - [ ] `execution_fail_rate <= 0.02`
- [ ] kill-switch 동작 확인(ON/OFF API 정상)
- [ ] 24h 관찰 중 치명 알림 조건 미충족

NO_GO/보류 조건(하나라도 해당):
- smoke:ci 실패
- KPI `overall=NO_GO`
- 24h 관찰 중 kill-switch 자동 ON 이벤트 발생

---

## 5) 24h 관찰 계획 (항목/주기/알림)

관찰 로그 템플릿: `docs/ops/templates/p1-24h-monitoring-log.md`

### 관찰 주기

- **2시간 간격** 정기 점검 (총 12회/24h)
- 권장 시각(KST): 00, 02, 04, 06, 08, 10, 12, 14, 16, 18, 20, 22시

### 필수 관찰 항목

- Brier
- ECE
- realized slippage(bps)
- execution fail-rate
- latency(p95/p99 또는 max)
- kill-switch 이벤트(수동/자동, reason)

### 알림(즉시 에스컬레이션) 조건

- `brier > 0.20` 또는 `ece > 0.08`
- `realized_slippage_bps > 15.0`
- `execution_fail_rate > 0.02`
- latency 급증/임계 초과
  - `AUTO_KILL_SWITCH_LATENCY_THRESHOLD_MS` 초과
  - EWMA 대비 `AUTO_KILL_SWITCH_LATENCY_SPIKE_MULTIPLIER` 초과
- `kill_switch_on` 이벤트 발생

즉시 조치:
1. `POST /api/execution/stop`로 kill-switch ON 유지 확인
2. 최근 run/jodId 기준 원인 로그 수집
3. `docs/ops/p1-gonogo-remediation.md` 보정안 재적용 후 재검증

---

## 6) 실행 기록

- 재검증 실행시각: `__________`
- 담당자: `__________`
- smoke 결과: `PASS / FAIL`
- KPI 5-run 결과: `GO / NO_GO`
- 24h 관찰 종료시각: `__________`
- 최종 판정: `GO / NO_GO / HOLD`
