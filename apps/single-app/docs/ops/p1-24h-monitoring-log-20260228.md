# P1 24h 관찰 로그 (2026-02-28)

- 관찰 시작시각(KST): `2026-02-28 00:02`
- 관찰 종료시각(KST): `2026-03-01 00:02`
- 담당자: `OpenClaw sub-agent`
- 기준 문서: `docs/ops/p1-revalidation-24h-checklist.md`

## Round-0 스냅샷

- 최신 smoke 결과: `PASS` (`npm run smoke:ci`, `2026-02-28 00:02 KST`, `Smoke test PASSED (13 checks)`)
- 최신 KPI 결과: `overall=GO`, `warn_runs=0/5` (`../../artifacts/ops/kpi_contract_report_canary_revalidate.json`, mtime `2026-02-27 23:57 KST`)
- kill-switch 상태 확인값(가능 범위): smoke step `f`에서 `enabled=false` reset 확인(OFF). 최근 이벤트 로그에도 `kill_switch_off` 기록 확인.
- 비고/즉시조치: Round-0 기준 운영 게이트 양호. 다음 체크부터 2시간 간격으로 동일 항목 반복 점검.

## 임계값 기준

- Brier `<= 0.20`
- ECE `<= 0.08`
- Slippage(bps) `<= 15.0`
- Fail-rate `<= 0.02`
- Latency: `AUTO_KILL_SWITCH_LATENCY_THRESHOLD_MS` 및 Spike 기준 준수

## 2시간 간격 관찰표 (24h)

| 시간(KST) | Run ID | Brier | ECE | Slippage (bps) | Fail-rate | Latency (ms) | Kill-switch 이벤트 | 이상 유무(OK/WARN) | 메모/조치 |
|---|---|---:|---:|---:|---:|---|---|---|---|
| T+00h (2026-02-28 00:02) | canary-2026-02-27T15:00Z | 0.189 | 0.078 | 12.3 | 0.013 | N/A (round-0 표본 미수집) | OFF (enabled=false) | OK | smoke PASS(13 checks), KPI GO/warn 0/5 |
| T+02h |  |  |  |  |  |  |  |  |  |
| T+04h |  |  |  |  |  |  |  |  |  |
| T+06h |  |  |  |  |  |  |  |  |  |
| T+08h |  |  |  |  |  |  |  |  |  |
| T+10h |  |  |  |  |  |  |  |  |  |
| T+12h |  |  |  |  |  |  |  |  |  |
| T+14h |  |  |  |  |  |  |  |  |  |
| T+16h |  |  |  |  |  |  |  |  |  |
| T+18h |  |  |  |  |  |  |  |  |  |
| T+20h |  |  |  |  |  |  |  |  |  |
| T+22h |  |  |  |  |  |  |  |  |  |

## 2시간 점검 명령 세트 (복붙용)

```bash
# [A] 기본 위치
cd /Users/ychoi/Documents/GitHub/Market-Calibration-Agent/apps/single-app

# [B] one-shot smoke
npm run smoke:ci

# [C] 최신 KPI overall/warn_runs 확인
python3 - <<'PY'
import json
p='../../artifacts/ops/kpi_contract_report_canary_revalidate.json'
with open(p) as f:
    d=json.load(f)
print('overall=', d.get('overall'), 'warn_runs=', f"{d.get('warn_runs')}/{d.get('recent_n')}")
if d.get('runs'):
    r=d['runs'][0]
    print('latest_run=', r.get('run_id'), 'brier=', r.get('brier'), 'ece=', r.get('ece'), 'slippage=', r.get('realized_slippage_bps'), 'fail_rate=', r.get('execution_fail_rate'))
PY

# [D] kill-switch 최근 ON/OFF 이벤트 확인(로그 tail)
tail -n 80 .ci_smoke.dev.log | rg "kill_switch_on|kill_switch_off|/api/execution/stop"
```

## 이벤트 상세 기록 (선택)

| 시각(KST) | 타입 | 심각도 | runId/jobId | 내용(reason) | 조치 | 담당 |
|---|---|---|---|---|---|---|
| 2026-02-28 00:02 | smoke:ci | info | - | Smoke test PASSED (13 checks) | baseline 확보 | OpenClaw |
| 2026-02-28 00:02 | kpi-summary | info | canary-2026-02-27T15:00Z | overall=GO, warn_runs=0/5 | 관찰 지속 | OpenClaw |

## 종료 판정

- 24h 관찰 중 WARN 횟수: ``
- Kill-switch ON 이벤트 발생: `Y / N`
- 최종 의견: `GO / NO_GO / HOLD`
- 후속 액션: ``
