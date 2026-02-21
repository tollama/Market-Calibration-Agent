# Live Demo GUI Runbook

## 목적 / Purpose
실시간 데모용 API + GUI(Streamlit) 실행 절차입니다.

## Prerequisites
- Python 3.11+
- Local shell access
- 기본 포트: API `8000`, GUI `8501` (환경변수로 변경 가능)

## Quick Start
```bash
cd /Users/ychoi/Documents/GitHub/Market-Calibration-Agent
./scripts/run_live_demo.sh
```

런처가 자동으로 수행하는 작업:
- Python 버전(3.11+) 확인
- 런타임 의존성 설치
- API 서버 실행 및 health 확인(기본 `/metrics`, 최대 30초 대기)
- 포트 점유 상태 안내

기본 접속 주소:
- API: `http://127.0.0.1:8000`
- GUI: `http://127.0.0.1:8501`

## Stop
다른 터미널에서 아래 명령으로 데모 프로세스 정리:

```bash
cd /Users/ychoi/Documents/GitHub/Market-Calibration-Agent
./scripts/stop_live_demo.sh
```

`stop_live_demo.sh`는 가능한 경우 다음 순서로 정리합니다:
1. pid 파일 기반 종료 (`.demo_state/api.pid`, `.demo_state/gui.pid`)
2. 남은 프로세스를 포트 기준(`8000`, `8501`)으로 추가 종료 시도

## Optional Environment Variables
- `PYTHON_BIN` (default: `python3.11`)
- `API_HOST` (default: `127.0.0.1`)
- `API_PORT` (default: `8000`)
- `GUI_PORT` (default: `8501`)
- `HEALTH_PATH` (default: `/metrics`)
- `HEALTH_TIMEOUT_SEC` (default: `30`)
- `DEMO_STATE_DIR` (default: `.demo_state`)

예시:
```bash
API_PORT=18000 GUI_PORT=18501 HEALTH_TIMEOUT_SEC=45 ./scripts/run_live_demo.sh
```

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
