# PRD1 MVP-1 Default Values

This document records default-value choices for PRD1 MVP-1 (batch/read-only) and the rationale for each choice.  
Config compatibility is preserved; PRD1-specific defaults are additive where new keys are required.

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

## Trust score weights

- `trust_score.weights.liquidity_depth: 0.35`
  - Rationale: Keep liquidity depth as the strongest contributor so thin markets are less likely to receive high trust.
- `trust_score.weights.stability: 0.25`
  - Rationale: Preserve stability as a major quality signal while balancing against liquidity and question quality.
- `trust_score.weights.question_quality: 0.25`
  - Rationale: Give prompt/market-structure quality equal weight with stability for PRD1 trust gating.
- `trust_score.weights.manipulation_suspect: 0.15`
  - Rationale: Retain a meaningful but smaller penalty channel so manipulation risk lowers trust without dominating every regime.

## Alert cooldown/thresholds

- `alerts.cooldown_seconds: 900`
  - Rationale: 15-minute cooldown suppresses duplicate alerts during short volatility bursts while preserving actionable cadence.
- `thresholds.mispricing_bps: 100`
  - Rationale: 100 bps (1.00%) is a practical default to avoid triggering on minor microstructure noise.
- `thresholds.max_drawdown_pct: 10.0`
  - Rationale: A 10% drawdown threshold is conservative enough for meaningful stress detection while avoiding frequent churn alerts.
- `thresholds.min_liquidity_usd: 5000`
  - Rationale: Raise liquidity floor so alerts focus on markets with enough depth for signal reliability, consistent with PRD1 low-liquidity risk notes.
- `thresholds.low_oi_confirmation: -0.15`
  - Rationale: Require a meaningful (<= -15%) open-interest contraction as a confirmation signal for band-breach alerts.
- `thresholds.low_ambiguity: 0.35`
  - Rationale: Treat low ambiguity scores as confirmation only when the question framing is clear enough for deterministic interpretation.
- `thresholds.volume_spike: 2.0`
  - Rationale: Use a 2x volume-velocity gate to prioritize alerts with materially elevated activity.
- `min_trust_score: 60.0`
  - Rationale: Suppress alerts for low-trust markets by default while preserving medium/high-trust and missing-trust records for operator review.

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
