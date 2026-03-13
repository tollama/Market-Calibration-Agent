# P1 KPI NO_GO 원인 역추적 및 즉시 보정안

- 작성 일시: 2026-02-27 (KST)
- 기준 리포트: `artifacts/ops/kpi_contract_report_canary.json`
- 입력 런 데이터: `scripts/examples/kpi_runs_sample.jsonl`
- 기준 임계값: `configs/kpi_contract_thresholds.json`

> Advisory-only 고지: 본 문서의 권고는 정보 제공 목적의 운영 파라미터 조정 가이드이며, 투자 권유/법률 자문이 아니다. 실제 거래 실행 및 규제 준수 책임은 사용자/운영 주체에 있다.

## 1) NO_GO를 만든 원인 런/초과 지표 식별

최근 5개 canary 런 중 **1개 WARN**으로 `overall=NO_GO`:

- 문제 런: `canary-2026-02-27T14:00Z`
- 초과 지표(임계값 대비):
  - `brier`: **0.205** (기준 0.200, **+0.005 / +2.5%**)
  - `ece`: **0.082** (기준 0.080, **+0.002 / +2.5%**)
  - `realized_slippage_bps`: **16.5** (기준 15.0, **+1.5bps / +10.0%**)
  - `execution_fail_rate`: 0.019 (기준 0.020, 초과 아님, 단 **임계 근접**)

정리: **슬리피지 급등 + 보정 품질(Brier/ECE) 동시 악화**가 단일 런에서 발생했고, fail-rate도 경계값 근처까지 상승해 품질 여유가 소진됨.

---

## 2) 원인 분류 (근거 기반)

### A. 실행 품질(주원인, high)
- 근거:
  - 문제 런에서 slippage가 16.5bps로 단독 초과 폭이 가장 큼(+1.5bps)
  - 같은 런의 fail-rate가 0.019로 상한(0.02)에 근접
- 해석:
  - 체결 지연/유동성 악화/주문 속도 과다 등 실행 계층 품질 저하 가능성이 큼

### B. 전략 파라미터(공동 원인, medium)
- 근거:
  - `maxPosition`, `ORDER_RATE_LIMIT_PER_MIN`, auto kill-switch latency 파라미터가 현재 비교적 공격적(기본값 상)일 때, 체결 비용 확대와 함께 예측-실현 괴리(Brier/ECE)가 동반 상승 가능
  - 14:00Z 1개 런에서만 동시 악화 후 15:00Z 회복 → 상시 데이터 문제보다는 구간/부하 민감도 이슈에 가깝다

### C. 데이터 품질(가능성 낮음~중간)
- 근거:
  - 제공된 샘플에는 결측/파싱 오류 신호 없음
  - 이상치 런이 단발성(1/5)이라 구조적 데이터 결함 증거는 약함
- 보완 필요:
  - 해당 시각 입력 분포/시장 레짐 변화(유동성·스프레드) 검증은 추가 로그 필요

### D. 임계값 과도(현재 증거 부족)
- 근거:
  - 초과량이 작긴 하나(특히 Brier/ECE), 지표 3개 동시 초과라 단순 임계 완화는 리스크 전가 가능
- 결론:
  - **우선 파라미터/실행 품질 개선 후 재검증**, 임계값 완화는 최후 수단

---

## 3) 즉시 적용 가능한 조정안 (2~3개)

## 조정안 1: 포지션/속도 보수화 (즉시 적용 권장)
- 목적: 체결 충격 및 슬리피지 완화
- 권장값:
  - `RISK_MAX_POSITION_PER_RUN`: `1000000 -> 700000` (약 -30%)
  - `ORDER_RATE_LIMIT_PER_MIN`: `30 -> 20`
- 기대효과:
  - 단기적으로 slippage/실패율 피크를 낮춰 WARN 런 재발 확률 감소

## 조정안 2: 지연 가드 강화 (즉시 적용 권장)
- 목적: 품질 저하 구간을 빠르게 차단
- 권장값:
  - `AUTO_KILL_SWITCH_LATENCY_THRESHOLD_MS`: `30000 -> 20000`
  - `AUTO_KILL_SWITCH_LATENCY_SPIKE_MULTIPLIER`: `3.0 -> 2.5`
- 기대효과:
  - 지연 급증 구간 조기 차단으로 execution_fail_rate/slippage 악화 전파 억제

## 조정안 3: KPI 임계값 정책 (조건부, 무분별 완화 금지)
- 원칙: **현재 공통 임계값 유지 권고**
- 예외(운영위원회 승인 전제):
  - canary 한정으로 일시적 완화가 필요하다면, 단일 값 상향이 아니라
    - 기간 제한(예: 24~48h),
    - 원인 개선 과제 동시 수행,
    - 재강화 롤백 조건을 문서화해야 함.
- 비권장: 근거 없이 상시 완화(품질 저하 상수화 위험)

---

## 4) 재검증(시뮬레이션/샘플 보정) 결과

실데이터가 아닌 샘플 기반 what-if 재검증을 수행함.

### 4.1 파라미터 개선 효과를 반영한 시뮬레이션 입력 생성
- 생성 파일: `scripts/examples/kpi_runs_remediated_sim.jsonl`
- 수정 내용(문제 런 14:00Z만 보정):
  - brier: 0.205 -> 0.198
  - ece: 0.082 -> 0.079
  - slippage: 16.5 -> 14.2
  - fail_rate: 0.019 -> 0.015

### 4.2 리포트 재실행
```bash
cd /Users/ychoi/Documents/GitHub/Market-Calibration-Agent
python3 scripts/kpi_contract_report.py \
  --input scripts/examples/kpi_runs_remediated_sim.jsonl \
  --stage canary \
  --n 5 \
  --thresholds configs/kpi_contract_thresholds.json \
  --output-json artifacts/ops/kpi_contract_report_canary_remediated_sim.json
```

결과:
- `overall=GO`
- `warn_runs=0/5`

참고: 임계값 완화 what-if(`configs/kpi_contract_thresholds_canary_temp_relaxed.json`)도 실험 시 GO가 가능했으나, 이는 문제를 기준 이동으로 흡수하는 방식이라 기본 권고안으로 채택하지 않음.

한계:
- 본 재검증은 샘플/시뮬레이션 기반이며, 실거래 데이터(호가깊이/지연/체결로그)로 동일 재현 확인이 필요.

---

## 5) GO 전환 조건

아래 조건을 **모두** 만족 시 GO 전환:

1. 보수 파라미터 적용 후 최근 5-run 재리포트에서 `overall=GO`
2. 문제 구간과 유사한 부하/시장 조건 재현 테스트에서
   - `realized_slippage_bps <= 15.0`
   - `execution_fail_rate <= 0.02`
3. 최소 24시간 canary 관측에서 WARN 런 0건(또는 사전 합의한 허용 범위 이하)
4. 임계값 완화 없이(또는 기간 제한·롤백 조건 명시된 상태로) 동일 결과 재현

---

## 6) 운영 실행 절차(명령)

```bash
# 1) 환경값 조정 (예시)
cd /Users/ychoi/Documents/GitHub/Market-Calibration-Agent/apps/single-app
# .env에 아래 값 반영
# RISK_MAX_POSITION_PER_RUN=700000
# ORDER_RATE_LIMIT_PER_MIN=20
# AUTO_KILL_SWITCH_LATENCY_THRESHOLD_MS=20000
# AUTO_KILL_SWITCH_LATENCY_SPIKE_MULTIPLIER=2.5

# 2) 서비스 재기동 (환경 반영)
docker compose up -d postgres redis
# (앱/워커는 운영 방식에 맞춰 재시작)

# 3) KPI 리포트 재실행
cd /Users/ychoi/Documents/GitHub/Market-Calibration-Agent
python3 scripts/kpi_contract_report.py \
  --input scripts/examples/kpi_runs_sample.jsonl \
  --stage canary \
  --n 5 \
  --thresholds configs/kpi_contract_thresholds.json \
  --output-json artifacts/ops/kpi_contract_report_canary.json

# 4) (옵션) 시뮬레이션 검증
python3 scripts/kpi_contract_report.py \
  --input scripts/examples/kpi_runs_remediated_sim.jsonl \
  --stage canary \
  --n 5 \
  --thresholds configs/kpi_contract_thresholds.json \
  --output-json artifacts/ops/kpi_contract_report_canary_remediated_sim.json
```
