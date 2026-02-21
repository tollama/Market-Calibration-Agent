# Live Demo GUI Runbook

## 목적 / Purpose
실시간 데모용 API + GUI(Streamlit) 실행 절차입니다.

## Prerequisites
- Python 3.11
- Local shell access

## Quick Start
```bash
cd /Users/ychoi/Documents/GitHub/Market-Calibration-Agent
./scripts/run_live_demo.sh
```

- API: `http://127.0.0.1:8000`
- GUI: `http://127.0.0.1:8501`

## Demo Script (Presenter Flow)
1. **Overview** 탭에서 `/scoreboard`, `/alerts` 확인
2. **Market Detail** 탭에서 시장 선택 → q10/q50/q90 forecast 확인
3. 같은 화면에서 최신 postmortem 확인
4. **Compare** 탭에서 baseline vs tollama 비교 실행
5. **Observability** 탭에서 `/metrics` 요약 확인

## Notes
- 안전 문구: "투자 조언이 아닙니다 / Not investment advice"
- `/tsfm/forecast`는 기존 canonical endpoint 유지
- 비교 endpoint는 내부적으로 동일 forecast service를 재사용
