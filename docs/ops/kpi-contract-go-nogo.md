# KPI 계약 (Go/No-Go) — PRD1 Task P1-T1

본 문서는 카나리/운영 공통으로 사용할 KPI 계약(임계값)과 판정 기준을 고정한다.

## 1) KPI 정의 및 현재 수집 위치

| KPI | 정의 | 현재 수집/생성 위치 |
|---|---|---|
| Brier | 예측확률-실제결과의 제곱오차 평균 (낮을수록 좋음) | 계산: `calibration/metrics.py` (`brier_score`) / 집계: `pipelines/build_scoreboard_artifacts.py` / 산출물: `data/derived/metrics/scoreboard.json` |
| ECE | Expected Calibration Error (낮을수록 좋음) | 계산: `calibration/metrics.py` (`expected_calibration_error`) / 집계: `pipelines/build_scoreboard_artifacts.py` / 산출물: `data/derived/metrics/scoreboard.json` |
| realized slippage (bps) | 실행 기준 대비 실제 체결 괴리(bps, 낮을수록 좋음) | **운영 입력 필요**: 런 단위 KPI JSON/JSONL(`scripts/kpi_contract_report.py --input`)에 `realized_slippage_bps` 필드로 수집 |
| execution fail rate | 실행 실패 비율(낮을수록 좋음) | 런 단위 KPI JSON/JSONL에 `execution_fail_rate` 필드로 수집 (실시간 관측 원천: `tsfm_request_total{status=~"error|failed"}` / `monitoring/grafana/prd2-observability-dashboard.json`) |

> 참고: Brier/ECE는 배치/스코어보드 기반 지표이고, slippage/fail-rate는 실행 런 기준으로 수집되는 운영 지표다.

---

## 2) 카나리/운영 공통 임계값 (기본값 확정)

공통 임계값(카나리/운영 동일):

- `brier <= 0.20`
- `ece <= 0.08`
- `realized_slippage_bps <= 15.0`
- `execution_fail_rate <= 0.02` (2%)

기본 설정 파일:
- `configs/kpi_contract_thresholds.json`

판정 규칙:
- 최근 N-run 중 **단 1건이라도** 임계값 초과가 있으면 `NO_GO`
- 최근 N-run 모두 통과 시 `GO`

---

## 3) 자동 리포트 스크립트 (최근 N-run 요약 + 경고)

스크립트:
- `scripts/kpi_contract_report.py`

입력 포맷(각 run 당 1 row):

```json
{
  "run_id": "canary-2026-02-27T12:00Z",
  "ts": "2026-02-27T12:00:00Z",
  "stage": "canary",
  "brier": 0.182,
  "ece": 0.066,
  "realized_slippage_bps": 10.2,
  "execution_fail_rate": 0.010
}
```

실행 예시:

```bash
python3 scripts/kpi_contract_report.py \
  --input scripts/examples/kpi_runs_sample.jsonl \
  --n 5 \
  --stage canary \
  --thresholds configs/kpi_contract_thresholds.json \
  --output-json artifacts/ops/kpi_contract_report_sample.json
```

동작:
- 최신 timestamp 기준 최근 N건 정렬/요약
- 임계값 초과 metric이 있으면 해당 run `WARN`
- 전체 판정 `GO`/`NO_GO` 출력
- 임계값 초과 내역(alerts) 상세 표시

---

## 4) 샘플 실행 결과

샘플 입력:
- `scripts/examples/kpi_runs_sample.jsonl`

샘플 결과(JSON):
- `artifacts/ops/kpi_contract_report_sample.json`

샘플 결과(요약 텍스트):
- `artifacts/ops/kpi_contract_report_sample.txt`

---

## 5) 운영 적용 체크

1. 배치 경로에서 최신 Brier/ECE를 run-level KPI feed로 넣는다.
2. 실행 시스템에서 `realized_slippage_bps`, `execution_fail_rate`를 동일 run_id 기준으로 기록한다.
3. 배포 게이트 전에 `scripts/kpi_contract_report.py --n <window>`를 실행해 `overall` 확인:
   - `GO`면 승급
   - `NO_GO`면 승급 중단 및 원인(run alerts) 해소 후 재평가
