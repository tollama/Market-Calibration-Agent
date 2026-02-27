import { getKillSwitchState } from '../lib/kill-switch';
import { emitOpsEvent } from '../lib/ops-events';
import { assertRiskGuardsOrThrow } from '../lib/risk-guard';
import { createExecutionQueue } from './executionQueue';
import type { ExecutionJobPayload } from './types';

export async function enqueueExecutionStart(payload: ExecutionJobPayload) {
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
  await assertRiskGuardsOrThrow('producer');

  const queue = createExecutionQueue();
  try {
    const job = await queue.add('execution.start', payload);

    return {
      runId: payload.runId,
      jobId: String(job.id),
      queueName: queue.name
    };
  } finally {
    await queue.close();
  }
}
