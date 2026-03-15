---
name: Forecasting Epic
about: Create an epic for improving MCA forecasting quality in prediction markets
title: "epic(forecasting): "
labels: ["forecasting", "prediction-markets", "research"]
assignees: []
---

## Summary

Describe the forecasting improvement program at a high level.

## Goal

State the user-facing or business-facing outcome this epic should achieve.

## Problem

Describe the current forecasting quality gap and why it matters.

## Scope

- In scope:
- In scope:
- Out of scope:

## Success Metrics

- [ ] Brier improvement versus raw market baseline is defined
- [ ] Log-loss improvement versus current MCA baseline is defined
- [ ] Calibration constraints are defined
- [ ] Segment-level evaluation requirements are defined

## Milestones

- [ ] Forecast Benchmark
- [ ] Dataset and Features
- [ ] Model and Calibration
- [ ] Runtime and Monitoring

## Child Issues

- [ ] T1 Build Forecasting Benchmark Contract
- [ ] T2 Add Richer Walk-Forward and Event-Holdout Reporting
- [ ] T3 Densify the Resolved Training Dataset
- [ ] T4 Expand Market Microstructure Features
- [ ] T5 Add Event-Consensus and Cross-Market Disagreement Features
- [ ] T6 Strengthen External Enrichment
- [ ] T7 Add a Residual Model Training Track
- [ ] T8 Add Feature Ablation and Model Comparison Workflow
- [ ] T9 Make Conformal Calibration Segment-Aware
- [ ] T10 Add Evidence-Based Model Routing to the Live Service
- [ ] T11 Add Forecast-Quality Monitoring and Promotion Gates
- [ ] T12 Commit Baseline Research Artifact Pack

## Dependencies

- Depends on:
- Blocks:

## Risks

- Risk:
- Mitigation:

## Validation Plan

- [ ] Offline benchmark artifacts will be produced
- [ ] Time-split and event-holdout evidence will be required
- [ ] Segment-level regressions will be reviewed before rollout

## References

- [Forecasting improvement issue pack](https://github.com/tollama/Market-Calibration-Agent/blob/main/docs/ops/forecasting-improvement-issue-templates.md)
- [PRD2 offline eval guide](https://github.com/tollama/Market-Calibration-Agent/blob/main/docs/ops/prd2-offline-eval.md)
