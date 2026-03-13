import { getKillSwitchState } from '../lib/kill-switch';
import { emitOpsEvent } from '../lib/ops-events';
import { assertRiskGuardsOrThrow, evaluateRiskGuards, RiskGuardError } from '../lib/risk-guard';
import { recordExecutionFailure } from '../lib/auto-killswitch';
import { isExecutionApiEnabled } from '../lib/advisory-policy';
import { createExecutionQueue } from './executionQueue';
import type { ExecutionJobPayload } from './types';

export async function enqueueExecutionStart(payload: ExecutionJobPayload) {
  if (!isExecutionApiEnabled()) {
    throw new Error('Execution is disabled by policy (EXECUTION_API_ENABLED=false)');
  }

  const killSwitch = await getKillSwitchState();
  if (killSwitch.enabled) {
    await emitOpsEvent({
      event: 'execution_start_blocked',
      severity: 'critical',
      runId: payload.runId,
      reason: killSwitch.reason ?? 'kill-switch is ON',
      details: {
        producer: 'enqueueExecutionStart',
      },
    });

    throw new Error(`Kill-switch is ON. enqueue blocked (${killSwitch.reason ?? 'no reason'})`);
  }
  const riskSnapshot = await evaluateRiskGuards();
  try {
    await assertRiskGuardsOrThrow('producer');
  } catch (error) {
    if (error instanceof RiskGuardError && error.code === 'RISK_LIMIT_EXCEEDED') {
      await recordExecutionFailure({
        runId: payload.runId,
        reason: error.message,
        currentLossAbs: riskSnapshot.dailyLoss.currentLossAbs,
      });
    }
    throw error;
  }

  const queue = createExecutionQueue();
  try {
    const job = await queue.add('execution.start', payload, {
      ...(payload.idempotencyKey
        ? {
            jobId: `execution:start:${payload.idempotencyKey}`,
          }
        : {}),
    });

    return {
      runId: payload.runId,
      jobId: String(job.id),
      queueName: queue.name,
    };
  } finally {
    await queue.close();
  }
}
