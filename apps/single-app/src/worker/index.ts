import 'dotenv/config';
import { execFile } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { promisify } from 'node:util';
import { QueueEvents, Worker } from 'bullmq';
import { getKillSwitchState, refreshKillSwitchState } from '../lib/kill-switch';
import { emitOpsEvent } from '../lib/ops-events';
import { executionOrderLifecycle } from '../lib/execution-order-lifecycle';
import { prisma } from '../lib/prisma';
import { assertRiskGuardsOrThrow, evaluateRiskGuards, RiskGuardError } from '../lib/risk-guard';
import { recordExecutionFailure, recordExecutionSuccess } from '../lib/auto-killswitch';
import { isExecutionApiEnabled } from '../lib/advisory-policy';
import { EXECUTION_QUEUE_NAME, executionJobDefaults } from '../queue/executionQueue';
import { getRedisConnection } from '../queue/config';
import type { ExecutionJobPayload } from '../queue/types';

const connection = getRedisConnection();
const MAX_POSITION_LIMIT = Number(process.env.MAX_POSITION_LIMIT || '1000000');
const EXEC_PYTHON = process.env.CALIBRATION_PYTHON_BIN || 'python';
const EXEC_TIMEOUT_MS = Number(process.env.CALIBRATION_PYTHON_TIMEOUT_MS || '120000');
const EXEC_MODULE_CANDIDATES = [
  'runners.features.calibration',
  'runners.features.calibration.main',
  'pipelines.daily_job',
];
const execFileAsync = promisify(execFile);

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const REPO_ROOT = resolve(__dirname, '../../../../');

function hasPythonModule(moduleName: string): boolean {
  const relPath = moduleName.split('.').join('/');
  return (
    existsSync(join(REPO_ROOT, `${relPath}.py`)) ||
    existsSync(join(REPO_ROOT, relPath, '__init__.py'))
  );
}

function resolveCalibrationModules(): string[] {
  const modules: string[] = [];
  const explicitModule = process.env.CALIBRATION_ENTRYPOINT_MODULE?.trim();
  if (explicitModule) {
    modules.push(explicitModule);
  }

  for (const moduleName of EXEC_MODULE_CANDIDATES) {
    if (hasPythonModule(moduleName)) {
      modules.push(moduleName);
    }
  }

  if (!modules.includes('pipelines.daily_job') && existsSync(join(REPO_ROOT, 'pipelines', 'daily_job.py'))) {
    modules.push('pipelines.daily_job');
  }

  if (modules.length === 0) {
    modules.push('pipelines.daily_job');
  }

  return [...new Set(modules)];
}

interface PipelineOutput {
  run_id: string;
  success: boolean;
  stages?: Array<{
    name: string;
    status: string;
  }>;
  failure?: {
    stage?: string;
    reason?: string;
  };
}

function toNumber(value: unknown): number | null {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null;
  }

  if (typeof value === 'string') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  if (value && typeof value === 'object' && 'toNumber' in value) {
    const parsed = Number((value as { toNumber: () => number }).toNumber());
    return Number.isFinite(parsed) ? parsed : null;
  }

  return null;
}

async function getCurrentMaxPosition(): Promise<number> {
  const positions = await prisma.position.findMany({ select: { size: true } });
  const total = positions.reduce((sum, position) => {
    const value = toNumber(position.size);
    if (value === null) {
      return sum;
    }
    return sum + Math.abs(value);
  }, 0);
  return total;
}

function summarizeNotes({
  mode,
  dryRun,
  maxPosition,
  message,
  requestedAt,
}: {
  mode: ExecutionJobPayload['mode'];
  dryRun: boolean;
  maxPosition: number;
  message: string;
  requestedAt: string;
}) {
  return [
    `mode=${mode}`,
    `dryRun=${dryRun}`,
    `maxPosition=${maxPosition}`,
    `requestedAt=${requestedAt}`,
    message,
  ].join(' | ');
}

async function executeCalibrationPipeline(payload: ExecutionJobPayload): Promise<string> {
  if (payload.dryRun) {
    return [
      `calibration pipeline dry-run`,
      `mode=${payload.mode}`,
      `maxPosition=${payload.maxPosition}`,
    ].join(' | ');
  }

  const entrypointCandidates = resolveCalibrationModules();
  const requestedAt = payload.requestedAt;

  const entrypointCandidatesLiteral = JSON.stringify(entrypointCandidates);
  const script = `
import importlib
import json

entrypoints = ${entrypointCandidatesLiteral}
result = None

for entrypoint in entrypoints:
    try:
        module = importlib.import_module(entrypoint)
    except ModuleNotFoundError:
        continue
    except Exception:
        raise

    entry = getattr(module, "run_calibration", None) or getattr(module, "run_daily_job", None)
    if not callable(entry):
        continue

    try:
        result = entry(run_id=${JSON.stringify(payload.runId)}, continue_on_stage_failure=True)
    except TypeError:
        try:
            result = entry(run_id=${JSON.stringify(payload.runId)})
        except TypeError:
            result = entry()

    if result is not None:
        break

if result is None:
    raise RuntimeError(f"No compatible calibration entrypoint found: {entrypoints}")
    
print(json.dumps(result))
`;

  const args = ['-c', script];
  const pythonPath = [REPO_ROOT, process.env.PYTHONPATH].filter(Boolean).join(':');

  const command = await execFileAsync(EXEC_PYTHON, args, {
    cwd: REPO_ROOT,
    timeout: Number.isFinite(EXEC_TIMEOUT_MS) ? EXEC_TIMEOUT_MS : 120000,
    env: {
      ...process.env,
      PYTHONPATH: pythonPath,
    },
  });

  const output = command.stdout?.toString().trim();
  const stderr = command.stderr?.toString().trim();
  if (stderr) {
    console.warn(`[worker] calibration pipeline stderr | runId=${payload.runId} | ${stderr}`);
  }
  if (!output) {
    throw new Error(`calibration entrypoint returned empty output | mode=${payload.mode}`);
  }

  let parsed: PipelineOutput;
  try {
    const lines = output.split('\n').filter((line) => line.trim());
    parsed = JSON.parse(lines[lines.length - 1]!) as PipelineOutput;
  } catch (error) {
    throw new Error(`Failed to parse calibration pipeline output: ${String(error)}`);
  }

  if (parsed.success !== true) {
    const failureMessage = parsed.failure ? `${parsed.failure.stage || 'unknown'}: ${parsed.failure.reason || 'failure'}` : 'pipeline did not report success';
    throw new Error(
      `calibration pipeline failed | runId=${payload.runId} | requestedAt=${requestedAt} | reason=${failureMessage}`
    );
  }

  return [
    `calibration pipeline done`,
    `runId=${payload.runId}`,
    `entrypoint=${entrypointCandidates[0]}`,
    `stages=${parsed.stages?.length ?? 0}`,
  ].join(' | ');
}

async function markRunFailed(runId: string, error: unknown, orderId?: string): Promise<void> {
  const reason = error instanceof Error ? error.message : 'Unknown error';
  const riskSuffix =
    error instanceof RiskGuardError
      ? ` | code=${error.code} | details=${JSON.stringify(error.details)}`
      : '';

  await prisma.calibrationRun
    .update({
      where: { id: runId },
      data: {
        status: 'FAILED',
        finishedAt: new Date(),
        notes: `status=FAILED | error=${reason}${riskSuffix}`,
      },
    })
    .catch((err) => {
      console.error(`[worker] failed to mark run failed runId=${runId}`, err);
    });

  await executionOrderLifecycle.markFailed({
    orderId,
    runId,
  });
}

const worker = new Worker<ExecutionJobPayload>(
  EXECUTION_QUEUE_NAME,
  async (job) => {
    const payload = job.data;
    const requestedAt = payload.requestedAt;
    const startedAtMs = Date.now();

    if (!isExecutionApiEnabled()) {
      throw new Error('Execution is disabled by policy (EXECUTION_API_ENABLED=false)');
    }

    const killSwitch = await refreshKillSwitchState().catch(() => getKillSwitchState());
    if (killSwitch.enabled) {
      await emitOpsEvent({
        event: 'execution_start_blocked',
        severity: 'critical',
        runId: payload.runId,
        jobId: job.id ? String(job.id) : undefined,
        reason: killSwitch.reason ?? 'kill-switch is ON',
        details: {
          stage: 'worker_precheck',
        },
      });
      throw new Error(`kill-switch is ON: ${killSwitch.reason ?? 'no reason provided'}`);
    }

    const riskSnapshot = await evaluateRiskGuards();
    try {
      await assertRiskGuardsOrThrow('worker');
    } catch (error) {
      if (error instanceof RiskGuardError && error.code === 'RISK_LIMIT_EXCEEDED') {
        await recordExecutionFailure({
          runId: payload.runId,
          jobId: job.id ? String(job.id) : undefined,
          reason: error.message,
          currentLossAbs: riskSnapshot.dailyLoss.currentLossAbs,
          latencyMs: Date.now() - startedAtMs,
        });
      }
      throw error;
    }

    await prisma.calibrationRun.upsert({
      where: { id: payload.runId },
      create: {
        id: payload.runId,
        status: 'RUNNING',
        startedAt: new Date(requestedAt),
        notes: summarizeNotes({
          mode: payload.mode,
          dryRun: payload.dryRun,
          maxPosition: payload.maxPosition,
          message: 'worker picked job',
          requestedAt,
        }),
      },
      update: {
        status: 'RUNNING',
        startedAt: new Date(requestedAt),
        finishedAt: null,
        notes: summarizeNotes({
          mode: payload.mode,
          dryRun: payload.dryRun,
          maxPosition: payload.maxPosition,
          message: 'worker picked job',
          requestedAt,
        }),
      },
    });

    const currentPosition = await getCurrentMaxPosition();
    if (currentPosition > payload.maxPosition) {
      const reason = `risk-guard: currentPosition(${currentPosition}) > maxPosition(${payload.maxPosition})`;
      throw new Error(reason);
    }

    if (currentPosition > MAX_POSITION_LIMIT) {
      const reason = `risk-guard: infra maxPositionLimit=${MAX_POSITION_LIMIT} exceeded by currentPosition(${currentPosition})`;
      throw new Error(reason);
    }

    const summary = await executeCalibrationPipeline(payload);
    const resultStatus = payload.dryRun ? 'DRY_RUN_DONE' : 'COMPLETED';

    await prisma.calibrationRun.update({
      where: { id: payload.runId },
      data: {
        status: resultStatus,
        finishedAt: new Date(),
        notes: summarizeNotes({
          mode: payload.mode,
          dryRun: payload.dryRun,
          maxPosition: payload.maxPosition,
          message: summary,
          requestedAt,
        }),
      },
    });

    await executionOrderLifecycle.markFilled({
      orderId: payload.orderId,
      runId: payload.runId,
    });

    const latestRiskSnapshot = await evaluateRiskGuards().catch(() => null);
    await recordExecutionSuccess({
      runId: payload.runId,
      jobId: job.id ? String(job.id) : undefined,
      latencyMs: Date.now() - startedAtMs,
      currentLossAbs: latestRiskSnapshot?.dailyLoss.currentLossAbs,
    });

    return { calibrationRunId: payload.runId, status: resultStatus };
  },
  {
    connection,
  }
);

const queueEvents = new QueueEvents(EXECUTION_QUEUE_NAME, { connection });

worker.on('active', (job) => {
  console.log(`[worker] active job id=${job.id} attemptsMade=${job.attemptsMade}`);
});

worker.on('completed', (job) => {
  console.log(`[worker] completed job id=${job.id}`);
});

worker.on('failed', (job, err) => {
  console.error(
    `[worker] failed job id=${job?.id} attemptsMade=${job?.attemptsMade ?? 0} error=${err.message}`
  );

  const runId = job?.data?.runId;
  const jobId = job?.id ? String(job.id) : undefined;
  const reason = err instanceof Error ? err.message : String(err);

  void emitOpsEvent({
    event: 'worker_failed',
    severity: 'critical',
    runId,
    jobId,
    reason,
    details: {
      attemptsMade: job?.attemptsMade ?? 0,
    },
  });

  void evaluateRiskGuards()
    .catch(() => null)
    .then((snapshot) =>
      recordExecutionFailure({
        runId,
        jobId,
        reason,
        currentLossAbs: snapshot?.dailyLoss.currentLossAbs,
      })
    );

  const configuredAttempts =
    typeof job?.opts?.attempts === 'number'
      ? job.opts.attempts
      : typeof executionJobDefaults.attempts === 'number'
        ? executionJobDefaults.attempts
        : 1;

  if ((job?.attemptsMade ?? 0) >= configuredAttempts) {
    void emitOpsEvent({
      event: 'retry_exhausted',
      severity: 'critical',
      runId,
      jobId,
      reason,
      details: {
        attemptsMade: job?.attemptsMade ?? 0,
        configuredAttempts,
      },
    });
  }

  if (runId) {
    void markRunFailed(runId, err, job?.data?.orderId);
  }
});

queueEvents.on('waiting', ({ jobId }) => {
  console.log(`[worker] waiting job id=${jobId}`);
});

queueEvents.on('stalled', ({ jobId }) => {
  console.warn(`[worker] stalled job id=${jobId}`);
});

queueEvents.on('failed', ({ jobId, failedReason }) => {
  console.error(`[worker] queue-event failed job id=${jobId} reason=${failedReason}`);
});

console.log(`[worker] started. queue=${EXECUTION_QUEUE_NAME}`);

async function shutdown(signal: string) {
  console.log(`[worker] shutdown signal received: ${signal}`);
  await worker.close();
  await queueEvents.close();
  await prisma.$disconnect();
  process.exit(0);
}

process.on('SIGINT', () => void shutdown('SIGINT'));
process.on('SIGTERM', () => void shutdown('SIGTERM'));
