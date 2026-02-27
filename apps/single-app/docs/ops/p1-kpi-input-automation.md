# P1 KPI 입력 자동화 (run-level 정합)

## 목적
`kpi_contract_report.py` 입력(JSONL)을 수동 편집 없이 자동 생성한다.

산출 JSONL 각 row 최소 필드:
- `run_id`
- `ended_at`
- `brier`
- `ece`
- `realized_slippage_bps`
- `execution_fail_rate`

## 스크립트
- `scripts/build_run_kpi_jsonl.ts`

## 입력 소스
1. **execution source** (필수)
   - 필드: `run_id`, `ended_at`, `realized_slippage_bps`, `execution_fail_rate`
   - alias 허용: `runId`, `finishedAt`, `slippage_bps`, `exec_fail_rate` 등

2. **metrics source** (선택)
   - run-level metrics 형식: `run_id`, `brier`, `ece` (+선택 `ended_at`)
   - scoreboard 형식: `items[].{as_of,brier,ece}` 또는 배열 row

## run_id 정합 규칙
매칭 우선순위:
1. **run_id exact match** (대소문자/공백 정규화)
2. **ended_at 근접 매칭** (기본 ±300초)
3. **scoreboard fallback**: `as_of <= ended_at` 중 최신값 사용

매칭 실패 정책(`--on-unmatched`):
- `warn`(기본): 경고 후 해당 run 제외
- `skip`: 조용히 제외
- `error`: 즉시 실패(exit)

## 실행 예시
```bash
cd /Users/ychoi/Documents/GitHub/Market-Calibration-Agent/apps/single-app

npx tsx scripts/build_run_kpi_jsonl.ts \
  --execution-source scripts/examples/execution_runs_sample.jsonl \
  --metrics-source scripts/examples/metrics_runs_sample.jsonl \
  --output ../../artifacts/ops/kpi_runs_auto.jsonl \
  --on-unmatched warn \
  --time-tolerance-seconds 300
```

이후 바로 리포트 실행:
```bash
python3 ../../scripts/kpi_contract_report.py \
  --input ../../artifacts/ops/kpi_runs_auto.jsonl \
  --stage canary \
  --n 5 \
  --thresholds ../../configs/kpi_contract_thresholds.json \
  --output-json ../../artifacts/ops/kpi_contract_report_canary_auto.json
```

## p1 재검증 스크립트 연동
`p1_revalidate.sh`에서 자동 모드 지원:
```bash
bash scripts/p1_revalidate.sh --auto \
  --execution-source scripts/examples/execution_runs_sample.jsonl \
  --metrics-source scripts/examples/metrics_runs_sample.jsonl \
  --auto-kpi-output ../../artifacts/ops/kpi_runs_auto.jsonl
```
