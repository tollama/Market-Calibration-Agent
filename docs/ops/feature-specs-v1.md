# Feature Specs v1.1 (MCA → single-app)

> 목적: PRD1 기반 핵심 6개 피처에 대해 **정확한 컬럼 스키마**, **백테스트 지표**, **Go/No-Go 채택 기준**을 표준화한다.
> 범위: `features/build_features.py`에서 계산되는 피처 중 v1.1 우선 이관 대상 6개 (`returns`, `vol`, `volume_velocity`, `oi_change`, `tte_seconds`, `liquidity_bucket`).

---

## 공통 입력 스키마 (Baseline)

| Column | 타입 | 단위 | 설명 | 소스 경로 |
|---|---|---:|---|---|
| `market_id` | string | - | 시장 식별자 | `pipelines/build_cutoff_snapshots.py` 결과(`context.state.cutoff_snapshots`) |
| `ts` | datetime(UTC) | ISO8601 | 관측 시각 | `cutoff_snapshot_rows[].ts` |
| `p_yes` | float | [0,1] | YES 확률 | 정규화 스냅샷 행 (`snapshot_rows`/`normalized_records`) |
| `volume_24h` | float | USD(24h 누적) | 거래량 | 동일 |
| `open_interest` | float | USD | 미결제약정 | 동일 |
| `tte_seconds` | float (nullable) | sec | 만기까지 잔여 시간(있으면 우선 사용) | 동일 |
| `end_ts` / `event_end_ts` / `resolution_ts` | datetime(UTC, nullable) | ISO8601 | 만기 시각 후보 | 동일 |

공통 파라미터(기본값):
- `vol_window=5`
- 정렬: `market_id, ts` (`mergesort`, deterministic)
- 결측/Inf 정리: `_clean_numeric(..., fill_value=0.0)`

---

## Feature 1) returns

| 항목 | 내용 |
|---|---|
| Feature Name / 목적 | `returns` / 가격 변화율(단기 방향성) 포착 |
| Input Columns | `market_id:string`, `ts:datetime`, `p_yes:float[0,1]` (`features/build_features.py`) |
| Derived Columns | `prev_price = groupby(market_id).shift(1)`<br>`returns = (p_yes - prev_price) / prev_price (prev_price!=0)`<br>`clean: NaN/Inf → 0.0` |
| Leakage Guard 규칙 | (1) 반드시 `shift(1)` 기반 과거값만 사용<br>(2) `ts` 오름차순 정렬 후 계산<br>(3) 백테스트 split 경계에서 미래 row 참조 금지<br>(4) event 단위 holdout 시 동일 event 내 train/test 혼입 금지 |
| Backtest Metrics (필수/보조) | **필수:** OOS Brier, OOS LogLoss, ECE(10-bin)<br>**보조:** HitRate(sign), Spearman IC(returns vs future error reduction), Turnover impact |
| Go/No-Go 기준 | **Go:** 기준모델 대비 OOS Brier ≥ **1.0% 개선**, ECE 악화 ≤ **0.005**, LogLoss 악화 없음<br>**No-Go:** 개선 미달 또는 ECE +0.005 초과 악화 |
| 실패 시 롤백 기준 | 2개 이상 연속 워크포워드 윈도우에서 Brier 개선 < 0 또는 ECE 악화 > 0.01 발생 시 즉시 제외 |
| MCA 삽입 포인트 + single-app 이관 포인트 | **MCA:** `features/build_features.py` (`frame["returns"]`)<br>**single-app:** `apps/single-app/src/lib/features/returns.ts`(신규 권장) + worker 호출 경로 `apps/single-app/src/worker/index.ts` |

---

## Feature 2) vol

| 항목 | 내용 |
|---|---|
| Feature Name / 목적 | `vol` / 단기 변동성(불확실성 강도) 추정 |
| Input Columns | `market_id`, `ts`, `returns` |
| Derived Columns | `rolling std(returns, window=5, min_periods=2, ddof=0)` by `market_id`<br>`clean: NaN/Inf → 0.0` |
| Leakage Guard 규칙 | (1) centered window 금지(후행 window만 허용)<br>(2) window 내부에 미래 시점 포함 금지<br>(3) 고빈도 overlay 사용 시 동일 `market_id, ts` exact match만 override |
| Backtest Metrics (필수/보조) | **필수:** Interval Coverage Error(목표 대비), ECE, OOS Brier<br>**보조:** CRPS(가능 시), Quantile crossing rate, tail-bin calibration |
| Go/No-Go 기준 | **Go:** coverage 오차 절대값 ≤ **2.0%p**, crossing rate ≤ **0.5%**, Brier ≥ **0.5% 개선**<br>**No-Go:** coverage 오차 > 3.0%p 또는 crossing rate > 1.0% |
| 실패 시 롤백 기준 | canary 24h 내 fallback_rate +3%p 이상 증가 또는 invalid output 이벤트 발생 시 롤백 |
| MCA 삽입 포인트 + single-app 이관 포인트 | **MCA:** `features/build_features.py` (`frame["vol"]`)<br>**single-app:** `apps/single-app/src/lib/features/volatility.ts`(신규 권장), TSFM 후처리 지표 연결 `runners/tsfm_service.py` 대응 레이어 |

---

## Feature 3) volume_velocity

| 항목 | 내용 |
|---|---|
| Feature Name / 목적 | `volume_velocity` / 거래량 변화 속도(유동성 충격) 감지 |
| Input Columns | `market_id`, `ts`, `volume_24h` |
| Derived Columns | `prev_volume = shift(1)`<br>`delta_volume = volume_24h - prev_volume`<br>`delta_seconds = ts - prev_ts`<br>`volume_velocity = delta_volume / delta_seconds (delta_seconds>0)`<br>`clean: NaN/Inf → 0.0` |
| Leakage Guard 규칙 | (1) `delta_seconds<=0`은 사용 금지(0 처리)<br>(2) 동일 timestamp 중복 row는 deterministic dedup 후 계산<br>(3) 재샘플링 시 미래 bar 합산 금지 |
| Backtest Metrics (필수/보조) | **필수:** Alert Precision@K, Brier, PSI(분포 안정성)<br>**보조:** Recall@K, latency-to-alert, false positive ratio |
| Go/No-Go 기준 | **Go:** Precision@K ≥ **0.58**, PSI ≤ **0.2**, Brier ≥ **0.5% 개선**<br>**No-Go:** PSI > 0.25 또는 Precision@K < 0.52 |
| 실패 시 롤백 기준 | 운영 3일 평균 false positive ratio가 베이스라인 대비 +20%p 초과 시 비활성화 |
| MCA 삽입 포인트 + single-app 이관 포인트 | **MCA:** `features/build_features.py` (`frame["volume_velocity"]`)<br>**single-app:** `apps/single-app/src/lib/features/volume-velocity.ts`(신규 권장), alert 스코어 계산부(`apps/single-app/src/lib/`) 연동 |

---

## Feature 4) oi_change

| 항목 | 내용 |
|---|---|
| Feature Name / 목적 | `oi_change` / 포지션 축적/해소 신호 추적 |
| Input Columns | `market_id`, `open_interest`, `ts` |
| Derived Columns | `prev_oi = shift(1)`<br>`oi_change = (open_interest - prev_oi) / prev_oi (prev_oi!=0)`<br>`clean: NaN/Inf → 0.0` |
| Leakage Guard 규칙 | (1) OI 업데이트 지연(배치 지연) 반영: 타임스탬프 역전 row 제거<br>(2) market 간 조인 금지(시장 독립 계산)<br>(3) label 시점 이후 OI 수정분 재반영 금지 |
| Backtest Metrics (필수/보조) | **필수:** OOS Brier, Segment ECE(유동성 버킷별), AUC(이진 이벤트면)<br>**보조:** KS 통계, 안정성(rolling mean/var drift) |
| Go/No-Go 기준 | **Go:** 전체 Brier ≥ **0.7% 개선** + 저유동성 구간 ECE 악화 없음(≤ +0.003)<br>**No-Go:** 저유동성 구간에서 ECE +0.005 초과 악화 |
| 실패 시 롤백 기준 | segment(LOW liquidity) 성능 악화가 2개 이상 연속 윈도우에서 재현되면 제거 |
| MCA 삽입 포인트 + single-app 이관 포인트 | **MCA:** `features/build_features.py` (`frame["oi_change"]`)<br>**single-app:** `apps/single-app/src/lib/features/oi-change.ts`(신규 권장), 리스크 가드(`apps/single-app/src/lib/risk-guard.ts`) 참고 신호로 선택적 연결 |

---

## Feature 5) tte_seconds

| 항목 | 내용 |
|---|---|
| Feature Name / 목적 | `tte_seconds` / 만기 근접도(시간 구조) 반영 |
| Input Columns | `ts`, `tte_seconds(nullable)`, `end_ts/event_end_ts/resolution_ts(nullable)` |
| Derived Columns | 우선순위: (1) 입력 `tte_seconds`가 유효하면 사용 (2) 아니면 `end_ts_candidate - ts`<br>`clip(lower=0.0)` 후 float 변환 |
| Leakage Guard 규칙 | (1) `end_ts`는 사전 고정된 이벤트 메타만 사용(사후 수정본 금지)<br>(2) 음수 TTE는 0으로 clip<br>(3) 해상도 변경 시 look-ahead 재정렬 금지 |
| Backtest Metrics (필수/보조) | **필수:** TTE bucket별 Brier/ECE, 전체 LogLoss<br>**보조:** near-expiry(예: <1h) 구간 calibration slope/intercept |
| Go/No-Go 기준 | **Go:** near-expiry bucket Brier ≥ **1.5% 개선**, 전체 LogLoss 비악화, bucket별 ECE 평균 ≤ **0.03**<br>**No-Go:** near-expiry 개선 없음 + bucket ECE 평균 > 0.04 |
| 실패 시 롤백 기준 | 만기 임박 구간에서 경고등급 오탐이 baseline 대비 +15%p 증가 시 롤백 |
| MCA 삽입 포인트 + single-app 이관 포인트 | **MCA:** `_build_tte_seconds()` in `features/build_features.py`<br>**single-app:** `apps/single-app/src/lib/features/tte.ts`(신규 권장), alert/feed 단계(`pipelines/build_alert_feed.py` 대응 로직)로 이관 |

---

## Feature 6) liquidity_bucket

| 항목 | 내용 |
|---|---|
| Feature Name / 목적 | `liquidity_bucket` / 시장 유동성 수준을 구간화해 캘리브레이션·리스크 가드·모니터링의 세그먼트 기준으로 사용 |
| Input Columns | `market_id:string` (식별자, baseline snapshot)<br>`ts:datetime(UTC)` (관측 시각, baseline snapshot)<br>`volume_24h:float, USD` (24h 누적 거래량, snapshot 정규화 행)<br>`open_interest:float, USD` (미결제약정, snapshot 정규화 행) |
| Derived Columns | `base_liquidity = max(volume_24h, open_interest)`<br>고정 임계값 구간화(코드 기준 단일 표준): `LOW` (`base_liquidity < liquidity_low`), `MID` (`liquidity_low <= base_liquidity < liquidity_high`), `HIGH` (`base_liquidity >= liquidity_high`)<br>기본 임계값: `liquidity_low=10,000`, `liquidity_high=100,000` (`pipelines/build_feature_frame.py`)<br>보조 정수 인코딩: `liquidity_bucket_id` = {LOW:0, MID:1, HIGH:2} |
| Leakage Guard 규칙 | (1) bucket 산출은 항상 **현재 시점 입력만** 사용(미래 `volume_24h/open_interest` 참조 금지)<br>(2) 분위수 재학습/시점별 동적 경계 계산 금지(운영/백테스트 모두 고정 threshold 사용)<br>(3) 이벤트 종료 후 보정된 거래량/OI 재기록분은 해당 시점 feature 재계산에 사용 금지(as-of snapshot only)<br>(4) `market_id` 간 교차 정렬/집계 시 timestamp mismatch join 금지(동일 `ts` 단면만 허용) |
| Backtest Metrics (필수/보조) | **필수:** bucket별 OOS Brier(LOW/MID/HIGH), bucket별 ECE(10-bin), 전체 대비 worst-bucket 성능 편차<br>**보조:** bucket 분포 안정성(PSI), bucket별 샘플 비율 드리프트, bucket-conditioned LogLoss |
| Go/No-Go 기준 | **Go:** (a) LOW bucket OOS Brier **≥ 1.0% 개선**, (b) 전체 ECE 비악화(ΔECE ≤ +0.003), (c) worst-bucket Brier 악화 없음(Δ≤0)<br>**No-Go:** LOW bucket 개선 미달 또는 특정 bucket ECE가 baseline 대비 +0.005 초과 악화, 혹은 PSI > 0.25 |
| 실패 시 롤백 기준 | 카나리/운영에서 2개 연속 평가 윈도우 동안 (1) LOW bucket Brier 개선 < 0, 또는 (2) bucket 불균형(단일 bucket 비중 > 80%) 발생 시 `liquidity_bucket` 비활성화 및 이전 세그먼트 규칙으로 롤백 |
| MCA 삽입 포인트 + single-app 이관 포인트 | **MCA:** `features/build_features.py` 내 `volume_24h`, `open_interest` 정리 직후 `frame["liquidity_bucket"]`, `frame["liquidity_bucket_id"]` 생성 블록 추가(returns/vol 파생 전 공통 세그먼트로 노출)<br>**single-app:** `apps/single-app/src/lib/features/liquidity-bucket.ts`(신규)에서 동일 계산/경계 로직 구현, `apps/single-app/src/worker/index.ts` feature build 단계에 주입, `apps/single-app/src/lib/risk-guard.ts` 및 calibration 입력 스키마에 세그먼트 키로 이관 |

### 운영 조정 절차 (liquidity threshold)

1. `configs/default.yaml`의 `features.liquidity_thresholds.low/high` 값을 변경한다. (기본값: `10000/100000`)
2. 긴급 조정이 필요하면 런타임 환경변수 `MCA_LIQUIDITY_LOW`, `MCA_LIQUIDITY_HIGH`로 일시 오버라이드한다.
3. 배포 전 `pytest tests/unit/test_feature_stage.py tests/unit/test_feature_builder.py`를 실행해 기본/커스텀/경계값 동작을 확인한다.
4. 배포 후 scoreboard에서 `by_liquidity_bucket` 분포(단일 bucket 쏠림 > 80% 여부)와 LOW bucket Brier 변화량을 1개 평가 윈도우 이상 모니터링한다.

---

## 공통 평가 프로토콜 (워크포워드 + 카나리 + 통계 유의성)

### 1) 워크포워드(필수)
- 기본: **expanding train + rolling test**
- 예시: train 28일 / test 7일, 4~8개 윈도우
- 분할 단위: 시간 우선, 필요 시 event-holdout 병행
- 산출: 윈도우별 Brier/LogLoss/ECE + 분산 + worst-window

### 2) 카나리(필수)
- 단계: `canary_5 -> canary_25 -> full_100`
- 관측 창: 최소 30분(5%), 60분(25%) clean window
- 운영 게이트 연동: `docs/ops/tsfm-canary-rollout-runbook.md`, `scripts/evaluate_tsfm_canary_gate.py`
- 즉시 롤백 조건: error_rate, fallback_rate, invalid output 임계치 초과

### 3) 통계 유의성 체크(필수)
- 1차: 윈도우별 개선치의 부트스트랩 95% CI (0 상회 여부)
- 2차: 페어드 테스트(예: Diebold-Mariano 또는 permutation test)로 기준모델 대비 유의성 확인
- 채택 원칙: **효과 크기 + 유의성 + 운영 안정성** 3요건 동시 충족

### 4) 최종 채택 판정
- **Go:** (a) 정량 기준 충족, (b) 누수 없음, (c) 카나리 안정 통과
- **Conditional Go:** 성능 충족 + 운영 리스크 경미(완화책/모니터링 조건부)
- **No-Go:** 기준 미충족 또는 안정성 결함 재현

---

## 부록: 구현 체크리스트 (요약)
- [ ] 스키마 계약 확정 (`input/derived column`, 타입, 단위)
- [ ] leakage test 케이스 추가 (split boundary / event holdout)
- [ ] backtest 리포트 템플릿 고정 (필수/보조 지표)
- [ ] canary gate 연동 및 rollback runbook 연결
- [ ] single-app 포팅 파일/모듈 경로 확정
