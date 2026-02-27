import assert from 'node:assert/strict';
import test from 'node:test';

import { Queue, Worker } from 'bullmq';

import { POST as startExecution } from '../../app/api/execution/start/route';
import { executionOrderLifecycle } from './execution-order-lifecycle';
import { prisma } from './prisma';
import { EXECUTION_QUEUE_NAME } from '../queue/executionQueue';
import { getRedisConnection } from '../queue/config';
import type { ExecutionJobPayload } from '../queue/types';

const TEST_TIMEOUT_MS = 15_000;
const POLL_INTERVAL_MS = 150;

async function waitForOrderTerminalStatus(orderId: string) {
  const startedAt = Date.now();

  while (Date.now() - startedAt < TEST_TIMEOUT_MS) {
    const order = await prisma.order.findUnique({ where: { id: orderId }, select: { status: true } });
    if (order && (order.status === 'FILLED' || order.status === 'FAILED')) {
      return order.status;
    }

    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
  }

  throw new Error(`order terminal status timeout exceeded (${TEST_TIMEOUT_MS}ms)`);
}

test('start API -> queue/worker 처리 -> order 상태 전이 + 불법 전이 ops-event 검증', { timeout: 30_000 }, async (t) => {
  process.env.ADMIN_API_TOKEN ??= 'test-admin-token';

  const connection = getRedisConnection();
  const queue = new Queue<ExecutionJobPayload>(EXECUTION_QUEUE_NAME, { connection });

  await prisma.order.deleteMany({ where: { market: { startsWith: 'EXECUTION:' } } });
  await prisma.calibrationRun.deleteMany({ where: { notes: { contains: '[e2e-test]' } } });
  await queue.obliterate({ force: true });

  const worker = new Worker<ExecutionJobPayload>(
    EXECUTION_QUEUE_NAME,
    async (job) => {
      await prisma.calibrationRun.update({
        where: { id: job.data.runId },
        data: {
          status: 'RUNNING',
          notes: '[e2e-test] worker picked',
        },
      });

      await executionOrderLifecycle.markFilled({
        orderId: job.data.orderId,
        runId: job.data.runId,
      });

      await prisma.calibrationRun.update({
        where: { id: job.data.runId },
        data: {
          status: 'COMPLETED',
          finishedAt: new Date(),
          notes: '[e2e-test] worker completed',
        },
      });

      return { ok: true };
    },
    { connection }
  );

  t.after(async () => {
    await worker.close();
    await queue.close();
  });

  const idempotencyKey = `e2e-order-sm-${Date.now()}`;
  const req = new Request('http://localhost/api/execution/start', {
    method: 'POST',
    headers: {
      authorization: `Bearer ${process.env.ADMIN_API_TOKEN}`,
      'content-type': 'application/json',
      'idempotency-key': idempotencyKey,
    },
    body: JSON.stringify({
      mode: 'mock',
      dryRun: true,
      maxPosition: 100,
      notes: '[e2e-test] start request',
    }),
  });

  const response = await startExecution(req as never);
  assert.equal(response.status, 202);

  const body = (await response.json()) as { runId: string };
  assert.ok(body.runId, 'runId should be returned');

  const createdOrder = await prisma.order.findFirst({
    where: { market: `EXECUTION:${body.runId}` },
    select: { id: true, status: true },
  });

  assert.ok(createdOrder, 'PENDING order should be created by start API');
  assert.equal(createdOrder.status, 'PENDING');

  const terminalStatus = await waitForOrderTerminalStatus(createdOrder.id);
  assert.equal(terminalStatus, 'FILLED');

  const warnLogs: string[] = [];
  const originalWarn = console.warn;
  console.warn = (...args: unknown[]) => {
    warnLogs.push(args.map((arg) => String(arg)).join(' '));
    originalWarn(...args);
  };

  try {
    await assert.rejects(
      () => executionOrderLifecycle.markFailed({ orderId: createdOrder.id, runId: body.runId }),
      (error: unknown) => {
        assert.ok(error instanceof Error);
        assert.match(error.message, /Invalid order status transition: FILLED -> FAILED/);
        return true;
      }
    );
  } finally {
    console.warn = originalWarn;
  }

  assert.ok(
    warnLogs.some((line) => line.includes('order_status_transition_blocked')),
    'invalid transition should emit order_status_transition_blocked ops-event'
  );

  const finalOrder = await prisma.order.findUnique({
    where: { id: createdOrder.id },
    select: { status: true },
  });
  assert.equal(finalOrder?.status, 'FILLED');
});
