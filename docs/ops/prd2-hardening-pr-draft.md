# PR Draft: PRD2 TSFM Hardening and Regression Stabilization

## 배경
- PRD2/Tollama 경로에서 `/tsfm/forecast` 안정성·보안 강화, 회귀 게이트 강화, 운영 하드닝 문서/체크리스트 정리가 필요했습니다.
- 최근 변경으로 TSFM 입력 검증, fallback·회귀 동작, 운영 단계 실패 계약, OpenAPI smoke가 추가되었고, CI에서도 하드닝 게이트를 반영해야 합니다.
- 요청사항인 "남은 작업 실행"에 맞춰, P1 핵심 회귀 최소 재검증 후 의미 단위로 커밋하여 리뷰 가능성을 높였습니다.

## 변경사항
- **테스트 보강**
  - `tests/unit/test_tsfm_runner_service.py`: 입력 유효성 경로(점수열 길이/형식·freq·타임스탬프 간격 등), fallback 동작, baseline/에러 처리 커버 강화.
  - `tests/unit/test_api_tsfm_forecast.py`: API 레이어에서 잘못된 요청(유효하지 않은 길이/빈값/freq/y_ts mismatch 등) 실패 케이스 추가.
  - `tests/unit/test_api_tsfm_auth.py`: placeholder 토큰 거부 케이스 추가.
  - `tests/unit/test_api_tsfm_rate_limit.py`: 토큰 값 고정 테스트 케이스 정합성 보정.
  - `tests/unit/test_derived_store_loaders.py`: 잘못된 JSON 라인·빈 라인 처리 지표 카운트 검증.
  - `tests/unit/test_api_readonly.py`: window 파라미터 입력 검증 추가.
  - 신규 테스트: `test_daily_job_failure_contracts.py`, `test_openapi_smoke.py`, `test_tsfm_service_concurrency.py`.

- **CI/오퍼레이션 강화**
  - `.github/workflows/ci.yml`: 하드닝 게이트에서 OpenAPI smoke(로컬 API) 단계 추가.

- **문서/운영 가이드 업데이트**
  - `docs/ops/tsfm-hardening-gate.md` 신규 작성 (게이트 수행/장애 대응).
  - `docs/ops/tsfm-forecast-operational-policy.md` 신규 작성 (운영 정책/롤백 기준).
  - PRD2 게이트/체크리스트/런북/의존성 고정 가이드 최신화.

- **코드/툴링**
  - `api/*`, `pipelines/*`, `runners/tsfm_service.py`: TSFM 입출력 유효성, fallback/메타데이터 계약, 파이프라인 실패 분류(복구 가능한 실패/치명 실패), 계약 처리 정합성 보강.
  - `scripts/openapi_smoke.py`: OpenAPI 계약 smoke(필수 경로+메서드) 도구 추가.
  - `scripts/rollout_hardening_gate.sh`: 롤아웃 하드닝 게이트 구현(라이브 데모/보안/메트릭/벤치/오픈API 단계 자동 실행).

## 검증(최소 재검증)
- P1 핵심 묶음 재실행:
  - `python3.11 -m pytest -q tests/unit/test_i01_acceptance.py tests/unit/test_i15_acceptance.py tests/unit/test_i20_acceptance.py tests/unit/test_api_tsfm_auth.py tests/unit/test_api_tsfm_rate_limit.py tests/unit/test_api_tsfm_forecast.py tests/unit/test_tsfm_runner_service.py tests/unit/test_openapi_smoke.py tests/unit/test_tsfm_service_concurrency.py tests/unit/test_daily_job_failure_contracts.py`
  - 결과: **PASS (100% 통과)**
- PRD2 유닛 묶음 재실행:
  - `python3.11 -m pytest -q tests/unit/test_tsfm_runner_service.py tests/unit/test_api_tsfm_forecast.py tests/unit/test_tsfm_model_license_guard.py tests/unit/test_baseline_bands.py tests/unit/test_tsfm_base_contract.py`
  - 결과: **PASS (100% 통과)**

## 리스크/영향
- OpenAPI smoke는 로컬 API 실행을 전제하므로 CI 구성에서 API 기동/기준 URL 타이밍 의존성이 생김.
- `rollout_hardening_gate.sh`는 외부/환경 의존성이 높아(포트/토큰/파생 데이터 경로) 운영환경에서 토큰/권한 정책/실행 경로를 정확히 맞춰야 함.
- Concurrency/fallback 경로를 더 많이 다루는 변경이므로, 실제 운영 트래픽에서 캐시/회로회복 동작(스레드 안전성, 상태 저장)이 추가 모니터링 대상.

## 체크리스트
- [x] 커밋 전/후 `git status` 및 `git log` 확인
- [x] P1 핵심 회귀 테스트 묶음 재실행 및 통과 기록
- [x] 테스트/CI/문서/코드로 분할 커밋
- [ ] `python3.11 -m pytest -q tests/unit` 전체 런 (선택: 더 긴 전체 회귀)
- [ ] `scripts/rollout_hardening_gate.sh` 실제 운영 환경에서 `TSFM_FORECAST_API_TOKEN` 유효값으로 1회 이상 실행

## 생성된 커밋
- `4b1d452` test: add tsfm hardening and robustness coverage
- `9aa010b` ci: hardening gate extends openapi smoke and TSFM checks
- `742f2e0` docs: add tsfm hardening docs and release checklist updates
- `7ac0976` code: harden tsfm api validation, fallback handling, and rollout gate tooling
