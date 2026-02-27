import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';

import { requireAdminAuth } from '../../../../src/lib/admin-auth';
import { getKillSwitchState } from '../../../../src/lib/kill-switch';
import { prisma } from '../../../../src/lib/prisma';
import { emitOpsEvent } from '../../../../src/lib/ops-events';
import { RiskGuardError } from '../../../../src/lib/risk-guard';
import { enqueueExecutionStart } from '../../../../src/queue/producer';
import type { ExecutionMode, ExecutionStartRequest } from '../../../../src/queue/types';

const executionStartSchema = z
  .object({
    mode: z.enum(['paper', 'live', 'mock']).optional().default('mock'),
    dryRun: z
      .preprocess((value) => {
        if (typeof value === 'boolean') return value;
        if (typeof value === 'string') {
          const normalized = value.trim().toLowerCase();
          if (normalized === 'true' || normalized === '1') return true;
          if (normalized === 'false' || normalized === '0') return false;
        }
        return value;
      }, z.boolean())
      .optional()
      .default(true),
    maxPosition: z.coerce.number().positive().finite().optional().default(1000000),
    notes: z.string().max(1200).optional(),
  })
  .passthrough();

function normalizeRequest(rawBody: unknown): ExecutionStartRequest {
  if (!rawBody || typeof rawBody !== 'object') {
    return {};
  }

  const body = rawBody as Record<string, unknown>;

  const maxPositionFromBody =
    body.maxPosition ?? body.max_position ?? body.maxPos ?? body.max_position_limit;
  const dryRunFromBody = body.dryRun ?? body.dry_run;
  const modeFromBody = body.mode;

  return {
    mode: typeof modeFromBody === 'string' ? (modeFromBody as ExecutionMode) : undefined,
    dryRun: dryRunFromBody as ExecutionStartRequest['dryRun'],
    maxPosition: maxPositionFromBody as ExecutionStartRequest['maxPosition'],
    notes: typeof body.notes === 'string' ? body.notes : undefined,
  };
}

export async function POST(req: NextRequest) {
  const authError = requireAdminAuth(req);
  if (authError) {
    return authError;
  }

  const killSwitchState = await getKillSwitchState();
  if (killSwitchState.enabled) {
    await emitOpsEvent({
      event: 'execution_start_blocked',
      severity: 'critical',
      reason: killSwitchState.reason ?? 'kill-switch is ON',
      details: {
        endpoint: '/api/execution/start',
      },
    });

    return NextResponse.json(
      {
        ok: false,
        code: 'KILL_SWITCH_ON',
        message: 'Kill-switch is ON. Execution start is blocked.',
        killSwitch: killSwitchState,
      },
      { status: 409 }
    );
  }

  const parsed = executionStartSchema.safeParse(
    normalizeRequest(await req.json().catch(() => ({})))
  );

  if (!parsed.success) {
    return NextResponse.json(
      {
        ok: false,
        message: 'Invalid request body',
        errors: parsed.error.flatten().fieldErrors,
      },
      { status: 400 }
    );
  }

  const request = parsed.data;
  const runId = crypto.randomUUID();
  const requestedAt = new Date().toISOString();

  try {
    await prisma.calibrationRun.create({
      data: {
        id: runId,
        status: 'QUEUED',
        startedAt: new Date(requestedAt),
        notes: request.notes ?? `execution.start request accepted (mode=${request.mode})`,
      },
    });

    const queueResult = await enqueueExecutionStart({
      runId,
      mode: request.mode,
      requestedAt,
      dryRun: request.dryRun,
      maxPosition: request.maxPosition,
      notes: request.notes,
    });

    return NextResponse.json(
      {
        ok: true,
        runId,
        jobId: queueResult.jobId,
        state: 'queued',
        queue: queueResult.queueName,
        params: {
          mode: request.mode,
          dryRun: request.dryRun,
          maxPosition: request.maxPosition,
        },
      },
      { status: 202 }
    );
  } catch (error) {
    await prisma.calibrationRun
      .delete({ where: { id: runId } })
      .catch((deleteError) => {
        console.error('[execution.start] failed to rollback run row', deleteError);
      });

    const message =
      error instanceof Error ? error.message : 'Failed to enqueue execution start job';

    const isKillSwitch = message.toLowerCase().includes('kill-switch');
    const isRiskGuard = error instanceof RiskGuardError;
    const status = isKillSwitch || isRiskGuard ? 409 : 503;

    if (status === 409) {
      await emitOpsEvent({
        event: 'execution_start_blocked',
        severity: 'critical',
        runId,
        reason: message,
        details: {
          endpoint: '/api/execution/start',
          code: isRiskGuard ? error.code : isKillSwitch ? 'KILL_SWITCH_ON' : 'UNKNOWN_BLOCKED',
          ...(isRiskGuard ? error.details : {}),
        },
      });
    }

    return NextResponse.json(
      {
        ok: false,
        code: isRiskGuard ? error.code : isKillSwitch ? 'KILL_SWITCH_ON' : 'ENQUEUE_FAILED',
        message,
        ...(isRiskGuard ? { details: error.details } : {}),
      },
      { status }
    );
  }
}

export async function GET() {
  return NextResponse.json(
    {
      accepted: false,
      message: 'Use POST /api/execution/start',
    },
    { status: 405 }
  );
}
