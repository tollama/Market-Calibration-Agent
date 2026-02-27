import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';

import { requireAdminAuth } from '../../../../src/lib/admin-auth';
import { getKillSwitchState, setKillSwitchState } from '../../../../src/lib/kill-switch';
import { emitOpsEvent } from '../../../../src/lib/ops-events';
import {
  getAdvisoryDisclaimer,
  getAdvisoryMeta,
  isExecutionApiEnabled,
} from '../../../../src/lib/advisory-policy';

const stopSchema = z
  .object({
    enabled: z.boolean().optional().default(true),
    reason: z.string().max(500).optional(),
  })
  .passthrough();

export async function POST(req: NextRequest) {
  const advisory = getAdvisoryMeta('/api/execution/stop');
  const disclaimer = getAdvisoryDisclaimer('/api/execution/stop');
  const authError = requireAdminAuth(req, '/api/execution/stop');
  if (authError) {
    return authError;
  }

  if (!isExecutionApiEnabled()) {
    return NextResponse.json(
      {
        ok: false,
        code: 'EXECUTION_DISABLED',
        message: 'Execution control API is disabled in advisory-only mode. Set EXECUTION_API_ENABLED=true to override.',
        advisory,
        disclaimer,
      },
      { status: 403 }
    );
  }

  const parsed = stopSchema.safeParse(await req.json().catch(() => ({})));
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

  const current = await getKillSwitchState();
  const nextEnabled = parsed.data.enabled;

  if (nextEnabled === current.enabled) {
    return NextResponse.json(
      {
        ok: false,
        message: `Kill-switch is already ${nextEnabled ? 'ON' : 'OFF'}`,
        killSwitch: current,
        advisory,
        disclaimer,
      },
      { status: 409 }
    );
  }

  const updated = await setKillSwitchState({
    enabled: nextEnabled,
    reason: parsed.data.reason ?? null,
  });

  await emitOpsEvent({
    event: updated.enabled ? 'kill_switch_on' : 'kill_switch_off',
    severity: 'critical',
    reason: updated.reason ?? `kill-switch turned ${updated.enabled ? 'ON' : 'OFF'}`,
    details: {
      endpoint: '/api/execution/stop',
      updatedAt: updated.updatedAt,
    },
  });

  return NextResponse.json(
    {
      ok: true,
      message: `Kill-switch turned ${updated.enabled ? 'ON' : 'OFF'}`,
      killSwitch: updated,
      advisory,
      disclaimer,
    },
    { status: 200 }
  );
}

export async function GET() {
  const current = await getKillSwitchState();
  return NextResponse.json(
    {
      ok: true,
      executionEnabled: isExecutionApiEnabled(),
      advisory: getAdvisoryMeta('/api/execution/stop'),
      killSwitch: current,
      disclaimer: getAdvisoryDisclaimer('/api/execution/stop'),
    },
    { status: 200 }
  );
}
