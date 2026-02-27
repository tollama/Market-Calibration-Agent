import test from 'node:test';
import assert from 'node:assert/strict';

import { evaluateAutoKillSwitchTrigger, type AutoKillSwitchConfig } from './auto-killswitch';

const baseConfig: AutoKillSwitchConfig = {
  enabled: true,
  consecutiveFailureThreshold: 3,
  maxDailyLoss: 500_000,
  latencyThresholdMs: 30_000,
  latencySpikeMultiplier: 3,
  latencySpikeMinSamples: 5,
  latencyEwmaAlpha: 0.2,
};

test('연속 실패 임계 초과 시 auto kill-switch 트리거', () => {
  const result = evaluateAutoKillSwitchTrigger(
    {
      consecutiveFailures: 3,
      latencySamples: 0,
    },
    baseConfig
  );

  assert.equal(result.triggered, true);
  assert.equal(result.type, 'consecutive_failures');
});

test('손실 임계 초과 시 auto kill-switch 트리거', () => {
  const result = evaluateAutoKillSwitchTrigger(
    {
      consecutiveFailures: 0,
      currentLossAbs: 500_001,
      latencySamples: 0,
    },
    baseConfig
  );

  assert.equal(result.triggered, true);
  assert.equal(result.type, 'loss_limit');
});

test('지연 절대 임계 초과 시 auto kill-switch 트리거', () => {
  const result = evaluateAutoKillSwitchTrigger(
    {
      consecutiveFailures: 0,
      latestLatencyMs: 30_000,
      latencySamples: 1,
      latencyEwmaMs: 12_000,
    },
    baseConfig
  );

  assert.equal(result.triggered, true);
  assert.equal(result.type, 'latency_threshold');
});

test('지연 급증(스파이크) 시 auto kill-switch 트리거', () => {
  const result = evaluateAutoKillSwitchTrigger(
    {
      consecutiveFailures: 0,
      latestLatencyMs: 18_000,
      latencySamples: 6,
      latencyEwmaMs: 5_000,
    },
    baseConfig
  );

  assert.equal(result.triggered, true);
  assert.equal(result.type, 'latency_spike');
});
