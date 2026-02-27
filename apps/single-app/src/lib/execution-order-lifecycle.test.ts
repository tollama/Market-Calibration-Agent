import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createExecutionOrderLifecycle,
  type ExecutionOrderLifecycleDeps,
} from './execution-order-lifecycle';
import { OrderStatusTransitionError } from './order-status';

function buildDeps(overrides: Partial<ExecutionOrderLifecycleDeps> = {}): ExecutionOrderLifecycleDeps {
  return {
    prismaClient: {
      order: {
        create: async () => ({ id: 'order-1' }),
      },
    } as ExecutionOrderLifecycleDeps['prismaClient'],
    transition: async () => 'FILLED',
    emit: async () => undefined,
    ...overrides,
  };
}

test('createPendingOrder는 PENDING 주문을 생성하고 orderId를 반환한다', async () => {
  let capturedStatus: string | undefined;
  const lifecycle = createExecutionOrderLifecycle(
    buildDeps({
      prismaClient: {
        order: {
          create: async ({ data }: { data: { status: string } }) => {
            capturedStatus = data.status;
            return { id: 'order-created' };
          },
        },
      } as ExecutionOrderLifecycleDeps['prismaClient'],
    })
  );

  const orderId = await lifecycle.createPendingOrder({
    runId: 'run-1',
    mode: 'mock',
    dryRun: true,
  });

  assert.equal(orderId, 'order-created');
  assert.equal(capturedStatus, 'PENDING');
});

test('markFilled/markFailed는 transitionOrderStatus 단일 경로를 사용한다', async () => {
  const calls: Array<{ orderId: string; to: string }> = [];
  const lifecycle = createExecutionOrderLifecycle(
    buildDeps({
      transition: async ({ orderId, to }) => {
        calls.push({ orderId, to });
        return to === 'FILLED' ? 'FILLED' : 'FAILED';
      },
    })
  );

  await lifecycle.markFilled({ orderId: 'order-1', runId: 'run-1' });
  await lifecycle.markFailed({ orderId: 'order-1', runId: 'run-1' });

  assert.deepEqual(calls, [
    { orderId: 'order-1', to: 'FILLED' },
    { orderId: 'order-1', to: 'FAILED' },
  ]);
});

test('불법 전이 시 ops-event warning 로그를 남기고 기존 에러를 그대로 던진다', async () => {
  const events: Array<{ event: string; severity: string }> = [];
  const expected = new OrderStatusTransitionError(
    'INVALID_ORDER_STATUS_TRANSITION',
    'Invalid order status transition: FILLED -> FAILED',
    { from: 'FILLED', to: 'FAILED' }
  );

  const lifecycle = createExecutionOrderLifecycle(
    buildDeps({
      transition: async () => {
        throw expected;
      },
      emit: async (payload) => {
        events.push({ event: payload.event, severity: payload.severity });
      },
    })
  );

  await assert.rejects(() => lifecycle.markFailed({ orderId: 'order-1', runId: 'run-1' }), (err) => {
    assert.equal(err, expected);
    return true;
  });

  assert.deepEqual(events, [
    {
      event: 'order_status_transition_blocked',
      severity: 'warning',
    },
  ]);
});
