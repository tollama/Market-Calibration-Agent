# P1 최종 인수인계 원페이저

- 대상: `apps/single-app`
- 기준 문서/스크립트: `docs/ops/p1-revalidation-24h-checklist.md`, `docs/ops/p1-gonogo-remediation.md`, `scripts/p1_revalidate.sh`, `scripts/ci_smoke.sh`, `README.md`

## Advisory-only 고지 (인수인계 필수 확인)

- 본 시스템은 정보 제공 전용이며 투자 권유/거래 집행 서비스가 아니다.
- 본 문서 내용은 법률·세무·회계 자문이 아니다.
- 실제 투자/거래 실행, 규제 준수, 결과 책임은 사용자/운영 주체에 있다.
- 기본 정책은 `EXECUTION_API_ENABLED=false` 유지이며, override는 내부 승인된 검증 시나리오에서만 제한적으로 허용한다.

## 1) 운영 명령 5개 (복붙용)

```bash
cd /Users/ychoi/Documents/GitHub/Market-Calibration-Agent/apps/single-app && docker compose up -d postgres redis
```

```bash
cd /Users/ychoi/Documents/GitHub/Market-Calibration-Agent/apps/single-app && npm run smoke:ci
```

```bash
cd /Users/ychoi/Documents/GitHub/Market-Calibration-Agent/apps/single-app && bash scripts/p1_revalidate.sh --auto --execution-source scripts/examples/execution_runs_sample.jsonl --metrics-source scripts/examples/metrics_runs_sample.jsonl --auto-kpi-output ../../artifacts/ops/kpi_runs_auto.jsonl
```

```bash
# 기본 advisory-only 정책에서는 EXECUTION_API_ENABLED=false 이므로 POST는 차단(403)됨.
# 내부 승인된 예외 검증에서만 true로 전환 후 호출.
curl -X POST http://127.0.0.1:3000/api/execution/stop -H "authorization: Bearer ${ADMIN_API_TOKEN}" -H 'content-type: application/json' -d '{"enabled":true,"reason":"P1 incident rollback"}'
```

```bash
curl http://127.0.0.1:3000/api/execution/stop
```

## 2) GO 조건 (정량 기준)

아래 **전부** 충족 시 GO:

1. `npm run smoke:ci` PASS
2. KPI 5-run 리포트 `overall=GO`
3. 지표 임계 충족
   - `brier <= 0.20`
   - `ece <= 0.08`
   - `realized_slippage_bps <= 15.0`
   - `execution_fail_rate <= 0.02`
4. 24h 관찰 중 `kill_switch_on`(자동) 미발생
5. P1 보정 파라미터 적용 확인
   - `RISK_MAX_POSITION_PER_RUN=700000`
   - `ORDER_RATE_LIMIT_PER_MIN=20`
   - `AUTO_KILL_SWITCH_LATENCY_THRESHOLD_MS=20000`
   - `AUTO_KILL_SWITCH_LATENCY_SPIKE_MULTIPLIER=2.5`

## 3) 장애 시 롤백 3단계

1. **즉시 차단 (1분 이내)**  
   `POST /api/execution/stop`로 kill-switch ON 유지(`enabled=true`) 및 reason 기록
2. **원인 구간 고정 + 로그 수집 (10분 이내)**  
   최근 실패 run 기준으로 app/worker 로그, slippage/fail-rate/latency 지표, `kill_switch_on` 이벤트 수집
3. **안전 기준 복귀 + 재검증 (30분 이내)**  
   P1 보정값 재적용 후 `npm run smoke:ci` + `bash scripts/p1_revalidate.sh --auto ...` 재실행, `overall=GO` 확인 전까지 재개 금지

## 4) 온콜 체크포인트 (주기/임계/알림)

- **점검 주기**: 2시간 간격(24h 동안 12회)
- **정량 임계**
  - `brier > 0.20` 또는 `ece > 0.08`
  - `realized_slippage_bps > 15.0`
  - `execution_fail_rate > 0.02`
  - latency가 `AUTO_KILL_SWITCH_LATENCY_THRESHOLD_MS` 초과
  - EWMA 대비 latency가 `AUTO_KILL_SWITCH_LATENCY_SPIKE_MULTIPLIER` 초과
- **즉시 알림 조건**
  - 위 임계 1개라도 초과
  - `kill_switch_on` 이벤트 발생
- **즉시 조치**
  - kill-switch ON 상태 확인 → 원인 로그 수집 → 보정안 재적용 후 재검증

## 5) 명령/구현 일치 검증 메모

- `npm run smoke:ci`는 `package.json`에서 `bash scripts/ci_smoke.sh`로 연결됨
- `bash scripts/p1_revalidate.sh --auto ...` 옵션(`--execution-source`, `--metrics-source`, `--auto-kpi-output`)은 스크립트 usage와 일치
- KPI/임계값 기준(`brier/ece/slippage/fail-rate`)과 24h 점검/알림 조건은 `docs/ops/p1-revalidation-24h-checklist.md`와 일치
- 롤백 시 kill-switch API(`POST /api/execution/stop`)는 `README.md` API 테스트 절차와 일치
