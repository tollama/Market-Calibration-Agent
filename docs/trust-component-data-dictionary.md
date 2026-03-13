# Trust Score Component Data Dictionary

Trust Score is computed from four independent components, each normalised to [0, 1]. This document defines each component's meaning, data source, formula, fallback behaviour, and configuration knobs.

## Formula

```
trust_score = 100 * (w_liq * liquidity_depth
                   + w_stab * stability
                   + w_qual * question_quality
                   + w_manip * (1 - manipulation_suspect))
```

Default weights (configurable in `configs/default.yaml` under `trust_score.weights`):

| Component | Weight | Key |
| --- | ---: | --- |
| liquidity_depth | 0.35 | `trust_score.weights.liquidity_depth` |
| stability | 0.25 | `trust_score.weights.stability` |
| question_quality | 0.25 | `trust_score.weights.question_quality` |
| manipulation_suspect | 0.15 | `trust_score.weights.manipulation_suspect` |

## Components

### liquidity_depth

| Property | Value |
| --- | --- |
| Range | [0, 1] |
| Interpretation | 0 = extremely thin market; 1 = deep, liquid market |
| Data sources | `liquidity_bucket` (LOW/MID/HIGH), `volume_24h`, `open_interest` |
| Formula | `0.4 * bucket_base + 0.6 * min(max(volume, oi) / liquidity_high, 1.0)` |
| Bucket base values | LOW = 0.2, MID = 0.5, HIGH = 0.8 |
| Fallback | 0.5 when all fields are missing |
| Config | `trust_score.component_derivation.liquidity_high` (default: 100000) |

### stability

| Property | Value |
| --- | --- |
| Range | [0, 1] |
| Interpretation | 0 = highly volatile; 1 = very stable price |
| Data sources | `vol` (rolling standard deviation of returns from `features/build_features.py`) |
| Formula | `1.0 - min(vol / volatility_ceiling, 1.0)` |
| Fallback | 0.5 when `vol` is missing |
| Config | `trust_score.component_derivation.volatility_ceiling` (default: 0.3) |

### question_quality

| Property | Value |
| --- | --- |
| Range | [0, 1] |
| Interpretation | 0 = highly ambiguous/risky question; 1 = clear, well-defined question |
| Data sources | `ambiguity_score`, `resolution_risk_score` (from `QuestionQualityAgent` via `llm/schemas.py`) |
| Formula | `1.0 - (0.6 * ambiguity_score + 0.4 * resolution_risk_score)` |
| Partial data | Uses whichever score is available if only one is present |
| Fallback | 0.5 when both scores are missing |
| Config | None (weights are hardcoded; agent output format is stable) |

### manipulation_suspect

| Property | Value |
| --- | --- |
| Range | [0, 1] |
| Interpretation | 0 = no manipulation evidence; 1 = strong manipulation signals |
| Data sources | `oi_change` (open interest change rate), `volume_velocity` (from `features/build_features.py`) |
| Formula | `max(abs(oi_change) / oi_spike_threshold, abs(volume_velocity) / velocity_spike_threshold)`, clipped to [0, 1] |
| Inversion | This component is **inverted** in the trust score formula: `(1 - manipulation_suspect)` |
| Fallback | 0.0 (no evidence = no suspicion) when both fields are missing |
| Config | `trust_score.component_derivation.oi_spike_threshold` (default: 0.30), `trust_score.component_derivation.velocity_spike_threshold` (default: 3.0) |

## Configuration

All derivation thresholds live in `configs/default.yaml`:

```yaml
trust_score:
  component_derivation:
    liquidity_high: 100000        # Volume/OI normalisation ceiling
    volatility_ceiling: 0.3       # Max vol before stability = 0
    oi_spike_threshold: 0.30      # OI change rate normalisation
    velocity_spike_threshold: 3.0 # Volume velocity normalisation
```

## Derivation priority

1. **Explicit values**: If a row already contains a component key (e.g. `liquidity_depth`), that value is used directly.
2. **Feature derivation**: If no explicit component keys exist, `derive_trust_components()` computes all four from feature columns.
3. **Fallback defaults**: If feature columns are also missing, each function returns its documented fallback value (0.5 for most, 0.0 for `manipulation_suspect`).

## Implementation

- Component derivation: `calibration/trust_components.py`
- Trust score formula: `calibration/trust_score.py`
- Scoreboard integration: `pipelines/build_scoreboard_artifacts.py` (`_average_trust_components`)
