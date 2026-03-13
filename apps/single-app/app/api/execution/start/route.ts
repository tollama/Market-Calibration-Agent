import { Prisma } from '@prisma/client';
import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';

import { requireAdminAuth } from '../../../../src/lib/admin-auth';
import { getKillSwitchState } from '../../../../src/lib/kill-switch';
import { prisma } from '../../../../src/lib/prisma';
import { emitOpsEvent } from '../../../../src/lib/ops-events';
import { RiskGuardError } from '../../../../src/lib/risk-guard';
import { executionOrderLifecycle } from '../../../../src/lib/execution-order-lifecycle';
import {
  getAdvisoryDisclaimer,
  getAdvisoryMeta,
  isExecutionApiEnabled,
  sanitizeAdvisoryText,
} from '../../../../src/lib/advisory-policy';
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
    idempotencyKey: z.string().trim().min(1).max(128).optional(),
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
  const idempotencyKeyFromBody = body.idempotencyKey ?? body.idempotency_key;

  return {
    mode: typeof modeFromBody === 'string' ? (modeFromBody as ExecutionMode) : undefined,
    dryRun: dryRunFromBody as ExecutionStartRequest['dryRun'],
    maxPosition: maxPositionFromBody as ExecutionStartRequest['maxPosition'],
    notes: typeof body.notes === 'string' ? body.notes : undefined,
    idempotencyKey:
      typeof idempotencyKeyFromBody === 'string' ? idempotencyKeyFromBody : undefined,
  };
}

function resolveIdempotencyKey(req: NextRequest, bodyKey?: string): string | undefined {
  const fromHeader = req.headers.get('idempotency-key')?.trim();
  if (fromHeader) {
    return fromHeader;
  }

  const normalizedBodyKey = bodyKey?.trim();
  return normalizedBodyKey || undefined;
}

function toPublicState(status: string): 'queued' | 'running' | 'completed' | 'failed' {
  if (status === 'RUNNING') return 'running';
  if (status === 'COMPLETED' || status === 'DRY_RUN_DONE') return 'completed';
  if (status === 'FAILED') return 'failed';
  return 'queued';
}

function replayResponse(run: { id: string; status: string }, idempotencyKey: string) {
  return NextResponse.json(
    {
      ok: true,
      runId: run.id,
      state: toPublicState(run.status),
      replayed: true,
      idempotencyKey,
      advisory: getAdvisoryMeta('/api/execution/start'),
      disclaimer: getAdvisoryDisclaimer('/api/execution/start'),
    },
    { status: 200 }
  );
}

function isIdempotencyUniqueError(error: unknown): error is Prisma.PrismaClientKnownRequestError {
  return (
    error instanceof Prisma.PrismaClientKnownRequestError &&
    error.code === 'P2002' &&
    Array.isArray(error.meta?.target) &&
    (error.meta?.target as string[]).includes('idempotencyKey')
  );
}

export async function POST(req: NextRequest) {
  const advisory = getAdvisoryMeta('/api/execution/start');
  const disclaimer = getAdvisoryDisclaimer('/api/execution/start');
  const authError = requireAdminAuth(req, '/api/execution/start');
  if (authError) {
    return authError;
  }

  if (!isExecutionApiEnabled()) {
    return NextResponse.json(
      {
        ok: false,
        code: 'EXECUTION_DISABLED',
        message: 'Execution API is disabled in advisory-only mode. Set EXECUTION_API_ENABLED=true to override.',
        advisory,
        disclaimer,
      },
      { status: 403 }
    );
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
        advisory,
        disclaimer,
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
        advisory,
        disclaimer,
      },
      { status: 400 }
    );
  }

  const request = parsed.data;
  const idempotencyKey = resolveIdempotencyKey(req, request.idempotencyKey);
  if (idempotencyKey) {
    const existingRun = await prisma.calibrationRun.findUnique({
      where: { idempotencyKey },
      select: {
        id: true,
        status: true,
      },
    });

    if (existingRun) {
      return replayResponse(existingRun, idempotencyKey);
    }
  }

  const runId = crypto.randomUUID();
  const requestedAt = new Date().toISOString();
  let createdRun = false;
  let createdOrderId: string | undefined;

  try {
    await prisma.calibrationRun.create({
      data: {
        id: runId,
        status: 'QUEUED',
        startedAt: new Date(requestedAt),
        notes: request.notes ?? `execution.start request accepted (mode=${request.mode})`,
        idempotencyKey,
      },
    });
    createdRun = true;

    createdOrderId = await executionOrderLifecycle.createPendingOrder({
      runId,
      mode: request.mode,
      dryRun: request.dryRun,
    });

    const queueResult = await enqueueExecutionStart({
      runId,
      mode: request.mode,
      requestedAt,
      dryRun: request.dryRun,
      maxPosition: request.maxPosition,
      notes: request.notes,
      idempotencyKey,
      orderId: createdOrderId,
    });

    return NextResponse.json(
      {
        ok: true,
        runId,
        jobId: queueResult.jobId,
        state: 'queued',
        queue: queueResult.queueName,
        ...(idempotencyKey ? { idempotencyKey } : {}),
        params: {
          mode: request.mode,
          dryRun: request.dryRun,
          maxPosition: request.maxPosition,
        },
        advisory,
        disclaimer,
      },
      { status: 202 }
    );
  } catch (error) {
    if (idempotencyKey && isIdempotencyUniqueError(error)) {
      const existingRun = await prisma.calibrationRun.findUnique({
        where: { idempotencyKey },
        select: {
          id: true,
          status: true,
        },
      });

      if (existingRun) {
        return replayResponse(existingRun, idempotencyKey);
      }
    }

    if (createdOrderId) {
      await prisma.order.delete({ where: { id: createdOrderId } }).catch((deleteError) => {
        console.error('[execution.start] failed to rollback order row', deleteError);
      });
    }

    if (createdRun) {
      await prisma.calibrationRun.delete({ where: { id: runId } }).catch((deleteError) => {
        console.error('[execution.start] failed to rollback run row', deleteError);
      });
    }

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
        message: sanitizeAdvisoryText(message),
        advisory,
        disclaimer,
      },
      { status }
    );
  }
}

export async function GET() {
  return NextResponse.json(
    {
      accepted: false,
      executionEnabled: isExecutionApiEnabled(),
      advisory: getAdvisoryMeta('/api/execution/start'),
      message: 'Use POST /api/execution/start',
      disclaimer: getAdvisoryDisclaimer('/api/execution/start'),
    },
    { status: 405 }
  );
}
