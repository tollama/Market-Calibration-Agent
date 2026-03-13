import { emitOpsEvent } from './ops-events';
import {
  OrderStatusTransitionError,
  transitionOrderStatus,
  type OrderStatus,
} from './order-status';
import { prisma } from './prisma';

interface OrderCreatePort {
  order: {
    create(args: {
      data: {
        market: string;
        side: string;
        quantity: string;
        price: null;
        status: 'PENDING';
        realizedPnl: string;
      };
      select: { id: true };
    }): Promise<{ id: string }>;
  };
}

export interface ExecutionOrderLifecycleDeps {
  prismaClient: OrderCreatePort;
  transition: (params: { orderId: string; to: string }) => Promise<OrderStatus>;
  emit: typeof emitOpsEvent;
}

const defaultDeps: ExecutionOrderLifecycleDeps = {
  prismaClient: prisma,
  transition: transitionOrderStatus,
  emit: emitOpsEvent,
};

export function createExecutionOrderLifecycle(deps: ExecutionOrderLifecycleDeps = defaultDeps) {
  async function createPendingOrder(params: {
    runId: string;
    mode: string;
    dryRun: boolean;
  }): Promise<string> {
    const order = await deps.prismaClient.order.create({
      data: {
        market: `EXECUTION:${params.runId}`,
        side: params.mode === 'live' ? 'BUY' : 'PAPER_BUY',
        quantity: '1',
        price: null,
        status: 'PENDING',
        realizedPnl: '0',
      },
      select: { id: true },
    });

    await deps.emit({
      event: 'execution_order_created',
      severity: 'warning',
      runId: params.runId,
      reason: `orderId=${order.id} status=PENDING dryRun=${params.dryRun}`,
      details: {
        orderId: order.id,
      },
    });

    return order.id;
  }

  async function transitionWithGuard(params: {
    orderId: string | undefined;
    runId: string;
    to: OrderStatus;
    stage: 'worker_success' | 'worker_failed';
  }) {
    if (!params.orderId) {
      return;
    }

    try {
      await deps.transition({ orderId: params.orderId, to: params.to });
    } catch (error) {
      if (error instanceof OrderStatusTransitionError) {
        await deps.emit({
          event: 'order_status_transition_blocked',
          severity: error.code === 'INVALID_ORDER_STATUS_TRANSITION' ? 'warning' : 'critical',
          runId: params.runId,
          reason: error.message,
          details: {
            orderId: params.orderId,
            to: params.to,
            stage: params.stage,
            code: error.code,
            ...error.details,
          },
        });
      } else {
        await deps.emit({
          event: 'order_status_transition_error',
          severity: 'critical',
          runId: params.runId,
          reason: error instanceof Error ? error.message : String(error),
          details: {
            orderId: params.orderId,
            to: params.to,
            stage: params.stage,
          },
        });
      }

      throw error;
    }
  }

  return {
    createPendingOrder,
    markFilled: (params: { orderId: string | undefined; runId: string }) =>
      transitionWithGuard({
        ...params,
        to: 'FILLED',
        stage: 'worker_success',
      }),
    markFailed: (params: { orderId: string | undefined; runId: string }) =>
      transitionWithGuard({
        ...params,
        to: 'FAILED',
        stage: 'worker_failed',
      }),
  };
}

export const executionOrderLifecycle = createExecutionOrderLifecycle();
