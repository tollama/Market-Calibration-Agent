# P1 24h 관찰 로그 템플릿

- 관찰 시작시각(KST): `YYYY-MM-DD HH:mm`
- 관찰 종료시각(KST): `YYYY-MM-DD HH:mm`
- 담당자: ``
- 기준 문서: `docs/ops/p1-revalidation-24h-checklist.md`

## 임계값 기준

- Brier `<= 0.20`
- ECE `<= 0.08`
- Slippage(bps) `<= 15.0`
- Fail-rate `<= 0.02`
- Latency: `AUTO_KILL_SWITCH_LATENCY_THRESHOLD_MS` 및 Spike 기준 준수

## 2시간 간격 관찰표 (24h)

| 시간(KST) | Run ID | Brier | ECE | Slippage (bps) | Fail-rate | Latency (ms) | Kill-switch 이벤트 | 이상 유무(OK/WARN) | 메모/조치 |
|---|---|---:|---:|---:|---:|---|---|---|---|
| T+00h |  |  |  |  |  |  |  |  |  |
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

## 이벤트 상세 기록 (선택)

| 시각(KST) | 타입 | 심각도 | runId/jobId | 내용(reason) | 조치 | 담당 |
|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |

## 종료 판정

- 24h 관찰 중 WARN 횟수: ``
- Kill-switch ON 이벤트 발생: `Y / N`
- 최종 의견: `GO / NO_GO / HOLD`
- 후속 액션: ``
