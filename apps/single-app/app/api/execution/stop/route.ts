import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';

import { requireAdminAuth } from '../../../../src/lib/admin-auth';
import { getKillSwitchState, setKillSwitchState } from '../../../../src/lib/kill-switch';
import { emitOpsEvent } from '../../../../src/lib/ops-events';

const stopSchema = z
  .object({
    enabled: z.boolean().optional().default(true),
    reason: z.string().max(500).optional(),
  })
  .passthrough();

export async function POST(req: NextRequest) {
  const authError = requireAdminAuth(req);
  if (authError) {
    return authError;
  }

  const parsed = stopSchema.safeParse(await req.json().catch(() => ({})));
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

  const current = await getKillSwitchState();
  const nextEnabled = parsed.data.enabled;

  if (nextEnabled === current.enabled) {
    return NextResponse.json(
      {
        ok: false,
        message: `Kill-switch is already ${nextEnabled ? 'ON' : 'OFF'}`,
        killSwitch: current,
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
    },
    { status: 200 }
  );
}

export async function GET() {
  const current = await getKillSwitchState();
  return NextResponse.json(
    {
      ok: true,
      killSwitch: current,
    },
    { status: 200 }
  );
}
