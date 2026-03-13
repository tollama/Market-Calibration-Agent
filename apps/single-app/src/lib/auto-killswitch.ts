import { emitOpsEvent } from './ops-events';
import { getKillSwitchState, setKillSwitchState } from './kill-switch';

export type AutoKillSwitchTriggerType =
  | 'consecutive_failures'
  | 'loss_limit'
  | 'latency_threshold'
  | 'latency_spike';

export interface AutoKillSwitchConfig {
  enabled: boolean;
  consecutiveFailureThreshold: number;
  maxDailyLoss: number;
  latencyThresholdMs: number;
  latencySpikeMultiplier: number;
  latencySpikeMinSamples: number;
  latencyEwmaAlpha: number;
}

export interface AutoKillSwitchRuntimeState {
  consecutiveFailures: number;
  latencySamples: number;
  latencyEwmaMs: number | null;
}

export interface AutoKillSwitchInput {
  consecutiveFailures: number;
  currentLossAbs?: number | null;
  latestLatencyMs?: number | null;
  latencySamples: number;
  latencyEwmaMs?: number | null;
}

export interface AutoKillSwitchTriggerResult {
  triggered: boolean;
  type?: AutoKillSwitchTriggerType;
  reason?: string;
  details?: Record<string, unknown>;
}

const runtimeState: AutoKillSwitchRuntimeState = {
  consecutiveFailures: 0,
  latencySamples: 0,
  latencyEwmaMs: null,
};

function toFinitePositiveInt(raw: string | undefined, fallback: number): number {
  const parsed = Number(raw);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return fallback;
  }
  return Math.floor(parsed);
}

function toFinitePositiveNumber(raw: string | undefined, fallback: number): number {
  const parsed = Number(raw);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return fallback;
  }
  return parsed;
}

function toFiniteUnitInterval(raw: string | undefined, fallback: number): number {
  const parsed = Number(raw);
  if (!Number.isFinite(parsed) || parsed <= 0 || parsed > 1) {
    return fallback;
  }
  return parsed;
}

export function loadAutoKillSwitchConfig(env: NodeJS.ProcessEnv = process.env): AutoKillSwitchConfig {
  const autoEnabledRaw = env.AUTO_KILL_SWITCH_ENABLED?.trim().toLowerCase();
  const enabled = autoEnabledRaw === undefined ? true : autoEnabledRaw !== 'false' && autoEnabledRaw !== '0';

  const maxDailyLossFallback = toFinitePositiveNumber(env.RISK_MAX_DAILY_LOSS, 500_000);

  return {
    enabled,
    consecutiveFailureThreshold: toFinitePositiveInt(env.AUTO_KILL_SWITCH_CONSECUTIVE_FAILURES, 3),
    maxDailyLoss: toFinitePositiveNumber(env.AUTO_KILL_SWITCH_MAX_DAILY_LOSS, maxDailyLossFallback),
    latencyThresholdMs: toFinitePositiveNumber(env.AUTO_KILL_SWITCH_LATENCY_THRESHOLD_MS, 30_000),
    latencySpikeMultiplier: toFinitePositiveNumber(env.AUTO_KILL_SWITCH_LATENCY_SPIKE_MULTIPLIER, 3),
    latencySpikeMinSamples: toFinitePositiveInt(env.AUTO_KILL_SWITCH_LATENCY_SPIKE_MIN_SAMPLES, 5),
    latencyEwmaAlpha: toFiniteUnitInterval(env.AUTO_KILL_SWITCH_LATENCY_EWMA_ALPHA, 0.2),
  };
}

export function evaluateAutoKillSwitchTrigger(
  input: AutoKillSwitchInput,
  config: AutoKillSwitchConfig
): AutoKillSwitchTriggerResult {
  if (!config.enabled) {
    return { triggered: false };
  }

  if (input.consecutiveFailures >= config.consecutiveFailureThreshold) {
    return {
      triggered: true,
      type: 'consecutive_failures',
      reason: `auto kill-switch: consecutive failures ${input.consecutiveFailures} >= ${config.consecutiveFailureThreshold}`,
      details: {
        consecutiveFailures: input.consecutiveFailures,
        threshold: config.consecutiveFailureThreshold,
      },
    };
  }

  if (
    typeof input.currentLossAbs === 'number' &&
    Number.isFinite(input.currentLossAbs) &&
    input.currentLossAbs >= config.maxDailyLoss
  ) {
    return {
      triggered: true,
      type: 'loss_limit',
      reason: `auto kill-switch: daily loss ${input.currentLossAbs} >= ${config.maxDailyLoss}`,
      details: {
        currentLossAbs: input.currentLossAbs,
        maxDailyLoss: config.maxDailyLoss,
      },
    };
  }

  if (
    typeof input.latestLatencyMs === 'number' &&
    Number.isFinite(input.latestLatencyMs) &&
    input.latestLatencyMs >= config.latencyThresholdMs
  ) {
    return {
      triggered: true,
      type: 'latency_threshold',
      reason: `auto kill-switch: latency ${input.latestLatencyMs}ms >= ${config.latencyThresholdMs}ms`,
      details: {
        latestLatencyMs: input.latestLatencyMs,
        latencyThresholdMs: config.latencyThresholdMs,
      },
    };
  }

  if (
    typeof input.latestLatencyMs === 'number' &&
    Number.isFinite(input.latestLatencyMs) &&
    typeof input.latencyEwmaMs === 'number' &&
    Number.isFinite(input.latencyEwmaMs) &&
    input.latencySamples >= config.latencySpikeMinSamples &&
    input.latestLatencyMs >= input.latencyEwmaMs * config.latencySpikeMultiplier
  ) {
    return {
      triggered: true,
      type: 'latency_spike',
      reason: `auto kill-switch: latency spike ${input.latestLatencyMs}ms >= ${config.latencySpikeMultiplier}x baseline(${input.latencyEwmaMs}ms)`,
      details: {
        latestLatencyMs: input.latestLatencyMs,
        latencyEwmaMs: input.latencyEwmaMs,
        latencySpikeMultiplier: config.latencySpikeMultiplier,
        latencySamples: input.latencySamples,
      },
    };
  }

  return { triggered: false };
}

function updateLatencyEwma(latencyMs: number, alpha: number) {
  runtimeState.latencyEwmaMs =
    runtimeState.latencyEwmaMs === null
      ? latencyMs
      : alpha * latencyMs + (1 - alpha) * runtimeState.latencyEwmaMs;
  runtimeState.latencySamples += 1;
}

async function activateKillSwitch(trigger: AutoKillSwitchTriggerResult, context: Record<string, unknown>) {
  if (!trigger.triggered || !trigger.reason || !trigger.type) {
    return;
  }

  const current = await getKillSwitchState();
  if (current.enabled) {
    return;
  }

  const updated = await setKillSwitchState({
    enabled: true,
    reason: trigger.reason,
  });

  await emitOpsEvent({
    event: 'kill_switch_on',
    severity: 'critical',
    reason: trigger.reason,
    details: {
      source: 'auto_kill_switch',
      triggerType: trigger.type,
      updatedAt: updated.updatedAt,
      ...trigger.details,
      ...context,
    },
  });
}

export async function recordExecutionSuccess(params: {
  latencyMs: number;
  runId?: string;
  jobId?: string;
  currentLossAbs?: number;
}) {
  const config = loadAutoKillSwitchConfig();
  runtimeState.consecutiveFailures = 0;

  const trigger = evaluateAutoKillSwitchTrigger(
    {
      consecutiveFailures: runtimeState.consecutiveFailures,
      currentLossAbs: params.currentLossAbs,
      latestLatencyMs: params.latencyMs,
      latencySamples: runtimeState.latencySamples,
      latencyEwmaMs: runtimeState.latencyEwmaMs,
    },
    config
  );

  await activateKillSwitch(trigger, {
    runId: params.runId,
    jobId: params.jobId,
    phase: 'success',
  });

  updateLatencyEwma(params.latencyMs, config.latencyEwmaAlpha);
}

export async function recordExecutionFailure(params: {
  runId?: string;
  jobId?: string;
  reason?: string;
  latencyMs?: number;
  currentLossAbs?: number;
}) {
  const config = loadAutoKillSwitchConfig();
  runtimeState.consecutiveFailures += 1;

  const trigger = evaluateAutoKillSwitchTrigger(
    {
      consecutiveFailures: runtimeState.consecutiveFailures,
      currentLossAbs: params.currentLossAbs,
      latestLatencyMs: params.latencyMs,
      latencySamples: runtimeState.latencySamples,
      latencyEwmaMs: runtimeState.latencyEwmaMs,
    },
    config
  );

  await activateKillSwitch(trigger, {
    runId: params.runId,
    jobId: params.jobId,
    phase: 'failure',
    failureReason: params.reason,
  });

  if (typeof params.latencyMs === 'number' && Number.isFinite(params.latencyMs)) {
    updateLatencyEwma(params.latencyMs, config.latencyEwmaAlpha);
  }
}

export function __resetAutoKillSwitchRuntimeStateForTest() {
  runtimeState.consecutiveFailures = 0;
  runtimeState.latencySamples = 0;
  runtimeState.latencyEwmaMs = null;
}
