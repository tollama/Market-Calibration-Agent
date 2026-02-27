import { prisma } from './prisma';

const EXECUTION_CONTROL_KEY = 'global';

let killSwitchCache: { enabled: boolean; reason: string | null; updatedAt: string | null } | null = null;

async function loadControl() {
  const control = await prisma.executionControl.upsert({
    where: { key: EXECUTION_CONTROL_KEY },
    create: { key: EXECUTION_CONTROL_KEY, killSwitch: false },
    update: {},
  });

  killSwitchCache = {
    enabled: control.killSwitch,
    reason: control.reason,
    updatedAt: control.updatedAt.toISOString(),
  };

  return killSwitchCache;
}

export async function getKillSwitchState() {
  return killSwitchCache ?? loadControl();
}

export async function refreshKillSwitchState() {
  return loadControl();
}

export async function setKillSwitchState(params: { enabled: boolean; reason?: string | null }) {
  const control = await prisma.executionControl.upsert({
    where: { key: EXECUTION_CONTROL_KEY },
    create: {
      key: EXECUTION_CONTROL_KEY,
      killSwitch: params.enabled,
      reason: params.reason ?? null,
    },
    update: {
      killSwitch: params.enabled,
      reason: params.reason ?? null,
    },
  });

  killSwitchCache = {
    enabled: control.killSwitch,
    reason: control.reason,
    updatedAt: control.updatedAt.toISOString(),
  };

  return killSwitchCache;
}
