# Forecasting Improvement Execution Brief

This brief turns the forecasting backlog into an execution plan for MCA.

Related GitHub issues:
- Epic: [#1](https://github.com/tollama/Market-Calibration-Agent/issues/1)
- Backlog pack: [forecasting-improvement-github-issues.md](/Users/yongchoelchoi/Documents/TollamaAI-Github/Market-Calibration-Agent/docs/ops/forecasting-improvement-github-issues.md)

## Objective

Improve MCA forecasting quality for prediction markets in a way that is measurable, reproducible, and safe to promote. The standard is not "better-looking forecasts"; it is better out-of-sample performance versus raw market probabilities and the current MCA baseline, without unacceptable calibration regression.

## Delivery Principles

- Benchmark before model changes.
- Improve the dataset before increasing model complexity.
- Treat raw market probability as the default baseline to beat.
- Promote by segment evidence, not aggregate optimism.
- Preserve runtime safety even when research results are mixed.

## Workstreams

### 1. Benchmark and Evaluation

**Owner**
- Research engineer or ML engineer

**Issues**
- [#2](https://github.com/tollama/Market-Calibration-Agent/issues/2)
- [#3](https://github.com/tollama/Market-Calibration-Agent/issues/3)

**Duration**
- 1 week

**Deliverables**
- Stable offline benchmark contract
- Walk-forward and event-holdout reporting
- Promotion thresholds and pass/fail summary fields

**Exit Criteria**
- Same-seed reruns produce identical benchmark outputs
- Reports show market baseline, current MCA baseline, and segment-level results
- Worst-fold behavior is visible, not hidden by pooled averages

### 2. Dataset and Feature Foundation

**Owner**
- Data engineer with research support

**Issues**
- [#4](https://github.com/tollama/Market-Calibration-Agent/issues/4)
- [#5](https://github.com/tollama/Market-Calibration-Agent/issues/5)
- [#6](https://github.com/tollama/Market-Calibration-Agent/issues/6)
- [#7](https://github.com/tollama/Market-Calibration-Agent/issues/7)

**Duration**
- 1 to 2 weeks

**Deliverables**
- Denser resolved training dataset
- Prediction-market microstructure features
- Event-consensus and disagreement features
- Stronger external enrichment features

**Exit Criteria**
- New dataset is leakage-safe and materially richer than the current one
- Feature specs are documented and tested
- Initial ablations show at least one feature group with stable lift in target segments

### 3. Modeling and Calibration

**Owner**
- ML engineer

**Issues**
- [#8](https://github.com/tollama/Market-Calibration-Agent/issues/8)
- [#9](https://github.com/tollama/Market-Calibration-Agent/issues/9)
- [#10](https://github.com/tollama/Market-Calibration-Agent/issues/10)

**Duration**
- 1 to 2 weeks

**Deliverables**
- Residual-model training path
- Feature ablation and model comparison workflow
- Segment-aware conformal calibration

**Exit Criteria**
- Residual path beats raw market and current MCA baseline on time split and event holdout
- Model comparison artifacts identify which feature groups are actually useful
- Coverage improves or stays within target without excessive interval widening

### 4. Runtime and Monitoring

**Owner**
- Platform engineer with ML support

**Issues**
- [#11](https://github.com/tollama/Market-Calibration-Agent/issues/11)
- [#12](https://github.com/tollama/Market-Calibration-Agent/issues/12)
- [#13](https://github.com/tollama/Market-Calibration-Agent/issues/13)

**Duration**
- 1 week

**Deliverables**
- Evidence-based route selection in the live service
- Forecast-quality dashboards and rollback thresholds
- Baseline research artifact pack committed and documented

**Exit Criteria**
- Runtime chooses route by policy, not by ad hoc defaults
- Monitoring distinguishes quality regression from infrastructure failure
- Artifact pack is reproducible from documented commands

## Recommended Sequence

### Phase 1

- [#2](https://github.com/tollama/Market-Calibration-Agent/issues/2) benchmark contract
- [#3](https://github.com/tollama/Market-Calibration-Agent/issues/3) backtest reporting

### Phase 2

- [#4](https://github.com/tollama/Market-Calibration-Agent/issues/4) resolved dataset
- [#5](https://github.com/tollama/Market-Calibration-Agent/issues/5) microstructure features
- [#7](https://github.com/tollama/Market-Calibration-Agent/issues/7) external enrichment
- [#6](https://github.com/tollama/Market-Calibration-Agent/issues/6) event-consensus features

### Phase 3

- [#8](https://github.com/tollama/Market-Calibration-Agent/issues/8) residual model
- [#9](https://github.com/tollama/Market-Calibration-Agent/issues/9) ablation workflow
- [#10](https://github.com/tollama/Market-Calibration-Agent/issues/10) segment-aware conformal

### Phase 4

- [#11](https://github.com/tollama/Market-Calibration-Agent/issues/11) runtime routing
- [#12](https://github.com/tollama/Market-Calibration-Agent/issues/12) monitoring and gates
- [#13](https://github.com/tollama/Market-Calibration-Agent/issues/13) baseline artifact pack

## Priority View

- `P0`: benchmark contract, reporting, dataset densification, residual-model path
- `P1`: microstructure features, event-consensus features, external enrichment, ablations, conformal, runtime routing, monitoring
- `P2`: baseline artifact pack

## Key Risks

### Risk: Aggregate lift hides segment regressions

**Mitigation**
- Require segment-level review by category, liquidity, TTE, and horizon before promotion

### Risk: Model quality appears to improve only because intervals widen

**Mitigation**
- Track width and coverage jointly in every benchmark review

### Risk: Feature growth increases complexity without durable value

**Mitigation**
- Use the ablation workflow to remove weak feature groups quickly

### Risk: Runtime promotion outruns offline evidence

**Mitigation**
- Block route activation until offline artifacts are attached to the relevant issues

## Definition of Done

- MCA has a reproducible benchmark contract
- MCA has a richer, leakage-safe resolved dataset
- At least one improved model path beats raw market and current MCA baseline on required splits
- Calibration remains within acceptable bounds
- Runtime routing and monitoring are evidence-based
- The baseline artifact pack exists and can be regenerated
