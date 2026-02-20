# PRD1 MVP-1 Default Values

This document records default-value choices for PRD1 MVP-1 (batch/read-only) and the rationale for each choice.  
YAML schema shape is unchanged; only values were adjusted.

## Calibration windows

- `calibration.lookback_minutes: 129600`
  - Rationale: PRD1 examples and API defaults use a `90d` analysis window. `129600` minutes equals 90 days and makes calibration/scoreboard outputs consistent with MVP-1 expectations.
- `calibration.update_interval_seconds: 3600`
  - Rationale: MVP-1 is batch-oriented, but hourly cadence is still practical for stable refreshes without near-real-time operational cost.

## Confidence thresholds

- `calibration.confidence_threshold: 0.70`
  - Rationale: Raise confidence gating from 0.60 to 0.70 to reduce low-quality signal promotion, matching PRD1 emphasis on trust-gated outputs.
- `calibration.min_volume: 500.0`
  - Rationale: Increase minimum market activity required for calibration inputs so sparse/noisy markets are less likely to influence confidence decisions.

## Alert cooldown/thresholds

- `alerts.cooldown_seconds: 900`
  - Rationale: 15-minute cooldown suppresses duplicate alerts during short volatility bursts while preserving actionable cadence.
- `thresholds.mispricing_bps: 100`
  - Rationale: 100 bps (1.00%) is a practical default to avoid triggering on minor microstructure noise.
- `thresholds.max_drawdown_pct: 10.0`
  - Rationale: A 10% drawdown threshold is conservative enough for meaningful stress detection while avoiding frequent churn alerts.
- `thresholds.min_liquidity_usd: 5000`
  - Rationale: Raise liquidity floor so alerts focus on markets with enough depth for signal reliability, consistent with PRD1 low-liquidity risk notes.

## Model profile defaults

- `active_model: baseline`
  - Rationale: Keep baseline model as the operational default for MVP-1 stability and reproducibility.
- `models.baseline.family: logistic`
  - Rationale: Retain logistic as a simple, interpretable default for batch calibration workflows.
- `models.baseline.features: [returns, vol, volume_velocity, oi_change, tte, liquidity_bucket]`
  - Rationale: Align with PRD1 minimum feature set (`returns`, `vol`, `volume_velocity`, `oi_change`, `tte`, `liquidity_bucket`) for MVP-1.
- `models.baseline.regularization: 0.20`
  - Rationale: Slightly stronger regularization than prior default to improve robustness under mixed market regimes.
- `models.fallback.family: isotonic`
  - Rationale: Keep isotonic fallback for monotonic probability calibration behavior when baseline is not suitable.
- `models.fallback.features: [returns, vol, volume_velocity, tte, liquidity_bucket]`
  - Rationale: Use a reduced robust subset that can still operate when some market-structure features are incomplete.
- `models.fallback.min_samples: 1000`
  - Rationale: Increase sample floor to avoid unstable fallback calibration on thin historical slices.
