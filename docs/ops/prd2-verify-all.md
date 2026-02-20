# PRD2 one-command verification

## 목적
`PRD2` 릴리스 전 필수 검증(유닛/통합 선택, 성능 벤치, 릴리스 감사)을 한 번에 고정 순서로 실행합니다.

## 엔트리포인트
```bash
scripts/prd2_verify_all.sh
```

실행 순서(결정적):
1. PRD2 unit selection
2. PRD2 integration selection
3. PRD2 performance benchmark
4. PRD2 release audit

## 출력 아티팩트
- 요약 JSON: `artifacts/prd2_verify_summary.json`
- 단계별 로그: `artifacts/prd2_verify_logs/*.log`

`artifacts/prd2_verify_summary.json` 예시 필드:
- `overall_status`: `success|failed`
- `dry_run`: `0|1`
- `steps[]`: `status`, `exit_code`, `elapsed_s`, `log_path`

## Local usage
```bash
# 실제 실행
scripts/prd2_verify_all.sh

# Python binary 지정 (권장: 3.11+)
PRD2_VERIFY_PYTHON_BIN=python3.11 scripts/prd2_verify_all.sh

# dry run (명령 실행 없이 순서/출력 구조 점검)
PRD2_VERIFY_DRY_RUN=1 scripts/prd2_verify_all.sh
```

실패 시:
- 스크립트는 non-zero exit code로 종료합니다.
- 실패 단계는 summary JSON과 해당 step 로그에서 확인합니다.

## CI usage
GitHub Actions 등에서 아래처럼 실행합니다.

```bash
pip install -e .[dev]
scripts/prd2_verify_all.sh
```

CI 업로드 권장 아티팩트:
- `artifacts/prd2_verify_summary.json`
- `artifacts/prd2_verify_logs/`

예: 실패 여부를 요약 JSON으로 재판정하려면 `overall_status == "success"`를 확인합니다.
